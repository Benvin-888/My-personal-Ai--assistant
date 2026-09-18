"""APEX / BENVIN Phase 2.38 - Deriv live broker reconciliation.

Read-only post-execution verification for the real Deriv account.  This module
never buys, sells, modifies, cancels, or retries an order.  It verifies that a
Phase 2.37 broker contract really exists in the configured real account and
that the broker-reported contract identity is consistent with the approved
execution outcome and explicit Deriv contract specification.

A Phase 2.37 ``CONFIRMED`` response is therefore not treated as the final
truth.  Only a successful broker-side reconciliation is considered verified.
Unknown or mismatched broker state is fail-closed and must not be converted
into a successful position state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import json
from typing import Any, Mapping, Protocol

from .broker_state import (
    BrokerContractState,
    BrokerPositionStore,
    PositionLifecycle,
    ReconciliationStatus,
    ReconciliationResult,
)
from .deriv_demo import DerivContractSpec
from .deriv_live_execution import DerivLiveExecutionConfig
from .execution import ExecutionMode, ExecutionRequest
from .execution_outcome import ExecutionOutcome, ExecutionOutcomeStatus, validate_execution_outcome
from .deriv_live_account import REAL_WS_PREFIX


class DerivLiveReconciliationError(ValueError):
    """Raised for invalid live-reconciliation input."""


@dataclass(frozen=True)
class DerivLiveReconciliationResult:
    """Strict result of read-only broker-side live reconciliation."""

    status: ReconciliationStatus
    request_id: str
    contract_id: str
    broker: str = "deriv"
    account_mode: str = "live"
    broker_state: BrokerContractState | None = None
    execution_outcome: ExecutionOutcome | None = None
    expected: dict[str, Any] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return self.status is ReconciliationStatus.MATCHED and self.broker_state is not None

    @property
    def safe_for_position_state(self) -> bool:
        return self.verified and self.broker_state is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "request_id": self.request_id,
            "contract_id": self.contract_id,
            "broker": self.broker,
            "account_mode": self.account_mode,
            "verified": self.verified,
            "safe_for_position_state": self.safe_for_position_state,
            "broker_state": self.broker_state.to_dict() if self.broker_state else None,
            "execution_outcome": self.execution_outcome.to_dict() if self.execution_outcome else None,
            "expected": dict(self.expected),
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
            "credentials_exposed": False,
        }


class DerivLiveReconciliationTransport(Protocol):
    def get_authenticated_websocket_url(self, config: DerivLiveExecutionConfig) -> str: ...
    def request(self, websocket_url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]: ...


class DerivLiveReadOnlyWebSocketTransport:
    """Real authenticated Deriv transport exposing reconciliation reads only."""

    def __init__(self) -> None:
        self._connectivity = None

    def get_authenticated_websocket_url(self, config: DerivLiveExecutionConfig) -> str:
        from .deriv_live_account import DerivLiveAccountConnectivity
        self._connectivity = self._connectivity or DerivLiveAccountConnectivity()
        return self._connectivity.get_authenticated_websocket_url(config.to_account_config())

    def request(self, websocket_url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
        try:
            import websocket
        except ImportError as exc:
            raise DerivLiveReconciliationError("websocket-client is required for Deriv live reconciliation") from exc
        if not isinstance(websocket_url, str) or not websocket_url.startswith(REAL_WS_PREFIX + "?"):
            raise DerivLiveReconciliationError("refusing a non-real Deriv WebSocket URL")
        if not isinstance(payload, Mapping) or set(payload) - {"proposal_open_contract" , "contract_id", "subscribe"}:
            raise DerivLiveReconciliationError("reconciliation transport accepts read-only contract-state fields only")
        if payload.get("proposal_open_contract") != 1:
            raise DerivLiveReconciliationError("reconciliation transport requires proposal_open_contract=1")
        ws = None
        try:
            ws = websocket.create_connection(websocket_url, timeout=timeout)
            ws.send(json.dumps(dict(payload), separators=(",", ":")))
            raw = ws.recv()
            if not isinstance(raw, str):
                raise DerivLiveReconciliationError("Deriv returned a non-text WebSocket response")
            response = json.loads(raw)
            if not isinstance(response, Mapping):
                raise DerivLiveReconciliationError("Deriv response must be a JSON object")
            return response
        except DerivLiveReconciliationError:
            raise
        except Exception as exc:
            raise DerivLiveReconciliationError(f"Deriv reconciliation request failed: {exc}") from exc
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass


class DerivLiveReconciliationTransportAdapter:
    """Adapt the Phase 2.37 transport shape without adding execution methods."""

    def __init__(self, transport: Any) -> None:
        self._transport = transport

    def get_authenticated_websocket_url(self, config: DerivLiveExecutionConfig) -> str:
        return self._transport.get_authenticated_websocket_url(config)

    def request(self, websocket_url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
        # Phase 2.37's live transport exposes only proposal/buy.  This adapter is
        # intentionally separate so reconciliation can use a read-only request
        # method supplied by the caller; no buy/sell/cancel method is introduced.
        request_method = getattr(self._transport, "request", None)
        if not callable(request_method):
            raise DerivLiveReconciliationError("reconciliation transport must expose read-only request()")
        return request_method(websocket_url, payload, timeout)


class DerivLiveReconciler:
    """Read-only verifier for a real Deriv contract returned by ``buy``."""

    broker = "deriv"
    account_mode = "live"

    def __init__(
        self,
        config: DerivLiveExecutionConfig,
        *,
        transport: DerivLiveReconciliationTransport,
        store: BrokerPositionStore | None = None,
    ) -> None:
        if not isinstance(config, DerivLiveExecutionConfig):
            raise DerivLiveReconciliationError("config must be DerivLiveExecutionConfig")
        self.config = config
        self.transport = transport
        self.store = store or BrokerPositionStore()

    def reconcile(
        self,
        request: ExecutionRequest,
        outcome: ExecutionOutcome,
        expected: DerivContractSpec,
    ) -> DerivLiveReconciliationResult:
        """Verify broker state for one previously confirmed live execution.

        This method accepts only a Phase 2.37 ``CONFIRMED`` outcome.  It then
        obtains a fresh authenticated real WebSocket URL and performs only a
        ``proposal_open_contract`` read.  No mutation operation is present in
        this reconciliation path.
        """
        try:
            validate_execution_outcome(request, outcome)
            self._validate_inputs(request, outcome, expected)
        except (TypeError, ValueError, DerivLiveReconciliationError) as exc:
            return self._invalid_result(request, outcome, expected, str(exc))

        try:
            websocket_url = self.transport.get_authenticated_websocket_url(self.config)
            if not isinstance(websocket_url, str) or not websocket_url.startswith(REAL_WS_PREFIX + "?"):
                return self._unknown(request, outcome, expected, "authenticated WebSocket URL is not real-scoped")

            response = self.transport.request(
                websocket_url,
                {"proposal_open_contract": 1, "contract_id": int(outcome.broker_order_id)},
                self.config.timeout_seconds,
            )
            if not isinstance(response, Mapping):
                return self._unknown(request, outcome, expected, "Deriv reconciliation response must be a mapping")
            if response.get("error"):
                error = response.get("error")
                message = str(error.get("message", "Deriv reconciliation error")) if isinstance(error, Mapping) else "Deriv reconciliation error"
                return self._unknown(request, outcome, expected, message)
            if response.get("msg_type") != "proposal_open_contract":
                return self._unknown(request, outcome, expected, "unexpected Deriv reconciliation response type")

            payload = response.get("proposal_open_contract")
            if not isinstance(payload, Mapping):
                return self._unknown(request, outcome, expected, "broker did not return proposal_open_contract")

            state = self._parse_state(payload)
            mismatches = self._compare(state, outcome, expected)
            if mismatches:
                return DerivLiveReconciliationResult(
                    ReconciliationStatus.MISMATCH,
                    request.request_id,
                    outcome.broker_order_id,
                    broker_state=state,
                    execution_outcome=outcome,
                    expected=self._expected_dict(expected, outcome),
                    reasons=tuple(mismatches),
                    metadata={"broker_state_read_only": True},
                )

            result = DerivLiveReconciliationResult(
                ReconciliationStatus.MATCHED,
                request.request_id,
                outcome.broker_order_id,
                broker_state=state,
                execution_outcome=outcome,
                expected=self._expected_dict(expected, outcome),
                metadata={
                    "broker_state_read_only": True,
                    "post_fill_reconciled": True,
                    "account_scope_verified": True,
                },
            )
            self.store.apply(ReconciliationResult(
                ReconciliationStatus.MATCHED,
                outcome.broker_order_id,
                state=state,
                expected=result.expected,
            ))
            return result
        except Exception as exc:
            return self._unknown(request, outcome, expected, f"reconciliation failed: {exc}")

    def _validate_inputs(self, request: ExecutionRequest, outcome: ExecutionOutcome, expected: DerivContractSpec) -> None:
        if not isinstance(request, ExecutionRequest):
            raise DerivLiveReconciliationError("request must be an ExecutionRequest")
        if not isinstance(outcome, ExecutionOutcome):
            raise DerivLiveReconciliationError("outcome must be an ExecutionOutcome")
        if request.mode is not ExecutionMode.LIVE:
            raise DerivLiveReconciliationError("reconciliation accepts LIVE requests only")
        if outcome.status is not ExecutionOutcomeStatus.CONFIRMED:
            raise DerivLiveReconciliationError("only CONFIRMED execution outcomes may be reconciled")
        if outcome.broker.lower() != "deriv":
            raise DerivLiveReconciliationError("execution outcome broker must be deriv")
        if outcome.account_scope != self.config.account_id:
            raise DerivLiveReconciliationError("execution outcome account scope does not match configured account")
        if not outcome.broker_order_id or not str(outcome.broker_order_id).isdigit():
            raise DerivLiveReconciliationError("Deriv contract id must be numeric")
        if not isinstance(expected, DerivContractSpec):
            raise DerivLiveReconciliationError("expected must be a DerivContractSpec")
        if expected.underlying_symbol != request.plan.pair:
            raise DerivLiveReconciliationError("expected contract symbol must match TradePlan pair")
        if not expected.currency.strip():
            raise DerivLiveReconciliationError("expected contract currency is required")

    @staticmethod
    def _parse_state(payload: Mapping[str, Any]) -> BrokerContractState:
        contract_id = str(payload.get("contract_id", "")).strip()
        if not contract_id or not contract_id.isdigit():
            raise DerivLiveReconciliationError("broker contract_id is missing or invalid")
        contract_type = _optional_text(payload.get("contract_type"))
        symbol = _optional_text(payload.get("underlying_symbol") or payload.get("symbol"))
        currency = _optional_text(payload.get("currency"))
        buy_price = _optional_number(payload.get("buy_price"), "buy_price")
        payout = _optional_number(payload.get("payout"), "payout")
        sold_raw = payload.get("is_sold")
        if sold_raw is not None and not isinstance(sold_raw, (bool, int)):
            raise DerivLiveReconciliationError("is_sold must be boolean-like")
        sold = bool(sold_raw) if sold_raw is not None else None
        lifecycle = PositionLifecycle.CLOSED if sold is True else PositionLifecycle.OPEN if sold is False else PositionLifecycle.UNKNOWN
        return BrokerContractState(
            broker="deriv",
            account_mode="live",
            contract_id=contract_id,
            contract_type=contract_type,
            symbol=symbol,
            currency=currency,
            buy_price=buy_price,
            payout=payout,
            is_sold=sold,
            lifecycle=lifecycle,
            observed_at=datetime.now(timezone.utc).isoformat(),
            raw=dict(payload),
        )

    @staticmethod
    def _compare(state: BrokerContractState, outcome: ExecutionOutcome, expected: DerivContractSpec) -> list[str]:
        reasons: list[str] = []
        if state.contract_id != str(outcome.broker_order_id):
            reasons.append("broker contract_id does not match execution outcome")
        if state.contract_type is None or state.contract_type.upper() != expected.contract_type.upper():
            reasons.append("contract_type mismatch or missing")
        if state.symbol is not None and state.symbol.upper() != expected.underlying_symbol.upper():
            reasons.append("underlying_symbol mismatch")
        if state.currency is None or state.currency.upper() != expected.currency.upper():
            reasons.append("currency mismatch or missing")
        if state.buy_price is None:
            reasons.append("broker buy_price is missing")
        elif outcome.execution_price is None or not math.isclose(state.buy_price, outcome.execution_price, rel_tol=1e-9, abs_tol=1e-9):
            reasons.append("broker buy_price does not match execution outcome price")
        return reasons

    def _invalid_result(self, request: Any, outcome: Any, expected: Any, reason: str) -> DerivLiveReconciliationResult:
        return DerivLiveReconciliationResult(
            ReconciliationStatus.INVALID_INPUT,
            getattr(request, "request_id", "INVALID"),
            str(getattr(outcome, "broker_order_id", "")),
            execution_outcome=outcome if isinstance(outcome, ExecutionOutcome) else None,
            expected=self._expected_dict(expected, outcome),
            reasons=(reason,),
        )

    def _unknown(self, request: ExecutionRequest, outcome: ExecutionOutcome, expected: DerivContractSpec, reason: str) -> DerivLiveReconciliationResult:
        return DerivLiveReconciliationResult(
            ReconciliationStatus.UNKNOWN,
            request.request_id,
            str(outcome.broker_order_id),
            execution_outcome=outcome,
            expected=self._expected_dict(expected, outcome),
            reasons=(reason,),
            metadata={"safe_to_assume_success": False},
        )

    @staticmethod
    def _expected_dict(expected: Any, outcome: Any) -> dict[str, Any]:
        if not isinstance(expected, DerivContractSpec):
            return {}
        return {
            "underlying_symbol": expected.underlying_symbol,
            "contract_type": expected.contract_type,
            "currency": expected.currency,
            "broker_order_id": getattr(outcome, "broker_order_id", None),
            "execution_price": getattr(outcome, "execution_price", None),
            "account_scope": getattr(outcome, "account_scope", None),
        }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _optional_number(value: Any, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise DerivLiveReconciliationError(f"{name} must be numeric")
    if isinstance(value, str):
        if not value.strip():
            raise DerivLiveReconciliationError(f"{name} must be numeric")
        try:
            result = float(value)
        except ValueError as exc:
            raise DerivLiveReconciliationError(f"{name} must be numeric") from exc
    elif isinstance(value, (int, float)):
        result = float(value)
    else:
        raise DerivLiveReconciliationError(f"{name} must be numeric")
    if not math.isfinite(result) or result < 0:
        raise DerivLiveReconciliationError(f"{name} must be finite and non-negative")
    return result
