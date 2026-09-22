"""Deterministic statistical robustness analysis for APEX trade evidence.

Phase 2.56 quantifies uncertainty in an observed evidence cohort.  It is a
within-sample statistical analysis layer, not an out-of-sample validator,
strategy optimizer, profitability predictor, or execution component.

Important policies:
    * missing costs and missing risk are never treated as zero;
    * invalid/non-finite P&L is excluded from statistical observations;
    * the caller can require complete cost/risk coverage;
    * bootstrap output is reproducible through an explicit seed;
    * no result authorizes, creates, or executes a trade.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from random import Random
from statistics import NormalDist, mean, median, stdev
from typing import Any, Iterable, Mapping


INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
DESCRIPTIVE_STATISTICS = "DESCRIPTIVE_STATISTICS"
UNCERTAINTY_QUANTIFIED = "UNCERTAINTY_QUANTIFIED"
WITHIN_SAMPLE_STABILITY = "WITHIN_SAMPLE_STABILITY"


def _finite(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _number(value: Any) -> float | None:
    return float(value) if _finite(value) else None


def _cost_covered(record: Mapping[str, Any]) -> bool:
    total = _number(record.get("total_costs"))
    if total is not None and total >= 0:
        return True
    fields = ("transaction_cost", "slippage_cost", "financing_cost")
    present = [field for field in fields if field in record]
    if not present:
        return False
    values = [_number(record.get(field)) for field in fields]
    return all(value is not None and value >= 0 for value in values)


def _risk_covered(record: Mapping[str, Any]) -> bool:
    for field in ("risk_amount", "max_risk", "initial_risk"):
        value = _number(record.get(field))
        if value is not None and value >= 0:
            return True
    return False


def _percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires values")
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def _wilson_interval(successes: int, trials: int, z: float) -> tuple[float, float] | None:
    if trials <= 0:
        return None
    proportion = successes / trials
    denominator = 1.0 + (z * z / trials)
    centre = (proportion + (z * z / (2.0 * trials))) / denominator
    margin = (
        z
        * sqrt(
            (proportion * (1.0 - proportion) / trials)
            + (z * z / (4.0 * trials * trials))
        )
        / denominator
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _bootstrap_mean(values: list[float], iterations: int, seed: int) -> list[float]:
    rng = Random(seed)
    count = len(values)
    results: list[float] = []
    for _ in range(iterations):
        total = 0.0
        for _ in range(count):
            total += values[rng.randrange(count)]
        results.append(total / count)
    return results


@dataclass(frozen=True)
class StatisticalRobustnessCriteria:
    """Explicit analysis settings; none imply future profitability."""

    min_sample_size: int = 30
    confidence_level: float = 0.95
    bootstrap_iterations: int = 2000
    bootstrap_seed: int = 256
    require_complete_cost_coverage: bool = True
    require_complete_risk_coverage: bool = True
    concentration_top_n: int = 5

    def __post_init__(self) -> None:
        if isinstance(self.min_sample_size, bool) or self.min_sample_size < 1:
            raise ValueError("min_sample_size must be at least 1")
        if not _finite(self.confidence_level) or not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be between 0 and 1")
        if isinstance(self.bootstrap_iterations, bool) or self.bootstrap_iterations < 1:
            raise ValueError("bootstrap_iterations must be at least 1")
        if isinstance(self.bootstrap_seed, bool) or self.bootstrap_seed < 0:
            raise ValueError("bootstrap_seed must be non-negative")
        if isinstance(self.concentration_top_n, bool) or self.concentration_top_n < 1:
            raise ValueError("concentration_top_n must be at least 1")


@dataclass(frozen=True)
class StatisticalRobustnessSummary:
    """Complete descriptive/uncertainty result for one evidence cohort."""

    status: str
    criteria: StatisticalRobustnessCriteria
    total_records: int
    usable_records: int
    invalid_pnl_records: int
    cost_covered_records: int
    risk_covered_records: int
    sample_adequate: bool
    wins: int
    losses: int
    breakeven: int
    win_rate: float | None
    win_rate_interval: tuple[float, float] | None
    mean_pnl: float | None
    median_pnl: float | None
    std_pnl: float | None
    min_pnl: float | None
    max_pnl: float | None
    total_pnl: float | None
    expectancy: float | None
    expectancy_interval: tuple[float, float] | None
    top_wins_pnl: float | None
    top_losses_pnl: float | None
    pnl_excluding_top_win: float | None
    pnl_excluding_top_losses: float | None
    bootstrap_iterations: int
    bootstrap_seed: int
    bootstrap_mean_interval: tuple[float, float] | None
    dependence_warning: bool
    cost_coverage_complete: bool
    risk_coverage_complete: bool
    limitations: tuple[str, ...]


def summarize_statistical_robustness(
    records: Iterable[Mapping[str, Any]],
    *,
    criteria: StatisticalRobustnessCriteria | None = None,
) -> StatisticalRobustnessSummary:
    """Analyze realized P&L uncertainty without making a trading decision."""
    if criteria is None:
        criteria = StatisticalRobustnessCriteria()
    if not isinstance(criteria, StatisticalRobustnessCriteria):
        raise TypeError("criteria must be StatisticalRobustnessCriteria")

    materialized = list(records)
    values: list[float] = []
    invalid = 0
    cost_count = 0
    risk_count = 0
    for record in materialized:
        if not isinstance(record, Mapping):
            invalid += 1
            continue
        pnl = _number(record.get("realized_pnl"))
        if pnl is None:
            invalid += 1
            continue
        values.append(pnl)
        cost_count += int(_cost_covered(record))
        risk_count += int(_risk_covered(record))

    n = len(values)
    wins = sum(value > 0 for value in values)
    losses = sum(value < 0 for value in values)
    breakeven = n - wins - losses
    sample_adequate = n >= criteria.min_sample_size
    cost_complete = n > 0 and cost_count == n
    risk_complete = n > 0 and risk_count == n

    limitations: list[str] = []
    if not sample_adequate:
        limitations.append("sample_below_minimum")
    if criteria.require_complete_cost_coverage and not cost_complete:
        limitations.append("cost_coverage_incomplete")
    if criteria.require_complete_risk_coverage and not risk_complete:
        limitations.append("risk_coverage_incomplete")
    if invalid:
        limitations.append("invalid_pnl_records_excluded")
    if n > 1:
        limitations.append("trade_independence_not_established")

    if n == 0:
        status = INSUFFICIENT_DATA
    elif not sample_adequate:
        status = DESCRIPTIVE_STATISTICS
    elif (criteria.require_complete_cost_coverage and not cost_complete) or (
        criteria.require_complete_risk_coverage and not risk_complete
    ):
        status = UNCERTAINTY_QUANTIFIED
    else:
        status = WITHIN_SAMPLE_STABILITY

    if not values:
        return StatisticalRobustnessSummary(
            status=status,
            criteria=criteria,
            total_records=len(materialized),
            usable_records=0,
            invalid_pnl_records=invalid,
            cost_covered_records=cost_count,
            risk_covered_records=risk_count,
            sample_adequate=False,
            wins=0,
            losses=0,
            breakeven=0,
            win_rate=None,
            win_rate_interval=None,
            mean_pnl=None,
            median_pnl=None,
            std_pnl=None,
            min_pnl=None,
            max_pnl=None,
            total_pnl=None,
            expectancy=None,
            expectancy_interval=None,
            top_wins_pnl=None,
            top_losses_pnl=None,
            pnl_excluding_top_win=None,
            pnl_excluding_top_losses=None,
            bootstrap_iterations=0,
            bootstrap_seed=criteria.bootstrap_seed,
            bootstrap_mean_interval=None,
            dependence_warning=n > 1,
            cost_coverage_complete=False,
            risk_coverage_complete=False,
            limitations=tuple(limitations),
        )

    avg = mean(values)
    confidence_z = NormalDist().inv_cdf(0.5 + criteria.confidence_level / 2.0)
    win_interval = _wilson_interval(wins, n, confidence_z)
    bootstrap_values = _bootstrap_mean(values, criteria.bootstrap_iterations, criteria.bootstrap_seed)
    bootstrap_values.sort()
    bootstrap_interval = (
        _percentile(bootstrap_values, (1 - criteria.confidence_level) / 2),
        _percentile(bootstrap_values, 1 - (1 - criteria.confidence_level) / 2),
    )

    if n > 1:
        std = stdev(values)
    else:
        std = 0.0
    top_wins = sorted((value for value in values if value > 0), reverse=True)[: criteria.concentration_top_n]
    top_losses = sorted((value for value in values if value < 0))[: criteria.concentration_top_n]
    top_wins_total = sum(top_wins) if top_wins else 0.0
    top_losses_total = sum(top_losses) if top_losses else 0.0
    best = max(values)
    best_removed = sum(values) - best
    worst_losses_removed = sum(values) - top_losses_total

    return StatisticalRobustnessSummary(
        status=status,
        criteria=criteria,
        total_records=len(materialized),
        usable_records=n,
        invalid_pnl_records=invalid,
        cost_covered_records=cost_count,
        risk_covered_records=risk_count,
        sample_adequate=sample_adequate,
        wins=wins,
        losses=losses,
        breakeven=breakeven,
        win_rate=wins / n,
        win_rate_interval=win_interval,
        mean_pnl=avg,
        median_pnl=median(values),
        std_pnl=std,
        min_pnl=min(values),
        max_pnl=max(values),
        total_pnl=sum(values),
        expectancy=avg,
        expectancy_interval=bootstrap_interval,
        top_wins_pnl=top_wins_total,
        top_losses_pnl=top_losses_total,
        pnl_excluding_top_win=best_removed,
        pnl_excluding_top_losses=worst_losses_removed,
        bootstrap_iterations=criteria.bootstrap_iterations,
        bootstrap_seed=criteria.bootstrap_seed,
        bootstrap_mean_interval=bootstrap_interval,
        dependence_warning=n > 1,
        cost_coverage_complete=cost_complete,
        risk_coverage_complete=risk_complete,
        limitations=tuple(limitations),
    )


def summarize_trade_evidence(
    query: Any,
    *,
    filters: Mapping[str, Any] | None = None,
    criteria: StatisticalRobustnessCriteria | None = None,
) -> StatisticalRobustnessSummary:
    """Run the analysis against an existing read-only evidence query object."""
    if not hasattr(query, "find"):
        raise TypeError("query must provide a find(filters) method")
    records = query.find(dict(filters or {}))
    return summarize_statistical_robustness(records, criteria=criteria)
