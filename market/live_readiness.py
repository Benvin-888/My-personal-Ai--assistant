"""APEX / BENVIN Phase 2.34 - Live Readiness Gate.

This module defines a provider-neutral, non-executing gate for determining
whether the APEX execution stack is structurally ready to enter a controlled
live-trading phase. It never reads credential values, connects to a broker,
places orders, or grants execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol

from .execution import ExecutionMode, ExecutionRequest


class LiveReadinessError(ValueError):
    """Raised for invalid live-readiness input."""


class LiveReadinessStatus(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    INVALID_INPUT = "INVALID_INPUT"


class ReadinessCheck(str, Enum):
    EXECUTION_MODE = "execution_mode"
    EXPLICIT_LIVE_ENABLEMENT = "explicit_live_enablement"
    REAL_ENDPOINT_SEPARATION = "real_endpoint_separation"
    CREDENTIAL_PROVIDER = "credential_provider"
    KILL_SWITCH = "kill_switch"
    RISK_LIMITS = "risk_limits"
    IDEMPOTENCY = "idempotency"
    RECONCILIATION = "reconciliation"
    AUDIT_LOGGING = "audit_logging"
    MONITORING = "monitoring"
    RECOVERY = "recovery"
    DEMO_SAFETY = "demo_safety"


@dataclass(frozen=True)
class LiveReadinessProfile:
    """Declarative live-readiness controls; contains no credential values."""

    live_enabled: bool = False
    live_endpoint: str | None = None
    demo_endpoint: str | None = None
    credential_provider_configured: bool = False
    kill_switch_enabled: bool = False
    risk_limits_configured: bool = False
    idempotency_enabled: bool = False
    reconciliation_enabled: bool = False
    audit_logging_enabled: bool = False
    monitoring_enabled: bool = False
    recovery_enabled: bool = False
    demo_safety_preserved: bool = True
    maximum_risk_fraction: float | None = None
    maximum_total_risk_fraction: float | None = None

    def __post_init__(self) -> None:
        if self.live_endpoint is not None and not isinstance(self.live_endpoint, str):
            raise LiveReadinessError("live_endpoint must be a string or None")
        if self.demo_endpoint is not None and not isinstance(self.demo_endpoint, str):
            raise LiveReadinessError("demo_endpoint must be a string or None")
        for name in ("maximum_risk_fraction", "maximum_total_risk_fraction"):
            value = getattr(self, name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise LiveReadinessError(f"{name} must be numeric or None")
                if value <= 0 or value > 1:
                    raise LiveReadinessError(f"{name} must be greater than 0 and at most 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "live_enabled": self.live_enabled,
            "live_endpoint_configured": bool(self.live_endpoint),
            "demo_endpoint_configured": bool(self.demo_endpoint),
            "credential_provider_configured": self.credential_provider_configured,
            "kill_switch_enabled": self.kill_switch_enabled,
            "risk_limits_configured": self.risk_limits_configured,
            "idempotency_enabled": self.idempotency_enabled,
            "reconciliation_enabled": self.reconciliation_enabled,
            "audit_logging_enabled": self.audit_logging_enabled,
            "monitoring_enabled": self.monitoring_enabled,
            "recovery_enabled": self.recovery_enabled,
            "demo_safety_preserved": self.demo_safety_preserved,
            "maximum_risk_fraction": self.maximum_risk_fraction,
            "maximum_total_risk_fraction": self.maximum_total_risk_fraction,
        }


class ReadinessEvidenceSource(Protocol):
    def checks(self) -> Mapping[str, bool]: ...


@dataclass(frozen=True)
class LiveReadinessResult:
    """Immutable readiness decision; never an execution authorization."""

    status: LiveReadinessStatus
    request_id: str
    failed_checks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.status is LiveReadinessStatus.READY

    @property
    def execution_authorized(self) -> bool:
        return False

    @property
    def broker_access(self) -> bool:
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
            "ready": self.ready,
            "execution_authorized": False,
            "broker_access": False,
            "live_execution": False,
            "credentials_exposed": False,
            "failed_checks": list(self.failed_checks),
            "warnings": list(self.warnings),
            "evidence": dict(self.evidence),
        }


class LiveReadinessGate:
    """Evaluate live-readiness prerequisites without broker or credential I/O."""

    def __init__(self, profile: LiveReadinessProfile) -> None:
        if not isinstance(profile, LiveReadinessProfile):
            raise LiveReadinessError("profile must be a LiveReadinessProfile")
        self._profile = profile

    @staticmethod
    def _separate_endpoints(live: str | None, demo: str | None) -> bool:
        if not live or not demo:
            return False
        return live.strip() != demo.strip()

    def evaluate(self, request: ExecutionRequest) -> LiveReadinessResult:
        request_id = str(getattr(request, "request_id", "INVALID"))
        try:
            if not isinstance(request, ExecutionRequest):
                raise LiveReadinessError("request must be an ExecutionRequest")
            if request.mode is not ExecutionMode.LIVE:
                return LiveReadinessResult(
                    LiveReadinessStatus.NOT_READY,
                    request.request_id,
                    (ReadinessCheck.EXECUTION_MODE.value,),
                    ("live-readiness evaluation requires LIVE execution mode",),
                    {},
                )

            p = self._profile
            failed: list[str] = []
            warnings: list[str] = []

            checks = {
                ReadinessCheck.EXECUTION_MODE.value: request.mode is ExecutionMode.LIVE,
                ReadinessCheck.EXPLICIT_LIVE_ENABLEMENT.value: p.live_enabled,
                ReadinessCheck.REAL_ENDPOINT_SEPARATION.value: self._separate_endpoints(
                    p.live_endpoint, p.demo_endpoint
                ),
                ReadinessCheck.CREDENTIAL_PROVIDER.value: p.credential_provider_configured,
                ReadinessCheck.KILL_SWITCH.value: p.kill_switch_enabled,
                ReadinessCheck.RISK_LIMITS.value: p.risk_limits_configured,
                ReadinessCheck.IDEMPOTENCY.value: p.idempotency_enabled,
                ReadinessCheck.RECONCILIATION.value: p.reconciliation_enabled,
                ReadinessCheck.AUDIT_LOGGING.value: p.audit_logging_enabled,
                ReadinessCheck.MONITORING.value: p.monitoring_enabled,
                ReadinessCheck.RECOVERY.value: p.recovery_enabled,
                ReadinessCheck.DEMO_SAFETY.value: p.demo_safety_preserved,
            }
            failed.extend(name for name, passed in checks.items() if not passed)

            if p.live_enabled and not p.credential_provider_configured:
                warnings.append("live enablement is configured without a credential provider")
            if p.maximum_risk_fraction is None or p.maximum_total_risk_fraction is None:
                failed.append(ReadinessCheck.RISK_LIMITS.value)
                if ReadinessCheck.RISK_LIMITS.value not in warnings:
                    warnings.append("explicit maximum risk fractions are required")
            elif p.maximum_total_risk_fraction < p.maximum_risk_fraction:
                failed.append(ReadinessCheck.RISK_LIMITS.value)
                warnings.append("maximum total risk must be at least maximum per-trade risk")

            # De-duplicate while preserving order.
            failed = list(dict.fromkeys(failed))
            evidence = {
                "checks": checks,
                "profile": p.to_dict(),
                "network_access_performed": False,
                "credential_values_read": False,
                "execution_performed": False,
            }
            status = LiveReadinessStatus.READY if not failed else LiveReadinessStatus.NOT_READY
            return LiveReadinessResult(status, request.request_id, tuple(failed), tuple(warnings), evidence)
        except LiveReadinessError as exc:
            return LiveReadinessResult(
                LiveReadinessStatus.INVALID_INPUT,
                request_id,
                (str(exc),),
                (),
                {"network_access_performed": False, "credential_values_read": False, "execution_performed": False},
            )


def evaluate_live_readiness(
    request: ExecutionRequest, profile: LiveReadinessProfile
) -> LiveReadinessResult:
    """Functional wrapper for deterministic live-readiness evaluation."""
    return LiveReadinessGate(profile).evaluate(request)
