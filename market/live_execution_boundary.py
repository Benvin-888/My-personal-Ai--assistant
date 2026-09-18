"""APEX / BENVIN Phase 2.36 - Live Order Execution Boundary.

This module is the provider-neutral final safety boundary immediately before a
future live execution adapter.  It combines the existing execution gateway
and live-readiness gate with explicit live-session and operational evidence.

Phase 2.36 deliberately does NOT place orders, call broker execution APIs,
read credential values, or grant an order-execution authorization.  A passed
boundary means that a future live adapter may be considered structurally
eligible; it is not proof of execution and is not an execution receipt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .execution import (
    ExecutionAdapterCapability,
    ExecutionGateway,
    ExecutionMode,
    ExecutionPolicy,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from .live_readiness import LiveReadinessGate, LiveReadinessProfile, LiveReadinessResult


class LiveExecutionBoundaryError(ValueError):
    """Raised for invalid live-boundary input."""


class LiveBoundaryStatus(str, Enum):
    BLOCKED = "BLOCKED"
    PASSED = "PASSED"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class LiveExecutionEvidence:
    """Non-secret evidence required before a future live adapter can run."""

    authenticated_real_session: bool = False
    real_endpoint_verified: bool = False
    balance_verified: bool = False
    demo_scope_false: bool = False
    credentials_exposed_false: bool = True
    trading_performed_false: bool = True
    kill_switch_clear: bool = False
    reconciliation_current: bool = False
    audit_logging_ready: bool = False
    monitoring_ready: bool = False
    recovery_ready: bool = False
    explicit_live_confirmation: bool = False
    live_adapter_present: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "authenticated_real_session": self.authenticated_real_session,
            "real_endpoint_verified": self.real_endpoint_verified,
            "balance_verified": self.balance_verified,
            "demo_scope_false": self.demo_scope_false,
            "credentials_exposed_false": self.credentials_exposed_false,
            "trading_performed_false": self.trading_performed_false,
            "kill_switch_clear": self.kill_switch_clear,
            "reconciliation_current": self.reconciliation_current,
            "audit_logging_ready": self.audit_logging_ready,
            "monitoring_ready": self.monitoring_ready,
            "recovery_ready": self.recovery_ready,
            "explicit_live_confirmation": self.explicit_live_confirmation,
            "live_adapter_present": self.live_adapter_present,
        }


@dataclass(frozen=True)
class LiveExecutionBoundaryResult:
    """Immutable result of live-boundary evaluation; never an execution receipt."""

    status: LiveBoundaryStatus
    request_id: str
    failed_checks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    gateway_result: ExecutionResult | None = None
    readiness_result: LiveReadinessResult | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status is LiveBoundaryStatus.PASSED

    @property
    def execution_authorized(self) -> bool:
        return False

    @property
    def broker_access(self) -> bool:
        return False

    @property
    def order_placed(self) -> bool:
        return False

    @property
    def live_execution(self) -> bool:
        return False

    @property
    def credentials_exposed(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        result = {
            "success": self.passed,
            "market": "forex",
            "component": "live_execution_boundary",
            "status": self.status.value,
            "request_id": self.request_id,
            "passed": self.passed,
            "execution_authorized": False,
            "broker_access": False,
            "order_placed": False,
            "live_execution": False,
            "credentials_exposed": False,
            "failed_checks": list(self.failed_checks),
            "warnings": list(self.warnings),
            "evidence": dict(self.evidence),
        }
        if self.gateway_result is not None:
            result["gateway"] = self.gateway_result.to_dict()
        if self.readiness_result is not None:
            result["readiness"] = self.readiness_result.to_dict()
        return result


class LiveExecutionBoundary:
    """Evaluate the final live safety boundary without executing anything."""

    def __init__(
        self,
        *,
        readiness_profile: LiveReadinessProfile,
        execution_policy: ExecutionPolicy | None = None,
    ) -> None:
        if not isinstance(readiness_profile, LiveReadinessProfile):
            raise LiveExecutionBoundaryError(
                "readiness_profile must be a LiveReadinessProfile"
            )
        policy = execution_policy or ExecutionPolicy(mode=ExecutionMode.LIVE)
        if policy.mode is not ExecutionMode.LIVE:
            raise LiveExecutionBoundaryError(
                "live execution boundary requires a LIVE execution policy"
            )
        self._readiness = LiveReadinessGate(readiness_profile)
        self._gateway = ExecutionGateway(policy)

    def evaluate(
        self,
        request: ExecutionRequest,
        *,
        total_risk_fraction: float | None = None,
        evidence: LiveExecutionEvidence | None = None,
    ) -> LiveExecutionBoundaryResult:
        request_id = str(getattr(request, "request_id", "INVALID"))
        try:
            if not isinstance(request, ExecutionRequest):
                raise LiveExecutionBoundaryError(
                    "request must be an ExecutionRequest"
                )
            if evidence is None or not isinstance(evidence, LiveExecutionEvidence):
                raise LiveExecutionBoundaryError(
                    "live execution evidence is required"
                )

            gateway_result = self._gateway.validate(
                request,
                total_risk_fraction=total_risk_fraction,
                adapter_capability=ExecutionAdapterCapability.LIVE,
            )
            readiness_result = self._readiness.evaluate(request)

            failed: list[str] = []
            warnings: list[str] = []

            if gateway_result.status is not ExecutionStatus.READY_FOR_ADAPTER:
                failed.append("execution_gateway")

            if not readiness_result.ready:
                failed.extend(
                    f"readiness:{check}"
                    for check in readiness_result.failed_checks
                )

            checks = evidence.to_dict()
            required_evidence = {
                "authenticated_real_session": evidence.authenticated_real_session,
                "real_endpoint_verified": evidence.real_endpoint_verified,
                "balance_verified": evidence.balance_verified,
                "demo_scope_false": evidence.demo_scope_false,
                "credentials_exposed_false": evidence.credentials_exposed_false,
                "trading_performed_false": evidence.trading_performed_false,
                "kill_switch_clear": evidence.kill_switch_clear,
                "reconciliation_current": evidence.reconciliation_current,
                "audit_logging_ready": evidence.audit_logging_ready,
                "monitoring_ready": evidence.monitoring_ready,
                "recovery_ready": evidence.recovery_ready,
                "explicit_live_confirmation": evidence.explicit_live_confirmation,
                "live_adapter_present": evidence.live_adapter_present,
            }
            for name, passed in required_evidence.items():
                if not passed:
                    failed.append(f"evidence:{name}")

            warnings.extend(readiness_result.warnings)
            warnings.append(
                "Phase 2.36 never authorizes, invokes, or verifies a live order"
            )

            failed = list(dict.fromkeys(failed))
            status = LiveBoundaryStatus.PASSED if not failed else LiveBoundaryStatus.BLOCKED
            safe_evidence = {
                "checks": checks,
                "network_access_performed": False,
                "credential_values_read": False,
                "execution_performed": False,
                "execution_authorized": False,
                "broker_access": False,
                "order_placed": False,
            }
            return LiveExecutionBoundaryResult(
                status,
                request.request_id,
                tuple(failed),
                tuple(warnings),
                gateway_result,
                readiness_result,
                safe_evidence,
            )
        except LiveExecutionBoundaryError as exc:
            return LiveExecutionBoundaryResult(
                LiveBoundaryStatus.INVALID_INPUT,
                request_id,
                (str(exc),),
                (),
                evidence={
                    "network_access_performed": False,
                    "credential_values_read": False,
                    "execution_performed": False,
                    "execution_authorized": False,
                    "broker_access": False,
                    "order_placed": False,
                },
            )


def evaluate_live_execution_boundary(
    request: ExecutionRequest,
    *,
    readiness_profile: LiveReadinessProfile,
    evidence: LiveExecutionEvidence,
    execution_policy: ExecutionPolicy | None = None,
    total_risk_fraction: float | None = None,
) -> LiveExecutionBoundaryResult:
    """Functional wrapper for deterministic live-boundary evaluation."""
    return LiveExecutionBoundary(
        readiness_profile=readiness_profile,
        execution_policy=execution_policy,
    ).evaluate(
        request,
        total_risk_fraction=total_risk_fraction,
        evidence=evidence,
    )
