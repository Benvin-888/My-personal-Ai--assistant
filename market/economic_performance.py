"""Cost-aware economic performance analytics over persisted trade evidence.

This module is read-only. It never invents missing costs, infers outcomes from
status, or grants trading/execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping

from .mongodb_evidence_query import MongoTradeEvidenceQuery


COST_COMPONENT_FIELDS: tuple[str, ...] = (
    "transaction_cost",
    "slippage_cost",
    "financing_cost",
)


@dataclass(frozen=True)
class EconomicPerformanceSummary:
    """Deterministic economic metrics with explicit cost-coverage accounting."""

    total_records: int
    realized_pnl_records: int
    gross_pnl_records: int
    cost_records: int
    fully_costed_records: int
    unpriced_records: int
    inconsistent_records: int
    total_realized_pnl: float | None
    gross_profit: float | None
    gross_loss: float | None
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    total_explicit_costs: float | None
    average_explicit_cost: float | None
    cost_coverage_rate: float | None
    derived_net_pnl: float | None
    economic_pnl_records: int


@dataclass(frozen=True)
class EconomicRecordAssessment:
    """Economic pricing assessment for one persisted evidence record."""

    trade_id: str
    realized_pnl: float | None
    gross_pnl: float | None
    explicit_costs: float | None
    derived_net_pnl: float | None
    fully_costed: bool
    priced: bool
    inconsistent: bool


def _finite_number(document: Mapping[str, Any], field: str) -> float | None:
    value = document.get(field)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _explicit_costs(document: Mapping[str, Any]) -> float | None:
    """Return explicit total costs, preferring total_costs when supplied.

    If total_costs is absent, individual transaction/slippage/financing costs
    are summed only when every supplied component is finite. Missing components
    are not treated as zero unless the record explicitly supplies a total.
    """
    total = _finite_number(document, "total_costs")
    if "total_costs" in document:
        return total
    supplied = [field for field in COST_COMPONENT_FIELDS if field in document]
    if not supplied:
        return None
    values = [_finite_number(document, field) for field in supplied]
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def assess_economic_record(
    document: Mapping[str, Any],
    tolerance: float = 1e-9,
) -> EconomicRecordAssessment:
    """Assess explicit economic information without filling missing values."""
    if not isinstance(document, Mapping):
        raise TypeError("document must be a mapping")
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not isfinite(float(tolerance)) or tolerance < 0:
        raise ValueError("tolerance must be a finite non-negative number")

    realized = _finite_number(document, "realized_pnl")
    gross = _finite_number(document, "gross_pnl")
    costs = _explicit_costs(document)
    fully_costed = gross is not None and costs is not None
    derived = gross - costs if fully_costed else None
    inconsistent = (
        realized is not None
        and derived is not None
        and abs(realized - derived) > float(tolerance)
    )
    trade_id = str(document.get("trade_id", "")).strip()
    priced = realized is not None or derived is not None
    return EconomicRecordAssessment(
        trade_id=trade_id,
        realized_pnl=realized,
        gross_pnl=gross,
        explicit_costs=costs,
        derived_net_pnl=derived,
        fully_costed=fully_costed,
        priced=priced,
        inconsistent=inconsistent,
    )


def summarize_economic_performance(
    query: MongoTradeEvidenceQuery,
    filters: Mapping[str, Any] | None = None,
    tolerance: float = 1e-9,
) -> EconomicPerformanceSummary:
    """Summarize realized outcomes and explicit cost coverage.

    ``realized_pnl`` is treated as the authoritative recorded net outcome when
    present. Gross-minus-cost is used only when both values are explicitly
    available. Missing costs are never assumed to be zero, which prevents
    incomplete evidence from masquerading as cost-realistic performance.
    """
    if filters is not None and not isinstance(filters, Mapping):
        raise TypeError("filters must be a mapping or None")

    records = [dict(record) for record in query.find(filters)]
    assessments = [assess_economic_record(record, tolerance=tolerance) for record in records]

    realized = [item.realized_pnl for item in assessments if item.realized_pnl is not None]
    gross = [item.gross_pnl for item in assessments if item.gross_pnl is not None]
    costs = [item.explicit_costs for item in assessments if item.explicit_costs is not None]
    derived = [item.derived_net_pnl for item in assessments if item.derived_net_pnl is not None]

    winners = sum(1 for value in realized if value > 0)
    losers = sum(1 for value in realized if value < 0)
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
    total_costs = sum(costs) if costs else None
    average_cost = total_costs / len(costs) if costs else None
    fully_costed = sum(item.fully_costed for item in assessments)
    priced = sum(item.priced for item in assessments)
    cost_coverage = fully_costed / len(records) if records else None
    derived_total = sum(derived) if derived else None

    return EconomicPerformanceSummary(
        total_records=len(records),
        realized_pnl_records=len(realized),
        gross_pnl_records=len(gross),
        cost_records=len(costs),
        fully_costed_records=fully_costed,
        unpriced_records=len(records) - priced,
        inconsistent_records=sum(item.inconsistent for item in assessments),
        total_realized_pnl=total_realized,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        total_explicit_costs=total_costs,
        average_explicit_cost=average_cost,
        cost_coverage_rate=cost_coverage,
        derived_net_pnl=derived_total,
        economic_pnl_records=priced,
    )
