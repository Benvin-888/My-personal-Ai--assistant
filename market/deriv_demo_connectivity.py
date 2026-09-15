"""APEX / BENVIN Phase 2.29 - Deriv Demo Credential & Connectivity Gate.

This phase introduces the first credential-aware connectivity layer, but it does
not place, modify, sell, or cancel contracts. Credentials are read from the
local environment only and are never returned in results or audit metadata.
The authenticated WebSocket URL is validated as demo-scoped and then opened
and closed as a connectivity probe.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .deriv_demo import DerivDemoConfig, DerivDemoError, DerivWebSocketTransport


class DerivDemoConnectivityError(ValueError):
    """Raised for invalid or unsafe connectivity configuration."""


class DemoConnectivityStatus(str, Enum):
    READY = "READY"
    CONNECTED = "CONNECTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DemoCredentialState:
    configured: bool
    account_id_present: bool
    token_present: bool
    app_id_present: bool

    @property
    def safe_summary(self) -> dict[str, bool]:
        return {
            "configured": self.configured,
            "account_id_present": self.account_id_present,
            "token_present": self.token_present,
            "app_id_present": self.app_id_present,
        }


@dataclass(frozen=True)
class DemoConnectivityResult:
    status: DemoConnectivityStatus
    account_id: str | None = None
    websocket_demo_scoped: bool = False
    live_endpoint_detected: bool = False
    credentials_exposed: bool = False
    message: str = ""

    @property
    def connected(self) -> bool:
        return self.status is DemoConnectivityStatus.CONNECTED

    @property
    def trading_performed(self) -> bool:
        return False

    @property
    def live_execution(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "account_id": self.account_id,
            "websocket_demo_scoped": self.websocket_demo_scoped,
            "live_endpoint_detected": self.live_endpoint_detected,
            "credentials_exposed": self.credentials_exposed,
            "trading_performed": False,
            "live_execution": False,
            "message": self.message,
        }


class DemoConnectivityTransport(Protocol):
    def get_authenticated_websocket_url(self, config: DerivDemoConfig) -> str: ...
    def probe_websocket(self, websocket_url: str, timeout: float) -> None: ...


class DerivDemoConnectivityTransport:
    """Real transport for a non-trading demo connectivity probe."""

    def __init__(self, base_transport: DerivWebSocketTransport | None = None) -> None:
        self._base = base_transport or DerivWebSocketTransport()

    def get_authenticated_websocket_url(self, config: DerivDemoConfig) -> str:
        return self._base.get_authenticated_websocket_url(config)

    def probe_websocket(self, websocket_url: str, timeout: float) -> None:
        if not websocket_url.startswith("wss://"):
            raise DerivDemoConnectivityError("authenticated WebSocket URL must use wss")
        if "/ws/real" in websocket_url:
            raise DerivDemoConnectivityError("real-account WebSocket URL rejected")
        if "/ws/demo" not in websocket_url:
            raise DerivDemoConnectivityError("WebSocket URL is not demo-scoped")
        try:
            import websocket
        except ImportError as exc:
            raise DerivDemoConnectivityError("websocket-client is required") from exc
        ws = None
        try:
            ws = websocket.create_connection(websocket_url, timeout=timeout)
        except Exception as exc:
            raise DerivDemoConnectivityError(f"demo WebSocket connection failed: {exc}") from exc
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass


class DerivDemoConnectivityGate:
    """Validate local credentials and optionally prove demo connectivity."""

    def __init__(self, *, transport: DemoConnectivityTransport | None = None) -> None:
        self.transport = transport or DerivDemoConnectivityTransport()

    @staticmethod
    def inspect_environment() -> DemoCredentialState:
        import os
        account = bool(os.getenv("DERIV_DEMO_ACCOUNT_ID", "").strip())
        token = bool(os.getenv("DERIV_AUTH_TOKEN", "").strip())
        app_id = bool(os.getenv("DERIV_APP_ID", "").strip())
        return DemoCredentialState(
            configured=account and token,
            account_id_present=account,
            token_present=token,
            app_id_present=app_id,
        )

    def validate_configuration(self, config: DerivDemoConfig) -> DemoConnectivityResult:
        if not config.account_id.strip() or not config.authorization_token.strip():
            return DemoConnectivityResult(
                status=DemoConnectivityStatus.REJECTED,
                message="demo account ID and authorization token are required",
            )
        if not config.rest_base_url.startswith("https://"):
            return DemoConnectivityResult(
                status=DemoConnectivityStatus.REJECTED,
                message="REST endpoint must use HTTPS",
            )
        return DemoConnectivityResult(
            status=DemoConnectivityStatus.READY,
            account_id=config.account_id,
            message="demo credentials are configured; no broker request performed",
        )

    def connect(self, config: DerivDemoConfig) -> DemoConnectivityResult:
        ready = self.validate_configuration(config)
        if ready.status is not DemoConnectivityStatus.READY:
            return ready
        try:
            ws_url = self.transport.get_authenticated_websocket_url(config)
            if "/ws/real" in ws_url:
                return DemoConnectivityResult(
                    status=DemoConnectivityStatus.REJECTED,
                    account_id=config.account_id,
                    live_endpoint_detected=True,
                    message="real-account WebSocket URL rejected",
                )
            if "/ws/demo" not in ws_url:
                return DemoConnectivityResult(
                    status=DemoConnectivityStatus.REJECTED,
                    account_id=config.account_id,
                    message="authenticated WebSocket URL is not demo-scoped",
                )
            self.transport.probe_websocket(ws_url, config.timeout_seconds)
        except (DerivDemoError, DerivDemoConnectivityError) as exc:
            return DemoConnectivityResult(
                status=DemoConnectivityStatus.FAILED,
                account_id=config.account_id,
                websocket_demo_scoped=False,
                message=str(exc),
            )
        except Exception as exc:
            return DemoConnectivityResult(
                status=DemoConnectivityStatus.FAILED,
                account_id=config.account_id,
                message=f"unexpected connectivity failure: {exc}",
            )
        return DemoConnectivityResult(
            status=DemoConnectivityStatus.CONNECTED,
            account_id=config.account_id,
            websocket_demo_scoped=True,
            message="Deriv demo authentication and WebSocket connectivity verified",
        )

    def connect_from_environment(self) -> DemoConnectivityResult:
        try:
            config = DerivDemoConfig.from_environment()
        except DerivDemoError as exc:
            return DemoConnectivityResult(
                status=DemoConnectivityStatus.REJECTED,
                message=str(exc),
            )
        return self.connect(config)
