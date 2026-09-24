"""Deterministic live-monitoring boundary for APEX.

Phase 2.64 observes controlled-live operational state and evidence. It does not
place, modify, cancel, or authorize trades and has no broker credential access.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


class MonitoringStatus(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_STATE = "INVALID_STATE"


@dataclass(frozen=True)
class LivePositionObservation:
    trade_id: str
    symbol: str
    direction: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float | None = None
    risk_amount: float | None = None


@dataclass(frozen=True)
class LiveOperationalObservation:
    observation_id: str
    observed_at: str
    execution_mode: str
    account_scope: str
    broker: str
    connection_healthy: bool
    authenticated: bool
    positions: Sequence[LivePositionObservation]
    last_execution_age_seconds: float | None = None
    reconciliation_pending: int = 0
    unknown_outcomes: int = 0
    failed_outcomes: int = 0
    error_count: int = 0
    warning_count: int = 0


@dataclass(frozen=True)
class LiveMonitoringCriteria:
    max_reconciliation_pending: int = 0
    max_unknown_outcomes: int = 0
    max_failed_outcomes: int = 0
    max_error_count: int = 0
    max_warning_count: int | None = None
    max_position_count: int | None = None
    max_total_risk: float | None = None
    stale_execution_age_seconds: float | None = None
    require_authenticated: bool = True
    require_connection_healthy: bool = True
    require_live_mode: bool = True


@dataclass(frozen=True)
class LiveMonitoringAssessment:
    status: MonitoringStatus
    reasons: tuple[str, ...]
    position_count: int
    total_risk: float | None
    pending_reconciliation: int
    unknown_outcomes: int
    failed_outcomes: int
    error_count: int
    warning_count: int
    criteria_fingerprint: str
    observation_fingerprint: str
    assessment_fingerprint: str
    execution_authorized: bool = False


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


def _validate(criteria: LiveMonitoringCriteria, observation: LiveOperationalObservation) -> list[str]:
    reasons: list[str] = []
    nonnegative_ints = {
        "max_reconciliation_pending": criteria.max_reconciliation_pending,
        "max_unknown_outcomes": criteria.max_unknown_outcomes,
        "max_failed_outcomes": criteria.max_failed_outcomes,
        "max_error_count": criteria.max_error_count,
        "max_warning_count": criteria.max_warning_count,
        "max_position_count": criteria.max_position_count,
    }
    for name, value in nonnegative_ints.items():
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            reasons.append(f"invalid_{name}")
    for name, value in {"max_total_risk": criteria.max_total_risk, "stale_execution_age_seconds": criteria.stale_execution_age_seconds}.items():
        if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0):
            reasons.append(f"invalid_{name}")
    if not observation.observation_id.strip() or not observation.observed_at.strip() or not observation.broker.strip() or not observation.account_scope.strip():
        reasons.append("missing_observation_identity")
    if not observation.execution_mode.strip():
        reasons.append("missing_execution_mode")
    if observation.reconciliation_pending < 0 or observation.unknown_outcomes < 0 or observation.failed_outcomes < 0 or observation.error_count < 0 or observation.warning_count < 0:
        reasons.append("invalid_operational_counts")
    if observation.last_execution_age_seconds is not None and (not math.isfinite(float(observation.last_execution_age_seconds)) or observation.last_execution_age_seconds < 0):
        reasons.append("invalid_execution_age")
    seen: set[str] = set()
    for position in observation.positions:
        if not position.trade_id.strip() or position.trade_id in seen:
            reasons.append("invalid_or_duplicate_position_id")
        seen.add(position.trade_id)
        if not position.symbol.strip() or not position.direction.strip():
            reasons.append("invalid_position_identity")
        for name, value in {"quantity": position.quantity, "entry_price": position.entry_price, "current_price": position.current_price}.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0:
                reasons.append(f"invalid_position_{name}")
        for name, value in {"unrealized_pnl": position.unrealized_pnl, "risk_amount": position.risk_amount}.items():
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value))):
                reasons.append(f"invalid_position_{name}")
            if name == "risk_amount" and value is not None and float(value) < 0:
                reasons.append("invalid_position_risk_amount")
    return sorted(set(reasons))


def assess_live_monitoring(criteria: LiveMonitoringCriteria, observation: LiveOperationalObservation) -> LiveMonitoringAssessment:
    """Assess observed operational state; never authorizes execution."""
    validation = _validate(criteria, observation)
    criteria_fp = _fingerprint(criteria)
    observation_fp = _fingerprint(observation)
    if validation:
        return _assessment(MonitoringStatus.INVALID_STATE, tuple(validation), len(observation.positions), None, observation, criteria_fp, observation_fp)

    total_risk: float | None = None
    risk_values = [p.risk_amount for p in observation.positions if p.risk_amount is not None]
    if risk_values:
        if len(risk_values) == len(observation.positions):
            total_risk = sum(float(v) for v in risk_values)
    reasons: list[str] = []
    if criteria.require_live_mode and observation.execution_mode.upper() != "LIVE":
        reasons.append("not_live_mode")
    if criteria.require_authenticated and not observation.authenticated:
        reasons.append("authentication_unhealthy")
    if criteria.require_connection_healthy and not observation.connection_healthy:
        reasons.append("connection_unhealthy")
    if observation.reconciliation_pending > criteria.max_reconciliation_pending:
        reasons.append("reconciliation_pending_limit_exceeded")
    if observation.unknown_outcomes > criteria.max_unknown_outcomes:
        reasons.append("unknown_outcome_limit_exceeded")
    if observation.failed_outcomes > criteria.max_failed_outcomes:
        reasons.append("failed_outcome_limit_exceeded")
    if observation.error_count > criteria.max_error_count:
        reasons.append("error_limit_exceeded")
    if criteria.max_warning_count is not None and observation.warning_count > criteria.max_warning_count:
        reasons.append("warning_limit_exceeded")
    if criteria.max_position_count is not None and len(observation.positions) > criteria.max_position_count:
        reasons.append("position_count_limit_exceeded")
    if criteria.max_total_risk is not None:
        if total_risk is None and observation.positions:
            reasons.append("risk_data_missing")
        elif total_risk is not None and total_risk > criteria.max_total_risk:
            reasons.append("total_risk_limit_exceeded")
    if criteria.stale_execution_age_seconds is not None and observation.last_execution_age_seconds is not None and observation.last_execution_age_seconds > criteria.stale_execution_age_seconds:
        reasons.append("execution_observation_stale")
    elif criteria.stale_execution_age_seconds is not None and observation.last_execution_age_seconds is None:
        reasons.append("execution_age_missing")

    if "risk_data_missing" in reasons or "execution_age_missing" in reasons:
        status = MonitoringStatus.INSUFFICIENT_DATA
    elif any(r in reasons for r in ("connection_unhealthy", "authentication_unhealthy", "unknown_outcome_limit_exceeded", "reconciliation_pending_limit_exceeded")):
        status = MonitoringStatus.CRITICAL
    elif any(r.endswith("limit_exceeded") or r in {"error_limit_exceeded", "not_live_mode", "execution_observation_stale"} for r in reasons):
        status = MonitoringStatus.WARNING
    elif reasons:
        status = MonitoringStatus.WARNING
    else:
        status = MonitoringStatus.HEALTHY
        reasons = ["all_configured_monitoring_constraints_satisfied"]
    return _assessment(status, tuple(reasons), len(observation.positions), total_risk, observation, criteria_fp, observation_fp)


def _assessment(status, reasons, position_count, total_risk, observation, criteria_fp, observation_fp):
    fp = _fingerprint({"status": status.value, "reasons": reasons, "criteria": criteria_fp, "observation": observation_fp})
    return LiveMonitoringAssessment(status, tuple(reasons), position_count, total_risk, observation.reconciliation_pending, observation.unknown_outcomes, observation.failed_outcomes, observation.error_count, observation.warning_count, criteria_fp, observation_fp, fp, False)


def monitoring_assessment_is_not_execution_authorization(assessment: LiveMonitoringAssessment) -> bool:
    return assessment.execution_authorized is False
