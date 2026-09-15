"""APEX / BENVIN Phase 2.30 - Authenticated Deriv Demo Session.

This phase validates a real authenticated Deriv demo WebSocket session without
placing, modifying, selling, cancelling, or monitoring a trade.  It proves the
credential -> OTP -> demo WebSocket -> authenticated read-only request path.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol


_UNSET = object()

from .deriv_demo import DerivDemoConfig, DerivDemoError, DerivWebSocketTransport


class DerivDemoSessionError(ValueError):
    """Raised for invalid or unsafe authenticated demo-session operations."""


class DemoAuthMethod(str, Enum):
    PAT = "PAT"
    OAUTH = "OAUTH"


class DemoSessionStatus(str, Enum):
    READY = "READY"
    AUTHENTICATED = "AUTHENTICATED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DemoAuthConfiguration:
    """Explicit authentication method without storing credential values."""

    method: DemoAuthMethod
    app_id_required: Any = _UNSET

    def __post_init__(self) -> None:
        expected = self.method is DemoAuthMethod.PAT
        if self.app_id_required is _UNSET:
            object.__setattr__(self, "app_id_required", expected)
            return
        if not isinstance(self.app_id_required, bool):
            raise DerivDemoError("app_id_required must be a boolean when explicitly provided")
        if self.app_id_required != expected:
            raise DerivDemoError("authentication method and app ID requirement are inconsistent")

    @classmethod
    def pat(cls) -> "DemoAuthConfiguration":
        return cls(method=DemoAuthMethod.PAT, app_id_required=True)

    @classmethod
    def oauth(cls) -> "DemoAuthConfiguration":
        return cls(method=DemoAuthMethod.OAUTH, app_id_required=False)


@dataclass(frozen=True)
class DemoSessionResult:
    status: DemoSessionStatus
    account_id: str | None = None
    auth_method: DemoAuthMethod | None = None
    websocket_demo_scoped: bool = False
    authenticated_request_verified: bool = False
    trading_performed: bool = False
    live_execution: bool = False
    credentials_exposed: bool = False
    balance_verified: bool = False
    currency: str | None = None
    message: str = ""

    @property
    def authenticated(self) -> bool:
        return self.status is DemoSessionStatus.AUTHENTICATED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "account_id": self.account_id,
            "auth_method": self.auth_method.value if self.auth_method else None,
            "websocket_demo_scoped": self.websocket_demo_scoped,
            "authenticated_request_verified": self.authenticated_request_verified,
            "trading_performed": False,
            "live_execution": False,
            "credentials_exposed": False,
            "balance_verified": self.balance_verified,
            "currency": self.currency,
            "message": self.message,
        }


class DemoSessionTransport(Protocol):
    def get_authenticated_websocket_url(self, config: DerivDemoConfig) -> str: ...

    def request_read_only(
        self, websocket_url: str, payload: Mapping[str, Any], timeout: float
    ) -> Mapping[str, Any]: ...


class DerivAuthenticatedDemoTransport:
    """Real transport for one-shot authenticated, read-only demo validation."""

    def __init__(self, base_transport: DerivWebSocketTransport | None = None) -> None:
        self._base = base_transport or DerivWebSocketTransport()

    def get_authenticated_websocket_url(self, config: DerivDemoConfig) -> str:
        return self._base.get_authenticated_websocket_url(config)

    def request_read_only(
        self, websocket_url: str, payload: Mapping[str, Any], timeout: float
    ) -> Mapping[str, Any]:
        if not websocket_url.startswith("wss://"):
            raise DerivDemoSessionError("authenticated WebSocket URL must use wss")
        if "/ws/real" in websocket_url:
            raise DerivDemoSessionError("real-account WebSocket URL rejected")
        if "/ws/demo" not in websocket_url:
            raise DerivDemoSessionError("WebSocket URL is not demo-scoped")
        try:
            import websocket
        except ImportError as exc:
            raise DerivDemoSessionError("websocket-client is required") from exc

        ws = None
        try:
            ws = websocket.create_connection(websocket_url, timeout=timeout)
            ws.send(__import__("json").dumps(dict(payload), separators=(",", ":")))
            raw = ws.recv()
            data = __import__("json").loads(raw)
            if not isinstance(data, dict):
                raise DerivDemoSessionError("Deriv response must be a JSON object")
            return data
        except DerivDemoSessionError:
            raise
        except Exception as exc:
            raise DerivDemoSessionError(f"authenticated demo request failed: {exc}") from exc
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass


class DerivDemoAuthenticatedSession:
    """One-shot authenticated demo session validator; never performs trading."""

    def __init__(
        self,
        *,
        auth: DemoAuthConfiguration | None = None,
        transport: DemoSessionTransport | None = None,
    ) -> None:
        self.auth = auth or DemoAuthConfiguration.pat()
        self.transport = transport or DerivAuthenticatedDemoTransport()

    def validate_configuration(self, config: DerivDemoConfig) -> DemoSessionResult:
        if not config.account_id.strip() or not config.authorization_token.strip():
            return DemoSessionResult(
                status=DemoSessionStatus.REJECTED,
                auth_method=self.auth.method,
                message="demo account ID and authorization token are required",
            )
        if not config.rest_base_url.startswith("https://"):
            return DemoSessionResult(
                status=DemoSessionStatus.REJECTED,
                account_id=config.account_id,
                auth_method=self.auth.method,
                message="REST endpoint must use HTTPS",
            )
        if self.auth.app_id_required and not (config.app_id or "").strip():
            return DemoSessionResult(
                status=DemoSessionStatus.REJECTED,
                account_id=config.account_id,
                auth_method=self.auth.method,
                message="Deriv-App-ID is required for PAT authentication",
            )
        return DemoSessionResult(
            status=DemoSessionStatus.READY,
            account_id=config.account_id,
            auth_method=self.auth.method,
            message="authenticated demo session configuration is valid",
        )

    def validate(self, config: DerivDemoConfig) -> DemoSessionResult:
        ready = self.validate_configuration(config)
        if ready.status is not DemoSessionStatus.READY:
            return ready

        try:
            ws_url = self.transport.get_authenticated_websocket_url(config)
            if "/ws/real" in ws_url:
                return DemoSessionResult(
                    status=DemoSessionStatus.REJECTED,
                    account_id=config.account_id,
                    auth_method=self.auth.method,
                    live_execution=False,
                    message="real-account WebSocket URL rejected",
                )
            if not ws_url.startswith("wss://") or "/ws/demo" not in ws_url:
                return DemoSessionResult(
                    status=DemoSessionStatus.REJECTED,
                    account_id=config.account_id,
                    auth_method=self.auth.method,
                    message="authenticated WebSocket URL is not secure and demo-scoped",
                )

            # balance is account-scoped and auth-required. No trade operation is sent.
            response = self.transport.request_read_only(
                ws_url,
                {"balance": 1},
                config.timeout_seconds,
            )
            if response.get("error"):
                error = response.get("error") or {}
                message = str(error.get("message", "Deriv authenticated request failed"))
                return DemoSessionResult(
                    status=DemoSessionStatus.FAILED,
                    account_id=config.account_id,
                    auth_method=self.auth.method,
                    websocket_demo_scoped=True,
                    message=message,
                )
            if response.get("msg_type") != "balance":
                return DemoSessionResult(
                    status=DemoSessionStatus.FAILED,
                    account_id=config.account_id,
                    auth_method=self.auth.method,
                    websocket_demo_scoped=True,
                    message="authenticated session did not return a balance response",
                )
            balance = response.get("balance") or {}
            currency = balance.get("currency") if isinstance(balance, dict) else None
            return DemoSessionResult(
                status=DemoSessionStatus.AUTHENTICATED,
                account_id=config.account_id,
                auth_method=self.auth.method,
                websocket_demo_scoped=True,
                authenticated_request_verified=True,
                balance_verified=True,
                currency=str(currency) if currency is not None else None,
                message="authenticated Deriv demo session verified with a read-only balance request",
            )
        except (DerivDemoError, DerivDemoSessionError) as exc:
            return DemoSessionResult(
                status=DemoSessionStatus.FAILED,
                account_id=config.account_id,
                auth_method=self.auth.method,
                message=str(exc),
            )
        except Exception as exc:
            return DemoSessionResult(
                status=DemoSessionStatus.FAILED,
                account_id=config.account_id,
                auth_method=self.auth.method,
                message=f"unexpected authenticated session failure: {exc}",
            )

    def validate_from_environment(self) -> DemoSessionResult:
        try:
            config = DerivDemoConfig.from_environment()
        except DerivDemoError as exc:
            return DemoSessionResult(
                status=DemoSessionStatus.REJECTED,
                auth_method=self.auth.method,
                message=str(exc),
            )
        return self.validate(config)
