"""Phase 2.70 controlled strategy allocation boundary.

This module assigns an explicit, auditable allocation/risk budget to strategies
that have already passed lifecycle and evidence gates. It does not select a
strategy, predict returns, authorize execution, or communicate with a broker.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from .strategy_lifecycle import StrategyLifecycleStage


class StrategyAllocationStatus(str, Enum):
    APPROVED = "APPROVED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_ALLOCATION = "INVALID_ALLOCATION"
    LIFECYCLE_BLOCKED = "LIFECYCLE_BLOCKED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    CONCENTRATION_EXCEEDED = "CONCENTRATION_EXCEEDED"
    CORRELATION_LIMIT_EXCEEDED = "CORRELATION_LIMIT_EXCEEDED"


@dataclass(frozen=True)
class StrategyAllocation:
    strategy_id: str
    strategy_version: str
    allocation_amount: float
    risk_budget: float
    lifecycle_stage: StrategyLifecycleStage


@dataclass(frozen=True)
class ProposedStrategyAllocation:
    strategy_id: str
    strategy_version: str
    allocation_amount: float
    risk_budget: float
    lifecycle_stage: StrategyLifecycleStage


@dataclass(frozen=True)
class StrategyAllocationCriteria:
    max_total_allocation: float | None = None
    max_strategy_allocation: float | None = None
    max_total_risk_budget: float | None = None
    max_strategy_risk_budget: float | None = None
    max_strategy_concentration_ratio: float | None = None
    max_correlated_risk_budget: float | None = None
    minimum_correlation_for_cluster: float = 0.70
    minimum_allocation_amount: float | None = None
    minimum_risk_budget: float | None = None
    require_eligible_lifecycle: bool = True
    allowed_lifecycle_stages: tuple[StrategyLifecycleStage, ...] = (
        StrategyLifecycleStage.ELIGIBLE,
        StrategyLifecycleStage.LIMITED_LIVE,
        StrategyLifecycleStage.MONITORING,
    )
    require_correlation_data: bool = False
    criteria_version: str = "2.70.0"


@dataclass(frozen=True)
class StrategyAllocationAssessment:
    status: StrategyAllocationStatus
    reasons: tuple[str, ...]
    current_total_allocation: float
    projected_total_allocation: float
    current_total_risk_budget: float
    projected_total_risk_budget: float
    strategy_allocation: float
    strategy_risk_budget: float
    concentration_ratio: float | None
    correlated_risk_budget: float | None
    criteria_fingerprint: str
    allocations_fingerprint: str
    proposed_fingerprint: str
    assessment_fingerprint: str
    execution_authorized: bool = False


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: _canonical(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, set):
        return sorted(_canonical(v) for v in value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return "<non_finite>"
        return value
    return value


def fingerprint(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_number(value: float, field: str, allow_zero: bool = True) -> str | None:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return f"invalid_{field}"
    if value < 0 or (not allow_zero and value == 0):
        return f"invalid_{field}"
    return None


def _validate(criteria: StrategyAllocationCriteria, allocations: Sequence[StrategyAllocation], proposed: ProposedStrategyAllocation) -> tuple[str, ...]:
    reasons: list[str] = []
    limits = {
        "max_total_allocation": criteria.max_total_allocation,
        "max_strategy_allocation": criteria.max_strategy_allocation,
        "max_total_risk_budget": criteria.max_total_risk_budget,
        "max_strategy_risk_budget": criteria.max_strategy_risk_budget,
        "max_strategy_concentration_ratio": criteria.max_strategy_concentration_ratio,
        "max_correlated_risk_budget": criteria.max_correlated_risk_budget,
        "minimum_allocation_amount": criteria.minimum_allocation_amount,
        "minimum_risk_budget": criteria.minimum_risk_budget,
    }
    for name, value in limits.items():
        if value is not None:
            err = _validate_number(float(value), name)
            if err:
                reasons.append(err)
    if not math.isfinite(criteria.minimum_correlation_for_cluster) or not 0 <= criteria.minimum_correlation_for_cluster <= 1:
        reasons.append("invalid_minimum_correlation")
    if not proposed.strategy_id.strip() or not proposed.strategy_version.strip():
        reasons.append("missing_proposed_identity")
    for field, value in (("proposed_allocation_amount", proposed.allocation_amount), ("proposed_risk_budget", proposed.risk_budget)):
        err = _validate_number(value, field, allow_zero=False)
        if err:
            reasons.append(err)
    if criteria.minimum_allocation_amount is not None and proposed.allocation_amount < criteria.minimum_allocation_amount:
        reasons.append("proposed_allocation_below_minimum")
    if criteria.minimum_risk_budget is not None and proposed.risk_budget < criteria.minimum_risk_budget:
        reasons.append("proposed_risk_budget_below_minimum")
    seen: set[tuple[str, str]] = set()
    for item in allocations:
        key = (item.strategy_id, item.strategy_version)
        if not item.strategy_id.strip() or not item.strategy_version.strip() or key in seen:
            reasons.append("invalid_or_duplicate_strategy_allocation")
        seen.add(key)
        for field, value in (("allocation_amount", item.allocation_amount), ("risk_budget", item.risk_budget)):
            err = _validate_number(value, field)
            if err:
                reasons.append(err)
    if criteria.require_eligible_lifecycle and proposed.lifecycle_stage not in criteria.allowed_lifecycle_stages:
        reasons.append("proposed_lifecycle_stage_not_allocatable")
    return tuple(sorted(set(reasons)))


def _correlation_for(a: str, b: str, matrix: Mapping[str, Mapping[str, float]]) -> float | None:
    if a == b:
        return 1.0
    if a in matrix and b in matrix[a]:
        return float(matrix[a][b])
    if b in matrix and a in matrix[b]:
        return float(matrix[b][a])
    return None


def assess_strategy_allocation(
    criteria: StrategyAllocationCriteria,
    allocations: Sequence[StrategyAllocation],
    proposed: ProposedStrategyAllocation,
    correlation_matrix: Mapping[str, Mapping[str, float]] | None = None,
) -> StrategyAllocationAssessment:
    """Assess a strategy allocation against explicit budgets; never authorizes execution."""
    matrix = correlation_matrix or {}
    criteria_fp = fingerprint(criteria)
    allocations_fp = fingerprint(tuple(allocations))
    proposed_fp = fingerprint(proposed)
    validation = _validate(criteria, allocations, proposed)
    current_total = sum(a.allocation_amount for a in allocations if math.isfinite(a.allocation_amount))
    current_risk = sum(a.risk_budget for a in allocations if math.isfinite(a.risk_budget))
    projected_total = current_total + proposed.allocation_amount if math.isfinite(proposed.allocation_amount) else current_total
    projected_risk = current_risk + proposed.risk_budget if math.isfinite(proposed.risk_budget) else current_risk
    strategy_total = sum(a.allocation_amount for a in allocations if a.strategy_id == proposed.strategy_id and a.strategy_version == proposed.strategy_version) + proposed.allocation_amount
    strategy_risk = sum(a.risk_budget for a in allocations if a.strategy_id == proposed.strategy_id and a.strategy_version == proposed.strategy_version) + proposed.risk_budget
    concentration = strategy_total / projected_total if projected_total > 0 else None
    if validation:
        status = StrategyAllocationStatus.LIFECYCLE_BLOCKED if "proposed_lifecycle_stage_not_allocatable" in validation and len(validation) == 1 else StrategyAllocationStatus.INVALID_ALLOCATION
        return _assessment(status, validation, current_total, projected_total, current_risk, projected_risk, strategy_total, strategy_risk, concentration, None, criteria_fp, allocations_fp, proposed_fp)

    reasons: list[str] = []
    if criteria.max_total_allocation is not None and projected_total > criteria.max_total_allocation:
        reasons.append("total_allocation_limit_exceeded")
    if criteria.max_strategy_allocation is not None and strategy_total > criteria.max_strategy_allocation:
        reasons.append("strategy_allocation_limit_exceeded")
    if criteria.max_total_risk_budget is not None and projected_risk > criteria.max_total_risk_budget:
        reasons.append("total_risk_budget_limit_exceeded")
    if criteria.max_strategy_risk_budget is not None and strategy_risk > criteria.max_strategy_risk_budget:
        reasons.append("strategy_risk_budget_limit_exceeded")
    if criteria.max_strategy_concentration_ratio is not None and concentration is not None and concentration > criteria.max_strategy_concentration_ratio:
        reasons.append("strategy_concentration_limit_exceeded")

    correlated_risk: float | None = None
    correlated: list[StrategyAllocation] = []
    missing_corr = False
    for item in allocations:
        corr = _correlation_for(item.strategy_id, proposed.strategy_id, matrix)
        if corr is None:
            missing_corr = True
        elif abs(corr) >= criteria.minimum_correlation_for_cluster:
            correlated.append(item)
    if correlated or (criteria.require_correlation_data and allocations and missing_corr):
        correlated_risk = proposed.risk_budget + sum(a.risk_budget for a in correlated)
    if criteria.require_correlation_data and allocations and missing_corr:
        reasons.append("correlation_data_missing")
    elif criteria.max_correlated_risk_budget is not None and correlated_risk is not None and correlated_risk > criteria.max_correlated_risk_budget:
        reasons.append("correlated_risk_budget_limit_exceeded")

    if "correlation_data_missing" in reasons:
        status = StrategyAllocationStatus.INSUFFICIENT_DATA
    elif "correlated_risk_budget_limit_exceeded" in reasons:
        status = StrategyAllocationStatus.CORRELATION_LIMIT_EXCEEDED
    elif any(r.endswith("risk_budget_limit_exceeded") for r in reasons):
        status = StrategyAllocationStatus.LIMIT_EXCEEDED
    elif "strategy_concentration_limit_exceeded" in reasons:
        status = StrategyAllocationStatus.CONCENTRATION_EXCEEDED
    elif any(r.endswith("allocation_limit_exceeded") for r in reasons):
        status = StrategyAllocationStatus.LIMIT_EXCEEDED
    else:
        status = StrategyAllocationStatus.APPROVED
        reasons = ["all_configured_allocation_constraints_satisfied"]
    return _assessment(status, tuple(reasons), current_total, projected_total, current_risk, projected_risk, strategy_total, strategy_risk, concentration, correlated_risk, criteria_fp, allocations_fp, proposed_fp)


def _assessment(status, reasons, current_total, projected_total, current_risk, projected_risk, strategy_total, strategy_risk, concentration, correlated_risk, criteria_fp, allocations_fp, proposed_fp):
    fp = fingerprint({"status": status.value, "reasons": reasons, "criteria": criteria_fp, "allocations": allocations_fp, "proposed": proposed_fp})
    return StrategyAllocationAssessment(status, tuple(reasons), current_total, projected_total, current_risk, projected_risk, strategy_total, strategy_risk, concentration, correlated_risk, criteria_fp, allocations_fp, proposed_fp, fp, False)


def allocation_assessment_is_not_execution_authorization(assessment: StrategyAllocationAssessment) -> bool:
    return assessment.execution_authorized is False
