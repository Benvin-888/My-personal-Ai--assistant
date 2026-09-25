"""Phase 2.71 controlled capital and risk budgeting boundary.

Point-in-time, fail-closed budgeting of capital and risk capacity. This module
never authorizes execution, predicts returns, or communicates with a broker.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


class CapitalRiskBudgetStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID = "INVALID"
    EXCEEDED = "EXCEEDED"


@dataclass(frozen=True)
class CapitalRiskSnapshot:
    observed_at: str
    account_scope: str
    account_balance: float | None
    reserved_capital: float | None
    committed_capital: float | None
    committed_risk: float | None
    capital_budget: float | None = None
    risk_budget: float | None = None
    source_fingerprint: str = ""


@dataclass(frozen=True)
class StrategyBudgetAllocation:
    strategy_id: str
    strategy_version: str
    allocated_capital: float
    allocated_risk: float


@dataclass(frozen=True)
class CapitalRiskBudgetCriteria:
    max_deployable_capital: float | None = None
    max_total_risk: float | None = None
    max_strategy_capital: float | None = None
    max_strategy_risk: float | None = None
    require_explicit_capital_budget: bool = True
    require_explicit_risk_budget: bool = True
    allow_balance_as_capital_budget: bool = False
    require_fresh_snapshot_seconds: float | None = None
    criteria_version: str = "2.71.0"


@dataclass(frozen=True)
class ProposedBudgetUse:
    strategy_id: str
    strategy_version: str
    capital_required: float
    risk_required: float


@dataclass(frozen=True)
class CapitalRiskBudgetAssessment:
    status: CapitalRiskBudgetStatus
    reasons: tuple[str, ...]
    account_scope: str
    available_capital: float | None
    available_risk: float | None
    projected_capital_used: float | None
    projected_risk_used: float | None
    remaining_capital: float | None
    remaining_risk: float | None
    strategy_capital_used: float | None
    strategy_risk_used: float | None
    criteria_fingerprint: str
    snapshot_fingerprint: str
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
        return value if math.isfinite(value) else "<non_finite>"
    return value


def fingerprint(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _number(value: Any, name: str, positive: bool = False) -> str | None:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return f"invalid_{name}"
    if float(value) < 0 or (positive and float(value) <= 0):
        return f"invalid_{name}"
    return None


def assess_capital_risk_budget(
    snapshot: CapitalRiskSnapshot,
    allocations: Sequence[StrategyBudgetAllocation],
    proposed: ProposedBudgetUse,
    criteria: CapitalRiskBudgetCriteria,
) -> CapitalRiskBudgetAssessment:
    reasons: list[str] = []
    if not snapshot.account_scope.strip() or not snapshot.observed_at.strip():
        reasons.append("missing_snapshot_identity")
    if not proposed.strategy_id.strip() or not proposed.strategy_version.strip():
        reasons.append("missing_proposed_strategy_identity")
    for name, value in (
        ("capital_required", proposed.capital_required),
        ("risk_required", proposed.risk_required),
    ):
        err = _number(value, name, positive=True)
        if err:
            reasons.append(err)
    for name, value in (
        ("account_balance", snapshot.account_balance),
        ("reserved_capital", snapshot.reserved_capital),
        ("committed_capital", snapshot.committed_capital),
        ("committed_risk", snapshot.committed_risk),
        ("capital_budget", snapshot.capital_budget),
        ("risk_budget", snapshot.risk_budget),
    ):
        if value is not None:
            err = _number(value, name)
            if err:
                reasons.append(err)
    for name, value in (
        ("max_deployable_capital", criteria.max_deployable_capital),
        ("max_total_risk", criteria.max_total_risk),
        ("max_strategy_capital", criteria.max_strategy_capital),
        ("max_strategy_risk", criteria.max_strategy_risk),
        ("require_fresh_snapshot_seconds", criteria.require_fresh_snapshot_seconds),
    ):
        if value is not None:
            err = _number(value, name)
            if err:
                reasons.append(err)

    snapshot_fp = fingerprint(snapshot)
    allocations_fp = fingerprint(tuple(allocations))
    proposed_fp = fingerprint(proposed)
    criteria_fp = fingerprint(criteria)

    for item in allocations:
        if not item.strategy_id.strip() or not item.strategy_version.strip():
            reasons.append("invalid_strategy_allocation_identity")
        for name, value in (("allocated_capital", item.allocated_capital), ("allocated_risk", item.allocated_risk)):
            err = _number(value, name)
            if err:
                reasons.append(err)

    # A budget must be explicit unless the caller deliberately permits balance fallback.
    if snapshot.capital_budget is None and criteria.require_explicit_capital_budget and not criteria.allow_balance_as_capital_budget:
        reasons.append("capital_budget_missing")
    if snapshot.risk_budget is None and criteria.require_explicit_risk_budget:
        reasons.append("risk_budget_missing")

    available_capital: float | None = snapshot.capital_budget
    available_risk: float | None = snapshot.risk_budget
    if available_capital is None and criteria.allow_balance_as_capital_budget and snapshot.account_balance is not None:
        reserved = snapshot.reserved_capital or 0.0
        committed = snapshot.committed_capital or 0.0
        available_capital = snapshot.account_balance - reserved - committed

    if available_capital is not None and criteria.max_deployable_capital is not None:
        available_capital = min(available_capital, criteria.max_deployable_capital)
    if available_risk is not None and criteria.max_total_risk is not None:
        available_risk = min(available_risk, criteria.max_total_risk)

    capital_used = sum(x.allocated_capital for x in allocations)
    risk_used = sum(x.allocated_risk for x in allocations)
    projected_capital = capital_used + proposed.capital_required
    projected_risk = risk_used + proposed.risk_required
    strategy_capital = sum(x.allocated_capital for x in allocations if x.strategy_id == proposed.strategy_id and x.strategy_version == proposed.strategy_version) + proposed.capital_required
    strategy_risk = sum(x.allocated_risk for x in allocations if x.strategy_id == proposed.strategy_id and x.strategy_version == proposed.strategy_version) + proposed.risk_required

    if available_capital is not None and projected_capital > available_capital:
        reasons.append("capital_budget_exceeded")
    if available_risk is not None and projected_risk > available_risk:
        reasons.append("risk_budget_exceeded")
    if criteria.max_strategy_capital is not None and strategy_capital > criteria.max_strategy_capital:
        reasons.append("strategy_capital_budget_exceeded")
    if criteria.max_strategy_risk is not None and strategy_risk > criteria.max_strategy_risk:
        reasons.append("strategy_risk_budget_exceeded")

    if reasons:
        missing = any("missing" in r for r in reasons)
        invalid = any(r.startswith("invalid_") or r == "missing_snapshot_identity" or r == "missing_proposed_strategy_identity" for r in reasons)
        exceeded = any("exceeded" in r for r in reasons)
        if invalid:
            status = CapitalRiskBudgetStatus.INVALID
        elif missing:
            status = CapitalRiskBudgetStatus.INSUFFICIENT_DATA
        elif exceeded:
            status = CapitalRiskBudgetStatus.EXCEEDED
        else:
            status = CapitalRiskBudgetStatus.LIMITED
    else:
        status = CapitalRiskBudgetStatus.AVAILABLE if available_capital is not None and available_risk is not None else CapitalRiskBudgetStatus.INSUFFICIENT_DATA
        if status == CapitalRiskBudgetStatus.AVAILABLE and (available_capital - projected_capital < 0 or available_risk - projected_risk < 0):
            status = CapitalRiskBudgetStatus.EXCEEDED
            reasons.append("budget_exceeded")
        elif status == CapitalRiskBudgetStatus.AVAILABLE:
            reasons = ["all_configured_capital_and_risk_constraints_satisfied"]

    remaining_capital = available_capital - projected_capital if available_capital is not None else None
    remaining_risk = available_risk - projected_risk if available_risk is not None else None
    assessment_data = {
        "status": status.value,
        "reasons": tuple(sorted(set(reasons))),
        "criteria": criteria_fp,
        "snapshot": snapshot_fp,
        "allocations": allocations_fp,
        "proposed": proposed_fp,
    }
    assessment_fp = fingerprint(assessment_data)
    return CapitalRiskBudgetAssessment(
        status, tuple(sorted(set(reasons))), snapshot.account_scope, available_capital, available_risk,
        projected_capital if available_capital is not None else None,
        projected_risk if available_risk is not None else None,
        remaining_capital, remaining_risk, strategy_capital, strategy_risk,
        criteria_fp, snapshot_fp, allocations_fp, proposed_fp, assessment_fp, False,
    )


def capital_risk_budget_is_not_execution_authorization(assessment: CapitalRiskBudgetAssessment) -> bool:
    return assessment.execution_authorized is False
