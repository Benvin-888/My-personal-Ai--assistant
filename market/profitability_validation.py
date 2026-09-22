"""Deterministic profitability validation over persisted trade evidence.

Phase 2.55 is a validation gate, not a statistical-significance engine. It
checks whether a cohort has sufficient, cost-aware and risk-aware evidence to
be considered economically promising under explicit caller-supplied criteria.
It never treats missing costs or risk as zero and never predicts future
performance.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

from .economic_performance import assess_economic_record
from .evidence_quality import assess_trade_evidence
from .mongodb_evidence_query import MongoTradeEvidenceQuery
from .risk_adjusted_performance import summarize_risk_adjusted_performance


@dataclass(frozen=True)
class ProfitabilityValidationCriteria:
    """Explicit deterministic acceptance criteria for one evidence cohort."""

    min_realized_pnl_records: int = 30
    min_cost_coverage_rate: float = 1.0
    min_risk_coverage_rate: float = 1.0
    require_positive_net_pnl: bool = True
    min_profit_factor: float = 1.0
    min_expectancy: float = 0.0
    min_pnl_to_risk_ratio: float | None = 0.0
    max_inconsistent_economic_records: int = 0
    max_invalid_evidence_records: int = 0
    max_incomplete_evidence_records: int = 0

    def __post_init__(self) -> None:
        _validate_criteria(self)


@dataclass(frozen=True)
class ProfitabilityValidationResult:
    """Transparent validation result with every gate exposed."""

    status: str
    criteria: ProfitabilityValidationCriteria
    total_records: int
    valid_evidence_records: int
    incomplete_evidence_records: int
    invalid_evidence_records: int
    realized_pnl_records: int
    cost_coverage_rate: float | None
    risk_coverage_rate: float | None
    total_realized_pnl: float | None
    expectancy: float | None
    profit_factor: float | None
    pnl_to_risk_ratio: float | None
    inconsistent_economic_records: int
    failed_checks: tuple[str, ...]


VALID = "VALID"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
INVALID = "INVALID_EVIDENCE"


def _validate_criteria(criteria: ProfitabilityValidationCriteria) -> None:
    if not isinstance(criteria, ProfitabilityValidationCriteria):
        raise TypeError("criteria must be ProfitabilityValidationCriteria")
    if isinstance(criteria.min_realized_pnl_records, bool) or criteria.min_realized_pnl_records < 1:
        raise ValueError("min_realized_pnl_records must be at least 1")
    for name in ("min_cost_coverage_rate", "min_risk_coverage_rate"):
        value = float(getattr(criteria, name))
        if not isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if criteria.min_profit_factor < 0 or not isfinite(float(criteria.min_profit_factor)):
        raise ValueError("min_profit_factor must be finite and non-negative")
    if not isfinite(float(criteria.min_expectancy)):
        raise ValueError("min_expectancy must be finite")
    if criteria.min_pnl_to_risk_ratio is not None and not isfinite(float(criteria.min_pnl_to_risk_ratio)):
        raise ValueError("min_pnl_to_risk_ratio must be finite or None")
    if isinstance(criteria.max_inconsistent_economic_records, bool) or criteria.max_inconsistent_economic_records < 0:
        raise ValueError("max_inconsistent_economic_records must be non-negative")
    if isinstance(criteria.max_invalid_evidence_records, bool) or criteria.max_invalid_evidence_records < 0:
        raise ValueError("max_invalid_evidence_records must be non-negative")
    if isinstance(criteria.max_incomplete_evidence_records, bool) or criteria.max_incomplete_evidence_records < 0:
        raise ValueError("max_incomplete_evidence_records must be non-negative")


def validate_profitability(
    query: MongoTradeEvidenceQuery,
    criteria: ProfitabilityValidationCriteria | None = None,
    filters: Mapping[str, Any] | None = None,
    tolerance: float = 1e-9,
) -> ProfitabilityValidationResult:
    """Validate descriptive profitability evidence against explicit criteria.

    This is deliberately not a statistical significance test. Phase 2.56 is
    responsible for statistical robustness, while Phase 2.57 handles OOS and
    walk-forward evidence.
    """
    criteria = criteria or ProfitabilityValidationCriteria()
    _validate_criteria(criteria)
    if filters is not None and not isinstance(filters, Mapping):
        raise TypeError("filters must be a mapping or None")
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
        raise ValueError("tolerance must be a finite non-negative number")
    tolerance = float(tolerance)
    if not isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be a finite non-negative number")

    records = [dict(record) for record in query.find(filters)]
    quality_summary = assess_trade_evidence(query, filters=filters)
    valid_count = quality_summary.valid_records
    incomplete_count = quality_summary.incomplete_records
    invalid_count = quality_summary.invalid_records

    economic = [assess_economic_record(record, tolerance=tolerance) for record in records]
    risk = summarize_risk_adjusted_performance(query, filters=filters, tolerance=tolerance)

    failed: list[str] = []
    if invalid_count > criteria.max_invalid_evidence_records:
        failed.append("invalid_evidence_records")
    if incomplete_count > criteria.max_incomplete_evidence_records:
        failed.append("incomplete_evidence_records")
    if risk.inconsistent_economic_records > criteria.max_inconsistent_economic_records:
        failed.append("inconsistent_economic_records")
    if risk.realized_pnl_records < criteria.min_realized_pnl_records:
        failed.append("minimum_realized_pnl_records")
    if risk.cost_coverage_rate is None or risk.cost_coverage_rate < criteria.min_cost_coverage_rate:
        failed.append("cost_coverage_rate")
    if risk.risk_coverage_rate is None or risk.risk_coverage_rate < criteria.min_risk_coverage_rate:
        failed.append("risk_coverage_rate")
    if criteria.require_positive_net_pnl and (risk.total_realized_pnl is None or risk.total_realized_pnl <= 0):
        failed.append("positive_net_pnl")
    realized_values = [item.realized_pnl for item in economic if item.realized_pnl is not None]
    no_losses = bool(realized_values) and all(value >= 0 for value in realized_values) and any(value > 0 for value in realized_values)
    profit_factor_ok = no_losses or (risk.profit_factor is not None and risk.profit_factor >= criteria.min_profit_factor)
    if not profit_factor_ok:
        failed.append("profit_factor")
    if risk.expectancy is None or risk.expectancy < criteria.min_expectancy:
        failed.append("expectancy")
    if criteria.min_pnl_to_risk_ratio is not None and (
        risk.pnl_to_risk_ratio is None or risk.pnl_to_risk_ratio < criteria.min_pnl_to_risk_ratio
    ):
        failed.append("pnl_to_risk_ratio")

    # INVALID evidence is a data-integrity problem; otherwise a failed gate is
    # insufficient evidence for this deterministic validation stage.
    status = INVALID if invalid_count > criteria.max_invalid_evidence_records else (
        INSUFFICIENT if failed else VALID
    )

    return ProfitabilityValidationResult(
        status=status,
        criteria=criteria,
        total_records=len(records),
        valid_evidence_records=valid_count,
        incomplete_evidence_records=incomplete_count,
        invalid_evidence_records=invalid_count,
        realized_pnl_records=risk.realized_pnl_records,
        cost_coverage_rate=risk.cost_coverage_rate,
        risk_coverage_rate=risk.risk_coverage_rate,
        total_realized_pnl=risk.total_realized_pnl,
        expectancy=risk.expectancy,
        profit_factor=risk.profit_factor,
        pnl_to_risk_ratio=risk.pnl_to_risk_ratio,
        inconsistent_economic_records=risk.inconsistent_economic_records,
        failed_checks=tuple(failed),
    )
