"""Descriptive strategy attribution over persisted trade evidence.

This module answers which strategy identity and version produced the recorded
outcomes in the evidence set. It is attribution, not proof of causality.
The layer is read-only and reuses the Phase 2.52 economic accounting rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

from .economic_performance import assess_economic_record
from .mongodb_evidence_query import MongoTradeEvidenceQuery

MISSING = "<missing>"


@dataclass(frozen=True)
class StrategyAttribution:
    """Economic outcome summary for one strategy identity/version cohort."""

    strategy_id: str
    strategy_version: str
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
class StrategyAttributionSummary:
    """Deterministic descriptive attribution across strategy cohorts."""

    total_records: int
    attributed_records: int
    unattributed_records: int
    strategy_count: int
    version_count: int
    groups: tuple[StrategyAttribution, ...]


def _label(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    if value is None:
        return MISSING
    text = str(value).strip()
    return text or MISSING


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _build_group(
    strategy_id: str,
    strategy_version: str,
    records: list[Mapping[str, Any]],
    tolerance: float,
) -> StrategyAttribution:
    assessments = [assess_economic_record(record, tolerance=tolerance) for record in records]
    realized = [item.realized_pnl for item in assessments if item.realized_pnl is not None]
    gross = [item.gross_pnl for item in assessments if item.gross_pnl is not None]
    costs = [item.explicit_costs for item in assessments if item.explicit_costs is not None]
    derived = [item.derived_net_pnl for item in assessments if item.derived_net_pnl is not None]

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
    total_costs = sum(costs) if costs else None
    average_cost = total_costs / len(costs) if costs else None
    fully_costed = sum(item.fully_costed for item in assessments)
    priced = sum(item.priced for item in assessments)
    derived_total = sum(derived) if derived else None

    return StrategyAttribution(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        total_records=len(records),
        realized_pnl_records=len(realized),
        gross_pnl_records=len(gross),
        cost_records=len(costs),
        fully_costed_records=fully_costed,
        unpriced_records=len(records) - priced,
        inconsistent_records=sum(item.inconsistent for item in assessments),
        total_realized_pnl=_finite(total_realized),
        gross_profit=_finite(gross_profit),
        gross_loss=_finite(gross_loss),
        win_rate=_finite(win_rate),
        profit_factor=_finite(profit_factor),
        expectancy=_finite(expectancy),
        total_explicit_costs=_finite(total_costs),
        average_explicit_cost=_finite(average_cost),
        cost_coverage_rate=fully_costed / len(records) if records else None,
        derived_net_pnl=_finite(derived_total),
        economic_pnl_records=priced,
    )


def summarize_strategy_attribution(
    query: MongoTradeEvidenceQuery,
    filters: Mapping[str, Any] | None = None,
    tolerance: float = 1e-9,
) -> StrategyAttributionSummary:
    """Group evidence by strategy identity and version and summarize outcomes.

    Missing strategy identity/version values remain explicit ``<missing>``
    cohorts. No outcome is inferred from status, and incomplete costs are not
    treated as zero. Results are sorted deterministically by strategy id and
    strategy version.
    """
    if filters is not None and not isinstance(filters, Mapping):
        raise TypeError("filters must be a mapping or None")
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
        raise ValueError("tolerance must be a finite non-negative number")
    tolerance = float(tolerance)
    if not isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be a finite non-negative number")

    records = [dict(record) for record in query.find(filters)]
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for record in records:
        key = (_label(record, "strategy_id"), _label(record, "strategy_version"))
        groups.setdefault(key, []).append(record)

    ordered_keys = sorted(groups)
    results = tuple(
        _build_group(strategy_id, strategy_version, groups[(strategy_id, strategy_version)], tolerance)
        for strategy_id, strategy_version in ordered_keys
    )
    attributed = sum(
        group.total_records
        for group in results
        if group.strategy_id != MISSING and group.strategy_version != MISSING
    )
    strategy_ids = {group.strategy_id for group in results if group.strategy_id != MISSING}
    versions = {group.strategy_version for group in results if group.strategy_version != MISSING}

    return StrategyAttributionSummary(
        total_records=len(records),
        attributed_records=attributed,
        unattributed_records=len(records) - attributed,
        strategy_count=len(strategy_ids),
        version_count=len(versions),
        groups=results,
    )
