"""APEX / BENVIN Phase 2.24 - Controlled Deriv Demo Connectivity.

This phase verifies the broker-facing boundary without enabling autonomous
trading. It provides demo-only connectivity, active-symbol discovery,
contracts-for validation, proposal validation, and an explicitly opt-in demo
purchase operation. No live-account URL is accepted and no purchase is
performed unless the caller explicitly supplies ``confirm_purchase=True``.

The module is deliberately transport-injected so all tests remain offline and
deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import os
from typing import Any, Mapping, Protocol
from urllib import request as urllib_request

from .deriv_demo import DerivContractSpec, DerivDemoConfig, DerivDemoError


class DerivDemoControlError(ValueError):
    """Raised for invalid controlled-demo input."""


class DemoControlStatus(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    SYMBOLS_VALIDATED = "SYMBOLS_VALIDATED"
    CONTRACTS_VALIDATED = "CONTRACTS_VALIDATED"
    PROPOSAL_VALIDATED = "PROPOSAL_VALIDATED"
    PURCHASED = "PURCHASED"
    REJECTED = "REJECTED"
    API_ERROR = "API_ERROR"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class DemoControlPolicy:
    """Safety policy for controlled demo verification."""

    require_demo_url: bool = True
    require_symbol_validation: bool = True
    require_contract_validation: bool = True
    allow_purchase: bool = True
    require_explicit_purchase_confirmation: bool = True
    maximum_purchase_price: float = 100.0

    def __post_init__(self) -> None:
        if self.maximum_purchase_price <= 0:
            raise DerivDemoControlError("maximum_purchase_price must be positive")


@dataclass(frozen=True)
class DerivActiveSymbol:
    underlying_symbol: str
    market: str | None = None
    underlying_symbol_name: str | None = None
    underlying_symbol_type: str | None = None
    exchange_is_open: bool | None = None
    is_trading_suspended: bool | None = None
    pip_size: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DerivContractAvailability:
    underlying_symbol: str
    contract_types: tuple[str, ...]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DerivDemoControlResult:
    status: DemoControlStatus
    account_mode: str = "demo"
    websocket_url_scoped_demo: bool = False
    symbols: tuple[DerivActiveSymbol, ...] = ()
    contracts: DerivContractAvailability | None = None
    proposal_id: str | None = None
    ask_price: float | None = None
    contract_id: str | None = None
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def connected(self) -> bool:
        return self.status in {
            DemoControlStatus.CONNECTED,
            DemoControlStatus.SYMBOLS_VALIDATED,
            DemoControlStatus.CONTRACTS_VALIDATED,
            DemoControlStatus.PROPOSAL_VALIDATED,
            DemoControlStatus.PURCHASED,
        }

    @property
    def purchase_performed(self) -> bool:
        return self.status is DemoControlStatus.PURCHASED and self.contract_id is not None

    @property
    def live_execution(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "account_mode": "demo",
            "websocket_url_scoped_demo": self.websocket_url_scoped_demo,
            "connected": self.connected,
            "purchase_performed": self.purchase_performed,
            "live_execution": False,
            "symbols": [s.__dict__ for s in self.symbols],
            "contracts": self.contracts.__dict__ if self.contracts else None,
            "proposal_id": self.proposal_id,
            "ask_price": self.ask_price,
            "contract_id": self.contract_id,
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
            "error": self.error,
        }


class DerivDemoControlTransport(Protocol):
    def get_authenticated_websocket_url(self, config: DerivDemoConfig) -> str: ...
    def request(self, websocket_url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]: ...
    def close(self) -> None: ...


class DerivDemoControlWebSocketTransport:
    """Real REST OTP + WebSocket transport for controlled demo verification."""

    def __init__(self) -> None:
        self._sockets: list[Any] = []

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
            raise DerivDemoControlError(f"failed to obtain Deriv demo WebSocket URL: {exc}") from exc
        ws_url = ((body.get("data") or {}).get("url"))
        if not isinstance(ws_url, str) or not ws_url.startswith("wss://"):
            raise DerivDemoControlError("OTP response did not contain a secure WebSocket URL")
        if "/ws/real" in ws_url:
            raise DerivDemoControlError("refusing a real-account WebSocket URL")
        if "/ws/demo" not in ws_url:
            raise DerivDemoControlError("authenticated WebSocket URL is not demo-scoped")
        return ws_url

    def request(self, websocket_url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
        try:
            import websocket
        except ImportError as exc:
            raise DerivDemoControlError("websocket-client is required") from exc
        ws = None
        try:
            ws = websocket.create_connection(websocket_url, timeout=timeout)
            ws.send(json.dumps(dict(payload), separators=(",", ":")))
            data = json.loads(ws.recv())
            if not isinstance(data, dict):
                raise DerivDemoControlError("Deriv response must be a JSON object")
            return data
        except DerivDemoControlError:
            raise
        except Exception as exc:
            raise DerivDemoControlError(f"Deriv WebSocket request failed: {exc}") from exc
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    def close(self) -> None:
        self._sockets.clear()


class DerivDemoControlSession:
    """Controlled demo verifier; purchase is always an explicit separate action."""

    def __init__(self, config: DerivDemoConfig, *, policy: DemoControlPolicy | None = None,
                 transport: DerivDemoControlTransport | None = None) -> None:
        self.config = config
        self.policy = policy or DemoControlPolicy()
        self.transport = transport or DerivDemoControlWebSocketTransport()
        self.websocket_url: str | None = None

    def connect(self) -> DerivDemoControlResult:
        try:
            url = self.transport.get_authenticated_websocket_url(self.config)
            if self.policy.require_demo_url and ("/ws/demo" not in url or "/ws/real" in url):
                return DerivDemoControlResult(
                    DemoControlStatus.REJECTED,
                    reasons=("authenticated URL is not demo-scoped",),
                )
            self.websocket_url = url
            return DerivDemoControlResult(
                DemoControlStatus.CONNECTED,
                websocket_url_scoped_demo=True,
                metadata={"broker": "deriv", "account_mode": "demo"},
            )
        except (DerivDemoControlError, DerivDemoError) as exc:
            return DerivDemoControlResult(DemoControlStatus.API_ERROR, error=str(exc))

    def active_symbols(self) -> DerivDemoControlResult:
        if not self.websocket_url:
            return DerivDemoControlResult(DemoControlStatus.REJECTED, reasons=("demo session is not connected",))
        try:
            response = self.transport.request(self.websocket_url, {"active_symbols": "brief"}, self.config.timeout_seconds)
            if response.get("error"):
                return DerivDemoControlResult(DemoControlStatus.API_ERROR, websocket_url_scoped_demo=True,
                                              error=str((response.get("error") or {}).get("message", "Deriv error")))
            rows = response.get("active_symbols")
            if not isinstance(rows, list):
                raise DerivDemoControlError("active_symbols response did not contain a list")
            parsed = tuple(self._parse_symbol(row) for row in rows if isinstance(row, Mapping))
            if not parsed:
                raise DerivDemoControlError("no active symbols were returned")
            return DerivDemoControlResult(DemoControlStatus.SYMBOLS_VALIDATED,
                                          websocket_url_scoped_demo=True, symbols=parsed)
        except Exception as exc:
            return DerivDemoControlResult(DemoControlStatus.API_ERROR, websocket_url_scoped_demo=True, error=str(exc))

    def validate_symbol(self, symbol: str) -> DerivDemoControlResult:
        result = self.active_symbols()
        if result.status is not DemoControlStatus.SYMBOLS_VALIDATED:
            return result
        if not any(item.underlying_symbol == symbol for item in result.symbols):
            return DerivDemoControlResult(DemoControlStatus.REJECTED, websocket_url_scoped_demo=True,
                                          symbols=result.symbols, reasons=(f"symbol {symbol!r} is not active",))
        return result

    def contracts_for(self, symbol: str) -> DerivDemoControlResult:
        if not self.websocket_url:
            return DerivDemoControlResult(DemoControlStatus.REJECTED, reasons=("demo session is not connected",))
        symbol_result = self.validate_symbol(symbol)
        if symbol_result.status is DemoControlStatus.REJECTED:
            return symbol_result
        try:
            response = self.transport.request(self.websocket_url, {"contracts_for": symbol}, self.config.timeout_seconds)
            if response.get("error"):
                return DerivDemoControlResult(DemoControlStatus.API_ERROR, websocket_url_scoped_demo=True,
                                              symbols=symbol_result.symbols,
                                              error=str((response.get("error") or {}).get("message", "Deriv error")))
            payload = response.get("contracts_for") or {}
            available: list[str] = []
            for group in payload.get("available", []) if isinstance(payload, Mapping) else []:
                if isinstance(group, Mapping):
                    for item in group.get("contracts", []) or []:
                        if isinstance(item, Mapping) and isinstance(item.get("contract_type"), str):
                            available.append(item["contract_type"])
            if not available:
                # Some API responses expose contract categories differently; preserve
                # raw evidence rather than inventing availability.
                raise DerivDemoControlError("contracts_for response did not expose contract types")
            contracts = DerivContractAvailability(symbol, tuple(sorted(set(available))), dict(payload))
            return DerivDemoControlResult(DemoControlStatus.CONTRACTS_VALIDATED,
                                          websocket_url_scoped_demo=True, symbols=symbol_result.symbols,
                                          contracts=contracts)
        except Exception as exc:
            return DerivDemoControlResult(DemoControlStatus.API_ERROR, websocket_url_scoped_demo=True,
                                          symbols=symbol_result.symbols, error=str(exc))

    def proposal(self, contract: DerivContractSpec) -> DerivDemoControlResult:
        if not self.websocket_url:
            return DerivDemoControlResult(DemoControlStatus.REJECTED, reasons=("demo session is not connected",))
        try:
            if self.policy.require_symbol_validation:
                symbol_result = self.validate_symbol(contract.underlying_symbol)
                if symbol_result.status is DemoControlStatus.REJECTED:
                    return symbol_result
            response = self.transport.request(self.websocket_url,
                                              {"proposal": 1, **contract.to_dict()},
                                              self.config.timeout_seconds)
            if response.get("error"):
                return DerivDemoControlResult(DemoControlStatus.API_ERROR, websocket_url_scoped_demo=True,
                                              error=str((response.get("error") or {}).get("message", "Deriv error")))
            proposal = response.get("proposal") or {}
            proposal_id = proposal.get("id")
            ask = proposal.get("ask_price")
            if not isinstance(proposal_id, str) or not proposal_id.strip():
                raise DerivDemoControlError("proposal response did not contain an id")
            ask_price = float(ask)
            if ask_price <= 0:
                raise DerivDemoControlError("proposal ask_price must be positive")
            return DerivDemoControlResult(DemoControlStatus.PROPOSAL_VALIDATED,
                                          websocket_url_scoped_demo=True,
                                          proposal_id=proposal_id, ask_price=ask_price,
                                          metadata={"proposal": dict(proposal)})
        except Exception as exc:
            return DerivDemoControlResult(DemoControlStatus.API_ERROR, websocket_url_scoped_demo=True, error=str(exc))

    def purchase_demo(self, proposal_result: DerivDemoControlResult, *, confirm_purchase: bool) -> DerivDemoControlResult:
        if not self.policy.allow_purchase:
            return DerivDemoControlResult(DemoControlStatus.REJECTED, reasons=("demo purchase is disabled by policy",))
        if self.policy.require_explicit_purchase_confirmation and not confirm_purchase:
            return DerivDemoControlResult(DemoControlStatus.REJECTED,
                                          proposal_id=proposal_result.proposal_id,
                                          ask_price=proposal_result.ask_price,
                                          reasons=("explicit demo purchase confirmation is required",))
        if proposal_result.status is not DemoControlStatus.PROPOSAL_VALIDATED:
            return DerivDemoControlResult(DemoControlStatus.REJECTED, reasons=("a validated proposal is required",))
        if not self.websocket_url or not proposal_result.proposal_id or proposal_result.ask_price is None:
            return DerivDemoControlResult(DemoControlStatus.REJECTED, reasons=("validated proposal is incomplete",))
        if proposal_result.ask_price > self.policy.maximum_purchase_price:
            return DerivDemoControlResult(DemoControlStatus.REJECTED, proposal_id=proposal_result.proposal_id,
                                          ask_price=proposal_result.ask_price,
                                          reasons=("proposal ask price exceeds demo safety ceiling",))
        try:
            response = self.transport.request(self.websocket_url,
                                              {"buy": proposal_result.proposal_id,
                                               "price": proposal_result.ask_price},
                                              self.config.timeout_seconds)
            if response.get("error"):
                return DerivDemoControlResult(DemoControlStatus.API_ERROR,
                                              websocket_url_scoped_demo=True,
                                              proposal_id=proposal_result.proposal_id,
                                              ask_price=proposal_result.ask_price,
                                              error=str((response.get("error") or {}).get("message", "Deriv error")))
            buy = response.get("buy") or {}
            contract_id = buy.get("contract_id")
            if contract_id is None:
                raise DerivDemoControlError("buy response did not contain contract_id")
            return DerivDemoControlResult(DemoControlStatus.PURCHASED,
                                          websocket_url_scoped_demo=True,
                                          proposal_id=proposal_result.proposal_id,
                                          ask_price=proposal_result.ask_price,
                                          contract_id=str(contract_id),
                                          metadata={"account_mode": "demo", "broker": "deriv",
                                                    "live_execution": False})
        except Exception as exc:
            return DerivDemoControlResult(DemoControlStatus.API_ERROR, websocket_url_scoped_demo=True,
                                          proposal_id=proposal_result.proposal_id,
                                          ask_price=proposal_result.ask_price, error=str(exc))

    def close(self) -> None:
        self.websocket_url = None
        self.transport.close()

    @staticmethod
    def _parse_symbol(row: Mapping[str, Any]) -> DerivActiveSymbol:
        symbol = row.get("underlying_symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            raise DerivDemoControlError("active symbol is missing underlying_symbol")
        pip = row.get("pip_size")
        return DerivActiveSymbol(
            underlying_symbol=symbol,
            market=row.get("market") if isinstance(row.get("market"), str) else None,
            underlying_symbol_name=row.get("underlying_symbol_name") if isinstance(row.get("underlying_symbol_name"), str) else None,
            underlying_symbol_type=row.get("underlying_symbol_type") if isinstance(row.get("underlying_symbol_type"), str) else None,
            exchange_is_open=bool(row["exchange_is_open"]) if "exchange_is_open" in row else None,
            is_trading_suspended=bool(row["is_trading_suspended"]) if "is_trading_suspended" in row else None,
            pip_size=float(pip) if pip is not None else None,
            raw=dict(row),
        )


def demo_config_from_environment() -> DerivDemoConfig:
    """Load credentials from environment without exposing them in output."""
    return DerivDemoConfig.from_environment()
