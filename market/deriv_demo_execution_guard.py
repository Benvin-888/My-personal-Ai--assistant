"""APEX / BENVIN Phase 2.33 - Demo Execution Admission Guard.

This module binds demo execution admission to an already authenticated,
healthy demo session.  It is a safety gate only: it never places orders,
performs broker I/O, exposes credentials, or grants execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol

from .deriv_demo import DerivDemoError
from .deriv_demo_session_manager import DerivDemoSessionManager
from .execution import ExecutionMode, ExecutionRequest


class DemoExecutionAdmissionError(ValueError):
    """Raised for invalid demo execution admission input."""


class DemoAdmissionStatus(str, Enum):
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class DemoExecutionAdmissionResult:
    """Immutable admission result; never an execution authorization."""

    status: DemoAdmissionStatus
    request_id: str
    reasons: tuple[str, ...] = ()
    health: Mapping[str, Any] = field(default_factory=dict)

    @property
    def admitted(self) -> bool:
        return self.status is DemoAdmissionStatus.ADMITTED

    @property
    def execution_authorized(self) -> bool:
        """Always false: admission is not execution authority."""
        return False

    @property
    def live_execution(self) -> bool:
        return False

    @property
    def credentials_exposed(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "request_id": self.request_id,
            "admitted": self.admitted,
            "execution_authorized": False,
            "live_execution": False,
            "credentials_exposed": False,
            "reasons": list(self.reasons),
            "health": dict(self.health),
        }


class DemoSessionHealthSource(Protocol):
    def health(self) -> Mapping[str, Any]: ...


class DemoExecutionAdmissionGuard:
    """Require a healthy authenticated demo session before demo admission."""

    def __init__(self, session_manager: DemoSessionHealthSource) -> None:
        if not callable(getattr(session_manager, "health", None)):
            raise DemoExecutionAdmissionError("session_manager must provide health()")
        self._session_manager = session_manager

    def check(self, request: ExecutionRequest) -> DemoExecutionAdmissionResult:
        request_id = getattr(request, "request_id", "INVALID")
        try:
            if not isinstance(request, ExecutionRequest):
                raise DemoExecutionAdmissionError("request must be an ExecutionRequest")
            if request.mode is not ExecutionMode.DEMO:
                return DemoExecutionAdmissionResult(
                    DemoAdmissionStatus.REJECTED,
                    request.request_id,
                    ("demo admission requires DEMO execution mode",),
                )

            health = dict(self._session_manager.health())
            reasons: list[str] = []
            if health.get("status") != "HEALTHY":
                reasons.append("authenticated demo session is not healthy")
            if health.get("lifecycle") != "AUTHENTICATED":
                reasons.append("authenticated demo session is not active")
            if health.get("authenticated") is not True:
                reasons.append("demo session is not authenticated")
            if health.get("demo_scope") is not True:
                reasons.append("demo session is not demo-scoped")
            if health.get("authenticated_read_only") is not True:
                reasons.append("authenticated read-only verification is missing")
            if health.get("credentials_exposed") is not False:
                reasons.append("session health reports credential exposure")
            if health.get("trading_performed") is not False:
                reasons.append("session health reports prior trading activity")
            if health.get("live_execution") is not False:
                reasons.append("session health reports live execution")

            status = DemoAdmissionStatus.ADMITTED if not reasons else DemoAdmissionStatus.REJECTED
            return DemoExecutionAdmissionResult(status, request.request_id, tuple(reasons), health)
        except DemoExecutionAdmissionError as exc:
            return DemoExecutionAdmissionResult(
                DemoAdmissionStatus.INVALID_INPUT,
                str(request_id),
                (str(exc),),
                {},
            )
        except (DerivDemoError, TypeError, ValueError, RuntimeError) as exc:
            return DemoExecutionAdmissionResult(
                DemoAdmissionStatus.REJECTED,
                str(request_id),
                (f"demo session health check failed: {exc}",),
                {},
            )


def require_demo_execution_admission(
    request: ExecutionRequest,
    session_manager: DemoSessionHealthSource,
) -> DemoExecutionAdmissionResult:
    """Functional wrapper for deterministic demo-session admission checking."""
    return DemoExecutionAdmissionGuard(session_manager).check(request)
