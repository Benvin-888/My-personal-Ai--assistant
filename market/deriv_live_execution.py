"""APEX / BENVIN Phase 2.37 - Deriv Live Execution Adapter.

This is the first broker-specific live execution adapter.  It is deliberately
narrow: it accepts only LIVE ExecutionRequest objects, validates them through
the provider-neutral ExecutionGateway, independently verifies the authenticated
real Deriv session, requires explicit live enablement plus an explicit
per-execution confirmation, requests an explicit Deriv contract proposal, and
only then calls Deriv's authenticated ``buy`` endpoint.

The adapter never translates a spot-FX TradePlan into a Deriv contract.  The
caller must provide an explicit DerivContractSpec, just as the demo adapter
does.  This prevents an ordinary APEX risk plan from silently becoming a
broker-specific options contract.

Phase 2.37 does not perform broker-side post-fill reconciliation; Phase 2.38
will add that verification layer.  A CONFIRMED outcome means Deriv returned a
valid authenticated ``buy`` response with a contract id and buy price.  It is
still not a substitute for later broker-state reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import os
from typing import Any, Mapping, Protocol
from .deriv_demo import DerivContractSpec, DerivProposal
from .deriv_live_account import (
    DerivLiveAccountConfig,
    DerivLiveAccountConnectivity,
    DerivLiveConnectivityResult,
    REAL_WS_PREFIX,
)
from .execution import (
    ExecutionAdapterCapability,
    ExecutionGateway,
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ExecutionPolicy,
)
from .execution_outcome import (
    ExecutionOutcome,
    ExecutionOutcomeStatus,
    validate_execution_outcome,
)


class DerivLiveExecutionError(ValueError):
    """Raised for invalid live-adapter configuration or execution input."""


class DerivLiveExecutionStatus(str, Enum):
    BLOCKED = "BLOCKED"
    PROPOSAL_REQUESTED = "PROPOSAL_REQUESTED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DerivLiveExecutionConfig:
    """Configuration for the real Deriv execution adapter.

    ``live_enabled`` defaults to False and is never inferred from LIVE mode.
    The environment flag is an additional explicit operational switch.
    """

    account_id: str
    authorization_token: str
    app_id: str
    rest_base_url: str = "https://api.derivws.com"
    timeout_seconds: float = 10.0
    live_enabled: bool = False

    def __post_init__(self) -> None:
        for name in ("account_id", "authorization_token", "app_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DerivLiveExecutionError(f"{name} must be a non-empty string")
        if not isinstance(self.rest_base_url, str) or not self.rest_base_url.startswith("https://"):
            raise DerivLiveExecutionError("rest_base_url must use HTTPS")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float)):
            raise DerivLiveExecutionError("timeout_seconds must be numeric")
        if self.timeout_seconds <= 0:
            raise DerivLiveExecutionError("timeout_seconds must be positive")
        if not isinstance(self.live_enabled, bool):
            raise DerivLiveExecutionError("live_enabled must be boolean")

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "DerivLiveExecutionConfig":
        env = os.environ if environ is None else environ
        return cls(
            account_id=env.get("DERIV_REAL_ACCOUNT_ID", ""),
            authorization_token=env.get("DERIV_PAT", ""),
            app_id=env.get("DERIV_APP_ID", ""),
            live_enabled=env.get("APEX_LIVE_EXECUTION_ENABLED", "").strip().lower() == "true",
        )

    def to_account_config(self) -> DerivLiveAccountConfig:
        return DerivLiveAccountConfig(
            account_id=self.account_id,
            app_id=self.app_id,
            authorization_token=self.authorization_token,
            rest_base_url=self.rest_base_url,
            timeout_seconds=self.timeout_seconds,
        )

    def safe_summary(self) -> dict[str, Any]:
        return {
            "account_id_configured": bool(self.account_id.strip()),
            "app_id_configured": bool(self.app_id.strip()),
            "authorization_token_configured": bool(self.authorization_token.strip()),
            "rest_base_url": self.rest_base_url,
            "timeout_seconds": self.timeout_seconds,
            "live_enabled": self.live_enabled,
            "credentials_exposed": False,
        }


class DerivLiveTransport(Protocol):
    """Replaceable transport boundary for live-adapter tests."""

    def verify_real_session(self, config: DerivLiveExecutionConfig) -> DerivLiveConnectivityResult: ...

    def get_authenticated_websocket_url(self, config: DerivLiveExecutionConfig) -> str: ...

    def request_proposal(self, websocket_url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]: ...

    def buy(self, websocket_url: str, proposal_id: str, price: float, timeout: float) -> Mapping[str, Any]: ...


class DerivLiveWebSocketTransport:
    """Real REST + WebSocket transport for authenticated Deriv live Options."""

    def __init__(self) -> None:
        self._connectivity = DerivLiveAccountConnectivity()

    def verify_real_session(self, config: DerivLiveExecutionConfig) -> DerivLiveConnectivityResult:
        return self._connectivity.verify_read_only(config.to_account_config())

    def get_authenticated_websocket_url(self, config: DerivLiveExecutionConfig) -> str:
        return self._connectivity.get_authenticated_websocket_url(config.to_account_config())

    @staticmethod
    def _call(websocket_url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
        try:
            import websocket
        except ImportError as exc:
            raise DerivLiveExecutionError("websocket-client is required for Deriv live execution") from exc
        if not websocket_url.startswith(REAL_WS_PREFIX + "?"):
            raise DerivLiveExecutionError("refusing a non-real Deriv WebSocket URL")
        ws = None
        try:
            ws = websocket.create_connection(websocket_url, timeout=timeout)
            ws.send(json.dumps(dict(payload), separators=(",", ":")))
            raw = ws.recv()
            if not isinstance(raw, str):
                raise DerivLiveExecutionError("Deriv returned a non-text WebSocket response")
            result = json.loads(raw)
            if not isinstance(result, Mapping):
                raise DerivLiveExecutionError("Deriv response must be a JSON object")
            return result
        except DerivLiveExecutionError:
            raise
        except Exception as exc:
            raise DerivLiveExecutionError(f"Deriv live WebSocket request failed: {exc}") from exc
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    def request_proposal(self, websocket_url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
        return self._call(websocket_url, {"proposal": 1, **dict(payload)}, timeout)

    def buy(self, websocket_url: str, proposal_id: str, price: float, timeout: float) -> Mapping[str, Any]:
        return self._call(websocket_url, {"buy": proposal_id, "price": price}, timeout)


@dataclass(frozen=True)
class DerivLiveExecutionResult:
    status: DerivLiveExecutionStatus
    request_id: str
    gateway_result: ExecutionResult
    outcome: ExecutionOutcome | None = None
    connectivity: DerivLiveConnectivityResult | None = None
    proposal: DerivProposal | None = None
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome is not None and self.outcome.successful

    @property
    def live_execution(self) -> bool:
        return self.outcome is not None and self.outcome.status is ExecutionOutcomeStatus.CONFIRMED

    @property
    def broker_order_id(self) -> str | None:
        return self.outcome.broker_order_id if self.outcome else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.succeeded,
            "status": self.status.value,
            "request_id": self.request_id,
            "live_execution": self.live_execution,
            "broker": "deriv",
            "account_mode": "live",
            "broker_order_id": self.broker_order_id,
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
            "error": self.error,
            "credentials_exposed": False,
            "gateway": self.gateway_result.to_dict(),
            "outcome": self.outcome.to_dict() if self.outcome else None,
            "connectivity": self.connectivity.safe_summary() if self.connectivity else None,
        }


class DerivLiveExecutionAdapter:
    """Place an explicitly specified Deriv live Options contract.

    The adapter is fail-closed.  It requires all of the following before the
    broker ``buy`` call is reachable:

    * LIVE request mode
    * LIVE-capable gateway admission
    * adapter-local live enablement
    * explicit per-call confirmation
    * successful real-account authentication + balance verification
    * real-only WebSocket URL
    * exact TradePlan pair / contract symbol match
    * valid proposal with a positive ask price

    The adapter does not provide sell/cancel/modify operations.
    """

    capability = ExecutionAdapterCapability.LIVE

    def __init__(
        self,
        config: DerivLiveExecutionConfig,
        *,
        transport: DerivLiveTransport | None = None,
        gateway: ExecutionGateway | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or DerivLiveWebSocketTransport()
        self.gateway = gateway or ExecutionGateway(
            policy=ExecutionPolicy(mode=ExecutionMode.LIVE)
        )

    def _blocked(self, request: ExecutionRequest, gateway_result: ExecutionResult, reason: str, *, connectivity=None, error=None) -> DerivLiveExecutionResult:
        return DerivLiveExecutionResult(
            DerivLiveExecutionStatus.BLOCKED,
            request.request_id,
            gateway_result,
            connectivity=connectivity,
            reasons=(reason,),
            error=error,
        )

    def execute(
        self,
        request: ExecutionRequest,
        contract: DerivContractSpec,
        *,
        total_risk_fraction: float | None = None,
        explicit_live_confirmation: bool = False,
    ) -> DerivLiveExecutionResult:
        gateway_result: ExecutionResult | None = None
        connectivity: DerivLiveConnectivityResult | None = None
        try:
            if not isinstance(request, ExecutionRequest):
                raise DerivLiveExecutionError("request must be an ExecutionRequest")
            if request.mode is not ExecutionMode.LIVE:
                raise DerivLiveExecutionError("DerivLiveExecutionAdapter accepts LIVE mode only")
            if not isinstance(contract, DerivContractSpec):
                raise DerivLiveExecutionError("contract must be a DerivContractSpec")
            gateway_result = self.gateway.validate(
                request,
                total_risk_fraction=total_risk_fraction,
                adapter_capability=self.capability,
            )
            if not gateway_result.ready_for_adapter:
                return DerivLiveExecutionResult(
                    DerivLiveExecutionStatus.REJECTED,
                    request.request_id,
                    gateway_result,
                    reasons=gateway_result.reasons,
                )
            if not self.config.live_enabled:
                return self._blocked(request, gateway_result, "adapter live enablement is disabled")
            if not explicit_live_confirmation:
                return self._blocked(request, gateway_result, "explicit per-execution live confirmation is required")
            if contract.underlying_symbol != request.plan.pair:
                return self._blocked(request, gateway_result, "contract symbol must exactly match TradePlan pair")
            if contract.currency.strip() == "":
                return self._blocked(request, gateway_result, "contract currency is required")

            connectivity = self.transport.verify_real_session(self.config)
            if not connectivity.ready_for_read_only:
                return self._blocked(
                    request,
                    gateway_result,
                    "real Deriv account authentication/balance verification failed",
                    connectivity=connectivity,
                )
            if connectivity.account_id != self.config.account_id:
                return self._blocked(request, gateway_result, "verified account identity does not match configured account", connectivity=connectivity)
            if connectivity.currency and connectivity.currency.upper() != contract.currency.upper():
                return self._blocked(request, gateway_result, "contract currency does not match verified account currency", connectivity=connectivity)

            ws_url = self.transport.get_authenticated_websocket_url(self.config)
            if not ws_url.startswith(REAL_WS_PREFIX + "?"):
                raise DerivLiveExecutionError("adapter requires a real-scoped authenticated WebSocket URL")

            proposal_response = self.transport.request_proposal(
                ws_url, contract.to_dict(), self.config.timeout_seconds
            )
            if proposal_response.get("error"):
                message = str((proposal_response.get("error") or {}).get("message", "Deriv proposal error"))
                return DerivLiveExecutionResult(
                    DerivLiveExecutionStatus.FAILED,
                    request.request_id,
                    gateway_result,
                    connectivity=connectivity,
                    reasons=(message,),
                )
            if proposal_response.get("msg_type") not in (None, "proposal"):
                return DerivLiveExecutionResult(
                    DerivLiveExecutionStatus.FAILED,
                    request.request_id,
                    gateway_result,
                    connectivity=connectivity,
                    reasons=("unexpected Deriv proposal response type",),
                )
            proposal_data = proposal_response.get("proposal")
            if not isinstance(proposal_data, Mapping):
                raise DerivLiveExecutionError("Deriv proposal response did not contain a proposal object")
            proposal_id = proposal_data.get("id")
            if not isinstance(proposal_id, str) or not proposal_id.strip():
                raise DerivLiveExecutionError("Deriv proposal response did not contain a proposal id")
            ask_price_raw = proposal_data.get("ask_price")
            if isinstance(ask_price_raw, bool) or not isinstance(ask_price_raw, (int, float)) or float(ask_price_raw) <= 0:
                raise DerivLiveExecutionError("Deriv proposal did not provide a positive ask price")
            proposal = DerivProposal(
                proposal_id=proposal_id,
                ask_price=float(ask_price_raw),
                payout=float(proposal_data["payout"]) if proposal_data.get("payout") is not None else None,
                spot=float(proposal_data["spot"]) if proposal_data.get("spot") is not None else None,
                raw=dict(proposal_data),
            )

            # The buy call is intentionally the last network operation and is
            # unreachable without the explicit confirmation above.
            buy_response = self.transport.buy(
                ws_url, proposal.proposal_id, proposal.ask_price, self.config.timeout_seconds
            )
            if buy_response.get("error"):
                message = str((buy_response.get("error") or {}).get("message", "Deriv buy error"))
                outcome = ExecutionOutcome(
                    request_id=request.request_id,
                    mode=ExecutionMode.LIVE,
                    status=ExecutionOutcomeStatus.FAILED,
                    broker="deriv",
                    account_scope=self.config.account_id,
                    message=message,
                    metadata={"account_mode": "live"},
                )
                return DerivLiveExecutionResult(
                    DerivLiveExecutionStatus.FAILED,
                    request.request_id,
                    gateway_result,
                    outcome=validate_execution_outcome(request, outcome),
                    connectivity=connectivity,
                    proposal=proposal,
                    reasons=(message,),
                )

            if buy_response.get("msg_type") not in (None, "buy"):
                raise DerivLiveExecutionError("unexpected Deriv buy response type")
            buy_data = buy_response.get("buy")
            if not isinstance(buy_data, Mapping):
                raise DerivLiveExecutionError("Deriv buy response did not contain a buy object")
            contract_id = buy_data.get("contract_id")
            buy_price_raw = buy_data.get("buy_price", proposal.ask_price)
            if contract_id is None or str(contract_id).strip() == "":
                raise DerivLiveExecutionError("Deriv buy response did not contain contract_id")
            if isinstance(buy_price_raw, bool) or not isinstance(buy_price_raw, (int, float)) or float(buy_price_raw) <= 0:
                raise DerivLiveExecutionError("Deriv buy response did not contain a positive buy_price")

            outcome = ExecutionOutcome(
                request_id=request.request_id,
                mode=ExecutionMode.LIVE,
                status=ExecutionOutcomeStatus.CONFIRMED,
                broker="deriv",
                account_scope=self.config.account_id,
                broker_order_id=str(contract_id),
                execution_price=float(buy_price_raw),
                executed_quantity=float(contract.amount),
                message="Deriv authenticated buy response confirmed contract purchase; broker reconciliation remains required",
                metadata={
                    "account_mode": "live",
                    "transaction_id": buy_data.get("transaction_id"),
                    "proposal_id": proposal.proposal_id,
                    "post_fill_reconciliation_required": True,
                },
            )
            outcome = validate_execution_outcome(request, outcome)
            return DerivLiveExecutionResult(
                DerivLiveExecutionStatus.CONFIRMED,
                request.request_id,
                gateway_result,
                outcome=outcome,
                connectivity=connectivity,
                proposal=proposal,
                metadata={"account_mode": "live", "broker": "deriv", "post_fill_reconciliation_required": True},
            )
        except DerivLiveExecutionError as exc:
            fallback = gateway_result or ExecutionResult(
                status=ExecutionStatus.INVALID_INPUT,
                request_id=getattr(request, "request_id", "INVALID"),
                mode=getattr(request, "mode", ExecutionMode.LIVE),
                request_fingerprint=None,
                error=str(exc),
            )
            return DerivLiveExecutionResult(
                DerivLiveExecutionStatus.UNKNOWN,
                getattr(request, "request_id", "INVALID"),
                fallback,
                connectivity=connectivity,
                error=str(exc),
            )
        except Exception as exc:
            fallback = gateway_result or ExecutionResult(
                status=ExecutionStatus.INVALID_INPUT,
                request_id=getattr(request, "request_id", "INVALID"),
                mode=getattr(request, "mode", ExecutionMode.LIVE),
                request_fingerprint=None,
                error=str(exc),
            )
            return DerivLiveExecutionResult(
                DerivLiveExecutionStatus.UNKNOWN,
                getattr(request, "request_id", "INVALID"),
                fallback,
                connectivity=connectivity,
                error=str(exc),
            )


def execute_deriv_live(
    request: ExecutionRequest,
    contract: DerivContractSpec,
    config: DerivLiveExecutionConfig,
    *,
    gateway: ExecutionGateway | None = None,
    transport: DerivLiveTransport | None = None,
    total_risk_fraction: float | None = None,
    explicit_live_confirmation: bool = False,
) -> DerivLiveExecutionResult:
    """Functional wrapper for explicit Deriv live execution."""
    return DerivLiveExecutionAdapter(config, transport=transport, gateway=gateway).execute(
        request,
        contract,
        total_risk_fraction=total_risk_fraction,
        explicit_live_confirmation=explicit_live_confirmation,
    )
