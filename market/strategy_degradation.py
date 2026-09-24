"""Deterministic strategy-degradation detection for APEX.

Phase 2.65 compares a current, prospective evidence cohort with a previously
validated baseline.  It detects material deterioration in observed economic
metrics without predicting future performance, selecting a strategy, or
authorizing execution.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


class DegradationStatus(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    DEGRADED = "DEGRADED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"


@dataclass(frozen=True)
class StrategyOutcome:
    trade_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    timeframe: str
    evidence_class: str
    realized_pnl: float
    risk_amount: float | None = None
    total_costs: float | None = None
    transaction_cost: float | None = None
    slippage_cost: float | None = None
    financing_cost: float | None = None
    won: bool | None = None


@dataclass(frozen=True)
class DegradationCriteria:
    minimum_baseline_records: int = 30
    minimum_current_records: int = 20
    require_cost_coverage: bool = True
    require_risk_coverage: bool = True
    maximum_expectancy_degradation_ratio: float = 0.50
    maximum_win_rate_drop: float = 0.15
    maximum_profit_factor_drop: float = 0.50
    maximum_pnl_to_risk_degradation_ratio: float = 0.50
    minimum_evidence_class: str = "FORWARD"


@dataclass(frozen=True)
class DegradationAssessment:
    status: DegradationStatus
    reasons: tuple[str, ...]
    baseline_records: int
    current_records: int
    baseline_cost_coverage: float
    current_cost_coverage: float
    baseline_risk_coverage: float
    current_risk_coverage: float
    baseline_expectancy: float | None
    current_expectancy: float | None
    baseline_win_rate: float | None
    current_win_rate: float | None
    baseline_profit_factor: float | None
    current_profit_factor: float | None
    baseline_pnl_to_risk: float | None
    current_pnl_to_risk: float | None
    baseline_fingerprint: str
    current_fingerprint: str
    criteria_fingerprint: str
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


def _cost(record: StrategyOutcome) -> float | None:
    if record.total_costs is not None:
        return float(record.total_costs) if _finite_nonnegative(record.total_costs) else None
    parts = (record.transaction_cost, record.slippage_cost, record.financing_cost)
    if all(value is not None for value in parts):
        if all(_finite_nonnegative(value) for value in parts):
            return sum(float(value) for value in parts)
    return None


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _finite_nonnegative(value: Any) -> bool:
    return _finite(value) and float(value) >= 0


def _validate_records(records: Sequence[StrategyOutcome], expected_class: str) -> list[str]:
    reasons: list[str] = []
    seen: set[str] = set()
    for record in records:
        if not record.trade_id.strip() or record.trade_id in seen:
            reasons.append("invalid_or_duplicate_trade_id")
        seen.add(record.trade_id)
        if not record.strategy_id.strip() or not record.strategy_version.strip():
            reasons.append("missing_strategy_identity")
        if not record.symbol.strip() or not record.timeframe.strip():
            reasons.append("missing_market_identity")
        if record.evidence_class.strip().upper() != expected_class.strip().upper():
            reasons.append("evidence_class_mismatch")
        if not _finite(record.realized_pnl):
            reasons.append("invalid_realized_pnl")
        if record.risk_amount is not None and not _finite_nonnegative(record.risk_amount):
            reasons.append("invalid_risk_amount")
        for name in ("total_costs", "transaction_cost", "slippage_cost", "financing_cost"):
            value = getattr(record, name)
            if value is not None and not _finite_nonnegative(value):
                reasons.append(f"invalid_{name}")
    return sorted(set(reasons))


def _summary(records: Sequence[StrategyOutcome]) -> dict[str, float | None]:
    net: list[float] = []
    pnl: list[float] = []
    risks: list[float] = []
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    cost_covered = 0
    risk_covered = 0
    for record in records:
        pnl_value = float(record.realized_pnl)
        pnl.append(pnl_value)
        cost = _cost(record)
        if cost is not None:
            cost_covered += 1
            net_value = pnl_value - cost
            net.append(net_value)
            if net_value > 0:
                gross_profit += net_value
            elif net_value < 0:
                gross_loss += abs(net_value)
        if record.risk_amount is not None:
            risk_covered += 1
            risks.append(float(record.risk_amount))
        outcome = record.won
        if outcome is True:
            wins += 1
        elif outcome is False:
            losses += 1
        elif cost is not None:
            if net[-1] > 0:
                wins += 1
            elif net[-1] < 0:
                losses += 1
    expectancy = sum(net) / len(net) if net else None
    win_rate = wins / (wins + losses) if wins + losses else None
    profit_factor = None if gross_loss == 0 and gross_profit == 0 else (math.inf if gross_loss == 0 else gross_profit / gross_loss)
    pnl_to_risk = sum(net) / sum(risks) if net and risks and len(net) == len(records) and sum(risks) > 0 else None
    return {
        "cost_coverage": cost_covered / len(records) if records else 0.0,
        "risk_coverage": risk_covered / len(records) if records else 0.0,
        "expectancy": expectancy,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "pnl_to_risk": pnl_to_risk,
    }


def _ratio_drop(baseline: float | None, current: float | None) -> float | None:
    if baseline is None or current is None or baseline <= 0:
        return None
    return 1.0 - (current / baseline)


def assess_strategy_degradation(
    criteria: DegradationCriteria,
    baseline: Sequence[StrategyOutcome],
    current: Sequence[StrategyOutcome],
) -> DegradationAssessment:
    """Compare observed cohorts; never grants execution authority."""
    criteria_fp = _fingerprint(criteria)
    baseline_fp = _fingerprint(baseline)
    current_fp = _fingerprint(current)
    validation = _validate_criteria(criteria)
    validation.extend(_validate_records(baseline, criteria.minimum_evidence_class))
    validation.extend(_validate_records(current, criteria.minimum_evidence_class))
    if baseline and current:
        identities = {(r.strategy_id, r.strategy_version, r.symbol, r.timeframe) for r in baseline}
        current_identities = {(r.strategy_id, r.strategy_version, r.symbol, r.timeframe) for r in current}
        if identities != current_identities:
            validation.append("strategy_or_market_identity_mismatch")
    if validation:
        return _make_assessment(DegradationStatus.INVALID_EVIDENCE, tuple(sorted(set(validation))), baseline, current, criteria_fp, baseline_fp, current_fp)

    if len(baseline) < criteria.minimum_baseline_records or len(current) < criteria.minimum_current_records:
        return _make_assessment(DegradationStatus.INSUFFICIENT_DATA, ("minimum_sample_size_not_met",), baseline, current, criteria_fp, baseline_fp, current_fp)

    base = _summary(baseline)
    cur = _summary(current)
    reasons: list[str] = []
    if criteria.require_cost_coverage and (base["cost_coverage"] < 1.0 or cur["cost_coverage"] < 1.0):
        reasons.append("cost_coverage_incomplete")
    if criteria.require_risk_coverage and (base["risk_coverage"] < 1.0 or cur["risk_coverage"] < 1.0):
        reasons.append("risk_coverage_incomplete")
    if reasons:
        return _make_assessment(DegradationStatus.INSUFFICIENT_DATA, tuple(reasons), baseline, current, criteria_fp, baseline_fp, current_fp)

    exp_drop = _ratio_drop(base["expectancy"], cur["expectancy"])
    if base["expectancy"] is not None and base["expectancy"] > 0 and cur["expectancy"] is not None and cur["expectancy"] <= 0:
        reasons.append("expectancy_degraded_to_nonpositive")
    elif exp_drop is not None and exp_drop > criteria.maximum_expectancy_degradation_ratio:
        reasons.append("expectancy_degradation_limit_exceeded")

    if base["win_rate"] is not None and cur["win_rate"] is not None and base["win_rate"] - cur["win_rate"] > criteria.maximum_win_rate_drop:
        reasons.append("win_rate_drop_limit_exceeded")

    if base["profit_factor"] is not None and cur["profit_factor"] is not None:
        if math.isinf(base["profit_factor"]):
            if not math.isinf(cur["profit_factor"]):
                reasons.append("profit_factor_degraded_from_infinite")
        elif base["profit_factor"] - cur["profit_factor"] > criteria.maximum_profit_factor_drop:
            reasons.append("profit_factor_drop_limit_exceeded")

    risk_drop = _ratio_drop(base["pnl_to_risk"], cur["pnl_to_risk"])
    if risk_drop is None and base["pnl_to_risk"] is not None and base["pnl_to_risk"] > 0 and cur["pnl_to_risk"] is not None and cur["pnl_to_risk"] <= 0:
        reasons.append("pnl_to_risk_degraded_to_nonpositive")
    elif risk_drop is not None and risk_drop > criteria.maximum_pnl_to_risk_degradation_ratio:
        reasons.append("pnl_to_risk_degradation_limit_exceeded")

    status = DegradationStatus.DEGRADED if reasons else DegradationStatus.HEALTHY
    if status is DegradationStatus.HEALTHY:
        reasons = ["no_configured_degradation_threshold_exceeded"]
    return _make_assessment(status, tuple(reasons), baseline, current, criteria_fp, baseline_fp, current_fp)


def _validate_criteria(criteria: DegradationCriteria) -> list[str]:
    reasons: list[str] = []
    for name in ("minimum_baseline_records", "minimum_current_records"):
        value = getattr(criteria, name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            reasons.append(f"invalid_{name}")
    for name in ("maximum_expectancy_degradation_ratio", "maximum_win_rate_drop", "maximum_profit_factor_drop", "maximum_pnl_to_risk_degradation_ratio"):
        value = getattr(criteria, name)
        if not _finite(value) or float(value) < 0 or float(value) > 1:
            reasons.append(f"invalid_{name}")
    if not criteria.minimum_evidence_class.strip():
        reasons.append("missing_minimum_evidence_class")
    return reasons


def _make_assessment(status, reasons, baseline, current, criteria_fp, baseline_fp, current_fp):
    base = _summary(baseline)
    cur = _summary(current)
    data = {
        "status": status.value,
        "reasons": reasons,
        "baseline": baseline_fp,
        "current": current_fp,
        "criteria": criteria_fp,
    }
    assessment_fp = _fingerprint(data)
    return DegradationAssessment(
        status=status,
        reasons=tuple(reasons),
        baseline_records=len(baseline),
        current_records=len(current),
        baseline_cost_coverage=float(base["cost_coverage"]),
        current_cost_coverage=float(cur["cost_coverage"]),
        baseline_risk_coverage=float(base["risk_coverage"]),
        current_risk_coverage=float(cur["risk_coverage"]),
        baseline_expectancy=base["expectancy"],
        current_expectancy=cur["expectancy"],
        baseline_win_rate=base["win_rate"],
        current_win_rate=cur["win_rate"],
        baseline_profit_factor=base["profit_factor"],
        current_profit_factor=cur["profit_factor"],
        baseline_pnl_to_risk=base["pnl_to_risk"],
        current_pnl_to_risk=cur["pnl_to_risk"],
        baseline_fingerprint=baseline_fp,
        current_fingerprint=current_fp,
        criteria_fingerprint=criteria_fp,
        assessment_fingerprint=assessment_fp,
        execution_authorized=False,
    )


def degradation_assessment_is_not_execution_authorization(assessment: DegradationAssessment) -> bool:
    return assessment.execution_authorized is False
