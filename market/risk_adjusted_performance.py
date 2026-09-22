"""Risk-aware performance analytics over persisted trade evidence.

This module is descriptive and read-only. It reuses the Phase 2.52 economic
accounting rules and only calculates risk metrics from risk information that is
explicitly present in the evidence. Missing risk is never treated as zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Mapping

from .economic_performance import assess_economic_record
from .mongodb_evidence_query import MongoTradeEvidenceQuery


RISK_FIELDS: tuple[str, ...] = ("risk_amount", "max_risk", "initial_risk")


@dataclass(frozen=True)
class RiskAdjustedPerformanceSummary:
    """Deterministic risk-aware summary for an evidence cohort."""

    total_records: int
    realized_pnl_records: int
    risk_records: int
    fully_costed_records: int
    risk_covered_records: int
    unpriced_records: int
    unrisked_records: int
    inconsistent_economic_records: int
    total_realized_pnl: float | None
    gross_profit: float | None
    gross_loss: float | None
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    total_explicit_costs: float | None
    cost_coverage_rate: float | None
    total_explicit_risk: float | None
    average_explicit_risk: float | None
    risk_coverage_rate: float | None
    pnl_to_risk_ratio: float | None
    max_realized_pnl_drawdown: float | None
    realized_pnl_drawdown_ratio: float | None
    risk_adjusted_expectancy: float | None


def _finite_number(document: Mapping[str, Any], field: str) -> float | None:
    value = document.get(field)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _explicit_risk(document: Mapping[str, Any]) -> float | None:
    """Return the first explicitly supplied finite non-negative risk amount."""
    for field in RISK_FIELDS:
        if field in document:
            value = _finite_number(document, field)
            if value is None or value < 0:
                return None
            return value
    return None


def _timestamp(document: Mapping[str, Any]) -> datetime | None:
    value = document.get("timestamp")
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _ordered_records(records: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Order records chronologically when timestamps are usable.

    Records without a usable timestamp retain their original relative order,
    after timestamped records. This keeps the path metric explicit rather than
    silently inventing chronology.
    """
    indexed = list(enumerate(records))
    timestamped = [(index, record, _timestamp(record)) for index, record in indexed]
    known = [item for item in timestamped if item[2] is not None]
    unknown = [item for item in timestamped if item[2] is None]
    known.sort(key=lambda item: (item[2], item[0]))
    return [item[1] for item in known + unknown]


def _realized_path_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = peak - equity
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


def summarize_risk_adjusted_performance(
    query: MongoTradeEvidenceQuery,
    filters: Mapping[str, Any] | None = None,
    tolerance: float = 1e-9,
) -> RiskAdjustedPerformanceSummary:
    """Summarize economic outcomes relative to explicit risk information.

    Risk metrics are calculated only from explicit ``risk_amount``,
    ``max_risk`` or ``initial_risk`` values. Missing risk is not treated as
    zero. The drawdown metric is the drawdown of the realized-P&L path, not an
    account-level drawdown estimate.
    """
    if filters is not None and not isinstance(filters, Mapping):
        raise TypeError("filters must be a mapping or None")
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
        raise ValueError("tolerance must be a finite non-negative number")
    tolerance = float(tolerance)
    if not isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be a finite non-negative number")

    records = [dict(record) for record in query.find(filters)]
    assessments = [assess_economic_record(record, tolerance=tolerance) for record in records]
    realized = [item.realized_pnl for item in assessments if item.realized_pnl is not None]
    risks = [_explicit_risk(record) for record in records]
    valid_risks = [value for value in risks if value is not None and value > 0]

    winners = sum(value > 0 for value in realized)
    losers = sum(value < 0 for value in realized)
    total_realized = sum(realized) if realized else None
    gross_profit = sum(value for value in realized if value > 0) if realized else None
    gross_loss = sum(value for value in realized if value < 0) if realized else None
    win_rate = winners / len(realized) if realized else None
    profit_factor = (
        gross_profit / abs(gross_loss)
        if gross_profit is not None and gross_loss is not None and gross_loss < 0
        else None
    )
    expectancy = total_realized / len(realized) if realized else None

    fully_costed = sum(item.fully_costed for item in assessments)
    priced = sum(item.priced for item in assessments)
    explicit_costs = [item.explicit_costs for item in assessments if item.explicit_costs is not None]
    total_costs = sum(explicit_costs) if explicit_costs else None

    risk_sum = sum(valid_risks) if valid_risks else None
    average_risk = risk_sum / len(valid_risks) if valid_risks else None
    risk_covered = len(valid_risks)
    risk_coverage = risk_covered / len(records) if records else None
    pnl_to_risk = total_realized / risk_sum if total_realized is not None and risk_sum and risk_sum > 0 else None
    risk_adjusted_expectancy = total_realized / risk_covered if total_realized is not None and risk_covered else None

    ordered = _ordered_records(records)
    ordered_realized = [
        assess_economic_record(record, tolerance=tolerance).realized_pnl
        for record in ordered
    ]
    path_values = [value for value in ordered_realized if value is not None]
    max_drawdown = _realized_path_drawdown(path_values)
    drawdown_ratio = (
        total_realized / max_drawdown
        if total_realized is not None and max_drawdown is not None and max_drawdown > 0
        else None
    )

    return RiskAdjustedPerformanceSummary(
        total_records=len(records),
        realized_pnl_records=len(realized),
        risk_records=risk_covered,
        fully_costed_records=fully_costed,
        risk_covered_records=risk_covered,
        unpriced_records=len(records) - priced,
        unrisked_records=len(records) - risk_covered,
        inconsistent_economic_records=sum(item.inconsistent for item in assessments),
        total_realized_pnl=total_realized,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        total_explicit_costs=total_costs,
        cost_coverage_rate=fully_costed / len(records) if records else None,
        total_explicit_risk=risk_sum,
        average_explicit_risk=average_risk,
        risk_coverage_rate=risk_coverage,
        pnl_to_risk_ratio=pnl_to_risk,
        max_realized_pnl_drawdown=max_drawdown,
        realized_pnl_drawdown_ratio=drawdown_ratio,
        risk_adjusted_expectancy=risk_adjusted_expectancy,
    )
