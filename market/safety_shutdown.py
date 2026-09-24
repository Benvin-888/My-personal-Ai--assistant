"""Fail-closed automatic safety shutdown and execution-admission lock for APEX.

Phase 2.66 is an execution-admission safety boundary.  It can revoke new live
execution authority when configured critical conditions are observed, but it
cannot place, modify, cancel, or close broker positions and it cannot reset
itself automatically.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


class SafetyState(str, Enum):
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    LOCKED = "LOCKED"
    RESET_PENDING = "RESET_PENDING"


class SafetySeverity(str, Enum):
    WARNING = "WARNING"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    INVALID = "INVALID"


class ShutdownScope(str, Enum):
    STRATEGY = "STRATEGY"
    SYMBOL = "SYMBOL"
    PORTFOLIO = "PORTFOLIO"
    ACCOUNT = "ACCOUNT"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class SafetyTrigger:
    trigger_id: str
    source: str
    severity: SafetySeverity
    scope: ShutdownScope
    reason_code: str
    detail: str = ""
    source_fingerprint: str = ""


@dataclass(frozen=True)
class SafetyObservation:
    observation_id: str
    observed_at: str
    execution_mode: str
    account_scope: str
    broker: str
    connection_healthy: bool | None
    authenticated: bool | None
    reconciliation_pending: int | None = 0
    unknown_outcomes: int | None = 0
    failed_outcomes: int | None = 0
    operational_error_count: int | None = 0
    warning_count: int | None = 0
    strategy_degraded: bool = False
    safety_state_available: bool = True
    risk_state_available: bool = True
    portfolio_state_available: bool = True
    eligibility_valid: bool = True


@dataclass(frozen=True)
class SafetyCriteria:
    require_live_mode: bool = True
    require_authenticated: bool = True
    require_connection_healthy: bool = True
    require_reconciled_state: bool = True
    require_safety_state_available: bool = True
    require_risk_state_available: bool = True
    require_portfolio_state_available: bool = True
    require_valid_eligibility: bool = True
    max_reconciliation_pending: int = 0
    max_unknown_outcomes: int = 0
    max_failed_outcomes: int = 0
    max_operational_error_count: int = 0
    max_warning_count: int | None = None
    strategy_degradation_scope: ShutdownScope = ShutdownScope.STRATEGY


@dataclass(frozen=True)
class SafetyAssessment:
    state: SafetyState
    severity: SafetySeverity
    execution_admission_allowed: bool
    scope: ShutdownScope | None
    reasons: tuple[str, ...]
    triggers: tuple[SafetyTrigger, ...]
    observation_fingerprint: str
    criteria_fingerprint: str
    assessment_fingerprint: str
    execution_authorized: bool = False


@dataclass(frozen=True)
class SafetyLock:
    lock_id: str
    state: SafetyState
    scope: ShutdownScope
    triggered_at: str
    reasons: tuple[str, ...]
    shutdown_fingerprint: str
    execution_admission_allowed: bool = False


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: _canonical(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, set):
        return sorted(_canonical(v) for v in value)
    if isinstance(value, float):
        return value if math.isfinite(value) else "<non_finite>"
    return value


def _fingerprint(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_criteria(criteria: SafetyCriteria) -> list[str]:
    reasons: list[str] = []
    for name in (
        "max_reconciliation_pending",
        "max_unknown_outcomes",
        "max_failed_outcomes",
        "max_operational_error_count",
    ):
        if not _valid_nonnegative_int(getattr(criteria, name)):
            reasons.append(f"invalid_{name}")
    if criteria.max_warning_count is not None and not _valid_nonnegative_int(criteria.max_warning_count):
        reasons.append("invalid_max_warning_count")
    if not isinstance(criteria.strategy_degradation_scope, ShutdownScope):
        reasons.append("invalid_strategy_degradation_scope")
    return reasons


def _validate_observation(observation: SafetyObservation) -> list[str]:
    reasons: list[str] = []
    if not observation.observation_id.strip():
        reasons.append("missing_observation_id")
    if not observation.observed_at.strip():
        reasons.append("missing_observed_at")
    if not observation.account_scope.strip():
        reasons.append("missing_account_scope")
    if not observation.broker.strip():
        reasons.append("missing_broker")
    for name in (
        "reconciliation_pending",
        "unknown_outcomes",
        "failed_outcomes",
        "operational_error_count",
        "warning_count",
    ):
        value = getattr(observation, name)
        if value is not None and not _valid_nonnegative_int(value):
            reasons.append(f"invalid_{name}")
    return reasons


def _trigger(
    observation: SafetyObservation,
    source: str,
    severity: SafetySeverity,
    scope: ShutdownScope,
    reason_code: str,
    detail: str = "",
) -> SafetyTrigger:
    payload = {
        "observation": observation.observation_id,
        "source": source,
        "severity": severity,
        "scope": scope,
        "reason_code": reason_code,
        "detail": detail,
    }
    return SafetyTrigger(
        trigger_id=_fingerprint(payload)[:24],
        source=source,
        severity=severity,
        scope=scope,
        reason_code=reason_code,
        detail=detail,
        source_fingerprint=_fingerprint(payload),
    )


def assess_safety(
    criteria: SafetyCriteria,
    observation: SafetyObservation,
    additional_triggers: Sequence[SafetyTrigger] = (),
) -> SafetyAssessment:
    """Evaluate safety admission without performing any broker action."""
    criteria_fp = _fingerprint(criteria)
    observation_fp = _fingerprint(observation)
    invalid = _validate_criteria(criteria) + _validate_observation(observation)
    triggers: list[SafetyTrigger] = list(additional_triggers)

    if invalid:
        triggers.append(_trigger(observation, "2.66", SafetySeverity.INVALID, ShutdownScope.SYSTEM, "invalid_safety_input", ";".join(sorted(set(invalid)))))
    else:
        if criteria.require_safety_state_available and not observation.safety_state_available:
            triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.SYSTEM, "safety_state_unavailable"))
        if criteria.require_risk_state_available and not observation.risk_state_available:
            triggers.append(_trigger(observation, "risk", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "risk_state_unavailable"))
        if criteria.require_portfolio_state_available and not observation.portfolio_state_available:
            triggers.append(_trigger(observation, "2.63", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "portfolio_state_unavailable"))
        if criteria.require_live_mode and observation.execution_mode.upper() != "LIVE":
            triggers.append(_trigger(observation, "execution_mode", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "live_mode_required"))
        if criteria.require_authenticated and observation.authenticated is not True:
            triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "authentication_not_verified"))
        if criteria.require_connection_healthy and observation.connection_healthy is not True:
            triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "connection_not_healthy"))
        if criteria.require_reconciled_state:
            pending = observation.reconciliation_pending
            unknown = observation.unknown_outcomes
            if pending is None:
                triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "reconciliation_state_unknown"))
            elif pending > criteria.max_reconciliation_pending:
                triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "reconciliation_backlog_exceeded"))
            if unknown is None:
                triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "unknown_outcome_state_unknown"))
            elif unknown > criteria.max_unknown_outcomes:
                triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "unknown_outcomes_exceeded"))
        if observation.failed_outcomes is None:
            triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "failed_outcome_state_unknown"))
        elif observation.failed_outcomes > criteria.max_failed_outcomes:
            triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "failed_outcomes_exceeded"))
        if observation.operational_error_count is None:
            triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "operational_error_state_unknown"))
        elif observation.operational_error_count > criteria.max_operational_error_count:
            triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "operational_errors_exceeded"))
        if criteria.max_warning_count is not None:
            if observation.warning_count is None:
                triggers.append(_trigger(observation, "2.64", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "warning_state_unknown"))
            elif observation.warning_count > criteria.max_warning_count:
                triggers.append(_trigger(observation, "2.64", SafetySeverity.DEGRADED, ShutdownScope.ACCOUNT, "warning_limit_exceeded"))
        if criteria.require_valid_eligibility and not observation.eligibility_valid:
            triggers.append(_trigger(observation, "2.62", SafetySeverity.CRITICAL, ShutdownScope.ACCOUNT, "eligibility_invalid"))
        if observation.strategy_degraded:
            triggers.append(_trigger(observation, "2.65", SafetySeverity.DEGRADED, criteria.strategy_degradation_scope, "strategy_degraded"))

    critical = [t for t in triggers if t.severity in (SafetySeverity.CRITICAL, SafetySeverity.INVALID)]
    degraded = [t for t in triggers if t.severity is SafetySeverity.DEGRADED]
    warnings = [t for t in triggers if t.severity is SafetySeverity.WARNING]

    if critical:
        state = SafetyState.TRIGGERED
        severity = SafetySeverity.CRITICAL if any(t.severity is SafetySeverity.CRITICAL for t in critical) else SafetySeverity.INVALID
        scope = _widest_scope(critical)
        allowed = False
    elif degraded:
        state = SafetyState.TRIGGERED
        severity = SafetySeverity.DEGRADED
        scope = _widest_scope(degraded)
        allowed = False
    elif warnings:
        state = SafetyState.ARMED
        severity = SafetySeverity.WARNING
        scope = None
        allowed = True
    else:
        state = SafetyState.ARMED
        severity = SafetySeverity.WARNING
        scope = None
        allowed = True

    reasons = tuple(sorted({t.reason_code for t in triggers}))
    if not reasons:
        reasons = ("no_safety_trigger",)
    assessment_data = {
        "state": state,
        "severity": severity,
        "execution_admission_allowed": allowed,
        "scope": scope,
        "reasons": reasons,
        "triggers": triggers,
        "observation_fingerprint": observation_fp,
        "criteria_fingerprint": criteria_fp,
    }
    return SafetyAssessment(
        state=state,
        severity=severity,
        execution_admission_allowed=allowed,
        scope=scope,
        reasons=reasons,
        triggers=tuple(triggers),
        observation_fingerprint=observation_fp,
        criteria_fingerprint=criteria_fp,
        assessment_fingerprint=_fingerprint(assessment_data),
        execution_authorized=False,
    )


def _widest_scope(triggers: Sequence[SafetyTrigger]) -> ShutdownScope:
    order = {
        ShutdownScope.STRATEGY: 1,
        ShutdownScope.SYMBOL: 2,
        ShutdownScope.PORTFOLIO: 3,
        ShutdownScope.ACCOUNT: 4,
        ShutdownScope.SYSTEM: 5,
    }
    return max((t.scope for t in triggers), key=lambda scope: order[scope])


def trigger_lock(
    assessment: SafetyAssessment,
    lock_id: str,
    triggered_at: str,
) -> SafetyLock:
    """Create a latched lock from a non-admissible safety assessment."""
    if assessment.execution_admission_allowed:
        raise ValueError("safe assessment cannot create a shutdown lock")
    if not lock_id.strip() or not triggered_at.strip():
        raise ValueError("lock_id and triggered_at are required")
    if assessment.scope is None:
        raise ValueError("shutdown scope is required")
    payload = {
        "lock_id": lock_id,
        "state": SafetyState.LOCKED,
        "scope": assessment.scope,
        "triggered_at": triggered_at,
        "reasons": assessment.reasons,
        "assessment": assessment.assessment_fingerprint,
    }
    return SafetyLock(
        lock_id=lock_id,
        state=SafetyState.LOCKED,
        scope=assessment.scope,
        triggered_at=triggered_at,
        reasons=assessment.reasons,
        shutdown_fingerprint=_fingerprint(payload),
        execution_admission_allowed=False,
    )


def request_reset(lock: SafetyLock) -> SafetyLock:
    """Move a lock to RESET_PENDING; this never arms execution by itself."""
    if lock.state is not SafetyState.LOCKED:
        raise ValueError("only a LOCKED safety state can request reset")
    payload = {"lock": lock, "next_state": SafetyState.RESET_PENDING}
    return SafetyLock(
        lock_id=lock.lock_id,
        state=SafetyState.RESET_PENDING,
        scope=lock.scope,
        triggered_at=lock.triggered_at,
        reasons=lock.reasons,
        shutdown_fingerprint=_fingerprint(payload),
        execution_admission_allowed=False,
    )


def rearm_after_explicit_validation(
    lock: SafetyLock,
    validation_passed: bool,
    explicit_reset: bool,
) -> bool:
    """Return whether re-arming is permitted; never mutates or authorizes execution."""
    return (
        lock.state is SafetyState.RESET_PENDING
        and validation_passed is True
        and explicit_reset is True
    )


def safety_assessment_is_not_execution_authorization(assessment: SafetyAssessment) -> bool:
    return assessment.execution_authorized is False


def safety_lock_is_not_execution_authorization(lock: SafetyLock) -> bool:
    return lock.execution_admission_allowed is False
