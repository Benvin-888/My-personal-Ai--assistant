"""APEX / BENVIN Phase 2.32 - Authenticated Demo Operational Control.

Provides operational health, bounded reconnect, and lifecycle control around the authenticated demo session.
The manager owns state only; it does not execute trades and never exposes secrets.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable
import time

from .deriv_demo import DerivDemoConfig, DerivDemoError
from .deriv_demo_session import (
    DemoAuthConfiguration,
    DemoAuthMethod,
    DemoSessionResult,
    DemoSessionStatus,
    DerivDemoAuthenticatedSession,
    DemoSessionTransport,
)


class DemoSessionLifecycle(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    AUTHENTICATED = "AUTHENTICATED"
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class DemoSessionState:
    lifecycle: DemoSessionLifecycle
    account_id: str | None = None
    auth_method: str | None = None
    demo_scope: bool = False
    authenticated_read_only: bool = False
    reconnect_count: int = 0
    last_message: str = ""

    @property
    def connected(self) -> bool:
        return self.lifecycle is DemoSessionLifecycle.AUTHENTICATED

    def to_dict(self) -> dict[str, object]:
        return {
            "lifecycle": self.lifecycle.value,
            "account_id": self.account_id,
            "auth_method": self.auth_method,
            "demo_scope": self.demo_scope,
            "authenticated_read_only": self.authenticated_read_only,
            "reconnect_count": self.reconnect_count,
            "last_message": self.last_message,
        }


class DerivDemoSessionManager:
    """Manage authenticated demo session lifecycle without trading authority."""

    def __init__(
        self,
        config: DerivDemoConfig,
        *,
        auth: DemoAuthConfiguration | None = None,
        transport: DemoSessionTransport | None = None,
        session_factory: Callable[..., DerivDemoAuthenticatedSession] | None = None,
        clock: Callable[[], float] | None = None,
        max_reconnects: int = 3,
    ) -> None:
        self._config = config
        # The Phase 2.30 validator defaults to PAT. Make the manager's effective
        # authentication method explicit as well, so lifecycle state and validation
        # cannot disagree about the required credential configuration.
        self._auth = auth or DemoAuthConfiguration.pat()
        self._transport = transport
        self._session_factory = session_factory or DerivDemoAuthenticatedSession
        self._clock = clock or time.monotonic
        if isinstance(max_reconnects, bool) or not isinstance(max_reconnects, int) or max_reconnects < 0:
            raise DerivDemoError("max_reconnects must be a non-negative integer")
        self._max_reconnects = max_reconnects
        self._authenticated_at: float | None = None
        self._last_transition_at: float = self._clock()
        self._state = DemoSessionState(DemoSessionLifecycle.DISCONNECTED)
        self._last_result: DemoSessionResult | None = None
        self._validate_manager_configuration()

    def _validate_manager_configuration(self) -> None:
        if self._auth.method is DemoAuthMethod.PAT and not (self._config.app_id or "").strip():
            raise DerivDemoError("Deriv-App-ID is required for PAT authentication")

    @property
    def state(self) -> DemoSessionState:
        return self._state

    @property
    def authenticated(self) -> bool:
        return self._state.connected

    @property
    def last_result(self) -> DemoSessionResult | None:
        return self._last_result

    def _new_session(self) -> DerivDemoAuthenticatedSession:
        return self._session_factory(auth=self._auth, transport=self._transport)

    @staticmethod
    def _state_from_result(
        result: DemoSessionResult,
        *,
        lifecycle: DemoSessionLifecycle,
        reconnect_count: int,
    ) -> DemoSessionState:
        return DemoSessionState(
            lifecycle,
            account_id=result.account_id,
            auth_method=result.auth_method.value if result.auth_method else None,
            demo_scope=result.websocket_demo_scoped,
            authenticated_read_only=result.authenticated_request_verified,
            reconnect_count=reconnect_count,
            last_message=result.message,
        )

    def _transition(self, state: DemoSessionState) -> None:
        self._state = state
        self._last_transition_at = self._clock()
        if state.lifecycle is not DemoSessionLifecycle.AUTHENTICATED:
            self._authenticated_at = None

    def health(self) -> dict[str, object]:
        """Return lifecycle health only; this does not perform a network request."""
        now = self._clock()
        age = None if self._authenticated_at is None else max(0.0, now - self._authenticated_at)
        if self._state.lifecycle is DemoSessionLifecycle.AUTHENTICATED:
            status = "HEALTHY"
        elif self._state.lifecycle in (DemoSessionLifecycle.EXPIRED, DemoSessionLifecycle.FAILED):
            status = "RECONNECT_REQUIRED"
        elif self._state.lifecycle is DemoSessionLifecycle.DISCONNECTED:
            status = "DISCONNECTED"
        else:
            status = "TRANSITIONING"
        return {
            "status": status,
            "lifecycle": self._state.lifecycle.value,
            "authenticated": self.authenticated,
            "demo_scope": self._state.demo_scope,
            "authenticated_read_only": self._state.authenticated_read_only,
            "account_id": self._state.account_id,
            "auth_method": self._state.auth_method,
            "reconnect_count": self._state.reconnect_count,
            "authenticated_age_seconds": round(age, 6) if age is not None else None,
            "last_transition_age_seconds": round(max(0.0, now - self._last_transition_at), 6),
            "credentials_exposed": False,
            "trading_performed": False,
            "live_execution": False,
        }

    @property
    def reconnect_allowed(self) -> bool:
        return self._state.reconnect_count < self._max_reconnects

    def connect(self) -> DemoSessionResult:
        if self.authenticated:
            result = self._last_result
            if result is not None:
                return result

        self._validate_manager_configuration()
        reconnect_count = self._state.reconnect_count
        self._transition(DemoSessionState(
            DemoSessionLifecycle.CONNECTING,
            account_id=self._config.account_id,
            auth_method=self._auth.method.value,
            demo_scope=True,
            reconnect_count=reconnect_count,
            last_message="authenticating demo session",
        ))

        result = self._new_session().validate(self._config)
        self._last_result = result
        lifecycle = (
            DemoSessionLifecycle.AUTHENTICATED
            if result.authenticated
            else DemoSessionLifecycle.FAILED
        )
        next_state = self._state_from_result(
            result, lifecycle=lifecycle, reconnect_count=reconnect_count
        )
        self._transition(next_state)
        if result.authenticated:
            self._authenticated_at = self._clock()
        return result

    def disconnect(self, reason: str = "session disconnected") -> DemoSessionState:
        self._transition(DemoSessionState(
            DemoSessionLifecycle.DISCONNECTED,
            account_id=self._state.account_id,
            auth_method=self._state.auth_method,
            reconnect_count=self._state.reconnect_count,
            last_message=reason,
        ))
        return self._state

    def mark_expired(self, reason: str = "authenticated session expired") -> DemoSessionState:
        self._transition(DemoSessionState(
            DemoSessionLifecycle.EXPIRED,
            account_id=self._state.account_id,
            auth_method=self._state.auth_method,
            demo_scope=self._state.demo_scope,
            authenticated_read_only=self._state.authenticated_read_only,
            reconnect_count=self._state.reconnect_count,
            last_message=reason,
        ))
        return self._state

    def reconnect(self) -> DemoSessionResult:
        self._validate_manager_configuration()
        if not self.reconnect_allowed:
            raise DerivDemoError("maximum demo session reconnect attempts reached")
        next_count = self._state.reconnect_count + 1
        self._transition(DemoSessionState(
            DemoSessionLifecycle.RECONNECTING,
            account_id=self._state.account_id or self._config.account_id,
            auth_method=self._auth.method.value,
            demo_scope=True,
            reconnect_count=next_count,
            last_message="reconnecting authenticated demo session",
        ))

        result = self._new_session().validate(self._config)
        self._last_result = result
        lifecycle = (
            DemoSessionLifecycle.AUTHENTICATED
            if result.authenticated
            else DemoSessionLifecycle.FAILED
        )
        next_state = self._state_from_result(
            result, lifecycle=lifecycle, reconnect_count=next_count
        )
        self._transition(next_state)
        if result.authenticated:
            self._authenticated_at = self._clock()
        return result

    def require_authenticated(self) -> None:
        if not self.authenticated:
            raise DerivDemoError("authenticated demo session is not active")

    def safe_summary(self) -> dict[str, object]:
        summary = self._state.to_dict()
        summary["health"] = self.health()
        summary["credentials_exposed"] = False
        summary["trading_performed"] = False
        summary["live_execution"] = False
        return summary
