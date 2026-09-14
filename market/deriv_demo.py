"""APEX / BENVIN Phase 2.23 - Deriv Demo Execution Adapter.

This module is the first broker-specific execution adapter, but it is strictly
restricted to Deriv demo accounts.  It sits behind the provider-neutral
Execution Gateway from Phase 2.22.

The adapter does not support real-account URLs, live execution, or implicit
TradePlan-to-contract conversion.  A caller must provide an explicit
DerivContractSpec describing the Deriv contract to request.  This prevents
APEX's spot-FX-style risk plan from being silently translated into a different
Deriv contract type.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import os
from typing import Any, Mapping, Protocol
from urllib import request as urllib_request

from .execution import (
    ExecutionAdapterCapability,
    ExecutionGateway,
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)


class DerivDemoError(ValueError):
    """Raised for invalid Deriv demo adapter input."""


class DerivDemoStatus(str, Enum):
    REJECTED = "REJECTED"
    PROPOSAL_REQUESTED = "PROPOSAL_REQUESTED"
    CONTRACT_PURCHASED = "CONTRACT_PURCHASED"
    API_ERROR = "API_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class DerivDemoConfig:
    """Connection configuration for a Deriv Options demo account."""

    account_id: str
    authorization_token: str
    app_id: str | None = None
    rest_base_url: str = "https://api.derivws.com"
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, str) or not self.account_id.strip():
            raise DerivDemoError("account_id must be non-empty")
        if not isinstance(self.authorization_token, str) or not self.authorization_token.strip():
            raise DerivDemoError("authorization_token must be non-empty")
        if not isinstance(self.rest_base_url, str) or not self.rest_base_url.startswith("https://"):
            raise DerivDemoError("rest_base_url must use HTTPS")
        if self.timeout_seconds <= 0:
            raise DerivDemoError("timeout_seconds must be positive")

    @classmethod
    def from_environment(cls, *, account_var: str = "DERIV_DEMO_ACCOUNT_ID",
                         token_var: str = "DERIV_AUTH_TOKEN",
                         app_id_var: str = "DERIV_APP_ID") -> "DerivDemoConfig":
        account = os.getenv(account_var)
        token = os.getenv(token_var)
        app_id = os.getenv(app_id_var)
        if not account or not token:
            raise DerivDemoError("Deriv demo credentials are not configured in the environment")
        return cls(account_id=account, authorization_token=token, app_id=app_id)


@dataclass(frozen=True)
class DerivContractSpec:
    """Explicit Deriv contract parameters; no implicit strategy translation."""

    underlying_symbol: str
    contract_type: str
    amount: float
    basis: str
    currency: str
    duration: int
    duration_unit: str
    extra_parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("underlying_symbol", "contract_type", "basis", "currency", "duration_unit"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DerivDemoError(f"{name} must be non-empty")
        if self.amount <= 0:
            raise DerivDemoError("amount must be positive")
        if self.duration <= 0:
            raise DerivDemoError("duration must be positive")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "underlying_symbol": self.underlying_symbol,
            "contract_type": self.contract_type,
            "amount": self.amount,
            "basis": self.basis,
            "currency": self.currency,
            "duration": self.duration,
            "duration_unit": self.duration_unit,
        }
        result.update(self.extra_parameters)
        return result


@dataclass(frozen=True)
class DerivProposal:
    proposal_id: str
    ask_price: float | None = None
    payout: float | None = None
    spot: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DerivDemoExecutionResult:
    status: DerivDemoStatus
    request_id: str
    gateway_result: ExecutionResult
    proposal: DerivProposal | None = None
    contract_id: str | None = None
    buy_price: float | None = None
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is DerivDemoStatus.CONTRACT_PURCHASED and self.contract_id is not None

    @property
    def live_execution(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.succeeded,
            "status": self.status.value,
            "request_id": self.request_id,
            "contract_id": self.contract_id,
            "buy_price": self.buy_price,
            "live_execution": False,
            "broker": "deriv",
            "account_mode": "demo",
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
            "error": self.error,
            "gateway": self.gateway_result.to_dict(),
        }


class DerivTransport(Protocol):
    """Minimal transport protocol so all network I/O is replaceable in tests."""

    def get_authenticated_websocket_url(self, config: DerivDemoConfig) -> str: ...

    def request_proposal(self, websocket_url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]: ...

    def buy(self, websocket_url: str, proposal_id: str, price: float, timeout: float) -> Mapping[str, Any]: ...


class DerivWebSocketTransport:
    """Real Deriv REST+WebSocket transport for demo Options accounts."""

    def get_authenticated_websocket_url(self, config: DerivDemoConfig) -> str:
        url = config.rest_base_url.rstrip("/") + f"/trading/v1/options/accounts/{config.account_id}/otp"
        headers = {"Authorization": f"Bearer {config.authorization_token}"}
        if config.app_id:
            headers["Deriv-App-ID"] = config.app_id
        req = urllib_request.Request(url, method="POST", headers=headers)
        try:
            with urllib_request.urlopen(req, timeout=config.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise DerivDemoError(f"failed to obtain Deriv demo WebSocket URL: {exc}") from exc
        ws_url = ((body.get("data") or {}).get("url"))
        if not isinstance(ws_url, str) or not ws_url.startswith("wss://"):
            raise DerivDemoError("Deriv OTP response did not contain a secure WebSocket URL")
        if "/ws/real" in ws_url:
            raise DerivDemoError("refusing a real-account WebSocket URL")
        if "/ws/demo" not in ws_url:
            raise DerivDemoError("Deriv authenticated WebSocket URL is not demo-scoped")
        return ws_url

    @staticmethod
    def _call(websocket_url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
        try:
            import websocket
        except ImportError as exc:
            raise DerivDemoError("websocket-client is required for Deriv demo execution") from exc
        ws = None
        try:
            ws = websocket.create_connection(websocket_url, timeout=timeout)
            ws.send(json.dumps(dict(payload), separators=(",", ":")))
            raw = ws.recv()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise DerivDemoError("Deriv response must be a JSON object")
            return data
        except Exception as exc:
            if isinstance(exc, DerivDemoError):
                raise
            raise DerivDemoError(f"Deriv WebSocket request failed: {exc}") from exc
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


class DerivDemoExecutionAdapter:
    """Execute explicitly specified Deriv Options contracts on demo only."""

    capability = ExecutionAdapterCapability.DEMO

    def __init__(self, config: DerivDemoConfig, *, transport: DerivTransport | None = None,
                 gateway: ExecutionGateway | None = None) -> None:
        self.config = config
        self.transport = transport or DerivWebSocketTransport()
        self.gateway = gateway or ExecutionGateway()

    def execute(self, request: ExecutionRequest, contract: DerivContractSpec,
                *, total_risk_fraction: float | None = None) -> DerivDemoExecutionResult:
        try:
            if not isinstance(request, ExecutionRequest):
                raise DerivDemoError("request must be an ExecutionRequest")
            if request.mode is not ExecutionMode.DEMO:
                raise DerivDemoError("DerivDemoExecutionAdapter accepts DEMO mode only")
            gateway_result = self.gateway.validate(
                request,
                total_risk_fraction=total_risk_fraction,
                adapter_capability=self.capability,
            )
            if not gateway_result.ready_for_adapter:
                return DerivDemoExecutionResult(
                    DerivDemoStatus.REJECTED, request.request_id, gateway_result,
                    reasons=gateway_result.reasons,
                )
            if contract.underlying_symbol != request.plan.pair:
                return DerivDemoExecutionResult(
                    DerivDemoStatus.REJECTED, request.request_id, gateway_result,
                    reasons=("contract symbol must exactly match TradePlan pair",),
                )
            ws_url = self.transport.get_authenticated_websocket_url(self.config)
            if "/ws/real" in ws_url or "/ws/demo" not in ws_url:
                raise DerivDemoError("adapter requires a demo-scoped WebSocket URL")
            proposal_response = self.transport.request_proposal(
                ws_url, contract.to_dict(), self.config.timeout_seconds
            )
            if proposal_response.get("error"):
                return DerivDemoExecutionResult(
                    DerivDemoStatus.API_ERROR, request.request_id, gateway_result,
                    reasons=(str((proposal_response.get("error") or {}).get("message", "Deriv proposal error")),),
                )
            proposal_data = proposal_response.get("proposal") or {}
            proposal_id = proposal_data.get("id")
            if not isinstance(proposal_id, str) or not proposal_id:
                raise DerivDemoError("Deriv proposal response did not contain an id")
            ask_price = proposal_data.get("ask_price")
            proposal = DerivProposal(
                proposal_id=proposal_id,
                ask_price=float(ask_price) if ask_price is not None else None,
                payout=float(proposal_data["payout"]) if proposal_data.get("payout") is not None else None,
                spot=float(proposal_data["spot"]) if proposal_data.get("spot") is not None else None,
                raw=dict(proposal_data),
            )
            if proposal.ask_price is None or proposal.ask_price <= 0:
                raise DerivDemoError("Deriv proposal did not provide a positive ask price")
            buy_response = self.transport.buy(ws_url, proposal_id, proposal.ask_price, self.config.timeout_seconds)
            if buy_response.get("error"):
                return DerivDemoExecutionResult(
                    DerivDemoStatus.API_ERROR, request.request_id, gateway_result, proposal=proposal,
                    reasons=(str((buy_response.get("error") or {}).get("message", "Deriv buy error")),),
                )
            buy_data = buy_response.get("buy") or {}
            contract_id = buy_data.get("contract_id")
            if contract_id is None:
                raise DerivDemoError("Deriv buy response did not contain contract_id")
            return DerivDemoExecutionResult(
                DerivDemoStatus.CONTRACT_PURCHASED,
                request.request_id,
                gateway_result,
                proposal=proposal,
                contract_id=str(contract_id),
                buy_price=float(buy_data.get("buy_price", proposal.ask_price)),
                metadata={"account_mode": "demo", "broker": "deriv", "live_execution": False},
            )
        except DerivDemoError as exc:
            return DerivDemoExecutionResult(
                DerivDemoStatus.INVALID_INPUT, request.request_id,
                locals().get("gateway_result") or ExecutionResult(
                    status=ExecutionStatus.INVALID_INPUT,
                    request_id=request.request_id,
                    mode=request.mode,
                    request_fingerprint=None,
                    error=str(exc),
                ),
                error=str(exc),
            )
        except Exception as exc:
            return DerivDemoExecutionResult(
                DerivDemoStatus.API_ERROR, request.request_id,
                locals().get("gateway_result") or self.gateway.validate(
                    request, adapter_capability=self.capability
                ),
                error=str(exc),
            )


def execute_deriv_demo(
    request: ExecutionRequest,
    contract: DerivContractSpec,
    config: DerivDemoConfig,
    *,
    gateway: ExecutionGateway | None = None,
    transport: DerivTransport | None = None,
    total_risk_fraction: float | None = None,
) -> DerivDemoExecutionResult:
    """Functional wrapper for explicit Deriv demo execution."""
    return DerivDemoExecutionAdapter(config, transport=transport, gateway=gateway).execute(
        request, contract, total_risk_fraction=total_risk_fraction
    )
