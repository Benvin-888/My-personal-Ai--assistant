"""APEX / BENVIN deterministic paper-trading performance evaluation.

Phase 2.20 - Paper Trading Performance & Evaluation Engine

This module measures a completed :class:`PaperTradingResult`.  It does not
create trades, alter risk, optimize parameters, select strategies, access a
broker, or authorize execution.

The evaluator is deliberately economic rather than cosmetic: net P&L,
gross P&L, transaction-cost burden, win/loss statistics, profit factor,
expectancy, R-multiples, drawdown, recovery, trade duration, and optional
session/regime/group evidence are calculated from the supplied paper result.
All inputs remain externally supplied and auditable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json
import math
from statistics import mean, pstdev
from typing import Any, Mapping, Sequence

from .paper import PaperTrade, PaperTradingResult


class PaperPerformanceError(ValueError):
    """Raised when paper-performance input is invalid."""


class PaperEvaluationStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"


def _number(value: Any, name: str, *, non_negative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PaperPerformanceError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise PaperPerformanceError(f"{name} must be finite")
    if non_negative and value < 0:
        raise PaperPerformanceError(f"{name} must be non-negative")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PaperPerformanceError(f"{name} must be a non-empty timestamp string")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PaperPerformanceError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise PaperPerformanceError(f"{name} must be timezone-aware")
    return parsed


def _pct(value: float, denominator: float) -> float:
    return (value / denominator * 100.0) if denominator else 0.0


@dataclass(frozen=True)
class PaperPerformancePolicy:
    """Measurement thresholds used only to classify paper evidence.

    These are conservative engineering defaults, not profitability claims or
    broker-trading permissions.  A small sample is classified as
    ``INSUFFICIENT_DATA`` rather than being declared successful.
    """

    minimum_trades: int = 30
    minimum_profit_factor: float = 1.0
    require_positive_net_pnl: bool = True
    maximum_drawdown_fraction: float = 0.20
    maximum_cost_burden_fraction: float = 0.50
    minimum_expectancy: float = 0.0
    require_positive_average_r: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.minimum_trades, bool) or not isinstance(self.minimum_trades, int) or self.minimum_trades < 1:
            raise PaperPerformanceError("minimum_trades must be a positive integer")
        for name in ("minimum_profit_factor", "maximum_drawdown_fraction", "maximum_cost_burden_fraction", "minimum_expectancy"):
            _number(getattr(self, name), name, non_negative=(name != "minimum_expectancy"))
        if not 0.0 <= self.maximum_drawdown_fraction <= 1.0:
            raise PaperPerformanceError("maximum_drawdown_fraction must be between 0 and 1")
        if not 0.0 <= self.maximum_cost_burden_fraction <= 1.0:
            raise PaperPerformanceError("maximum_cost_burden_fraction must be between 0 and 1")
        if not isinstance(self.require_positive_net_pnl, bool) or not isinstance(self.require_positive_average_r, bool):
            raise PaperPerformanceError("boolean policy fields must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class PaperPerformanceMetrics:
    """Deterministic economic summary of a completed paper simulation."""

    initial_equity: float
    ending_equity: float
    net_pnl: float
    gross_profit: float
    gross_loss: float
    total_costs: float
    return_fraction: float
    return_pct: float
    trade_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: float
    loss_rate: float
    profit_factor: float | None
    expectancy: float
    average_win: float
    average_loss: float
    payoff_ratio: float | None
    average_r_multiple: float
    best_trade: float
    worst_trade: float
    max_drawdown_fraction: float
    max_drawdown_pct: float
    recovery_factor: float | None
    cost_burden_fraction: float | None
    cost_burden_pct: float | None
    average_trade_duration_seconds: float
    median_trade_duration_seconds: float
    duration_stddev_seconds: float
    long_trades: int
    short_trades: int
    long_net_pnl: float
    short_net_pnl: float
    take_profit_trades: int
    stop_loss_trades: int
    end_of_test_trades: int
    rejected_entries: int

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name.endswith("_trades") or name == "rejected_entries":
                if not isinstance(value, int) or value < 0:
                    raise PaperPerformanceError(f"{name} must be a non-negative integer")
            elif name in {"profit_factor", "payoff_ratio", "recovery_factor"}:
                if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0):
                    raise PaperPerformanceError(f"{name} must be finite and non-negative when provided")
            else:
                _number(value, name, non_negative=name in {
                    "initial_equity", "gross_profit", "gross_loss", "total_costs",
                    "average_win", "average_trade_duration_seconds", "median_trade_duration_seconds",
                    "duration_stddev_seconds", "max_drawdown_fraction", "max_drawdown_pct",
                    "cost_burden_fraction", "cost_burden_pct",
                })
        if self.initial_equity <= 0:
            raise PaperPerformanceError("initial_equity must be positive")
        if self.trade_count != self.winning_trades + self.losing_trades + self.breakeven_trades:
            raise PaperPerformanceError("trade outcome counts must equal trade_count")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class PaperGroupMetrics:
    """Performance summary for an externally labelled group."""

    group_key: str
    group_value: str
    trade_count: int
    net_pnl: float
    gross_profit: float
    gross_loss: float
    win_rate: float
    profit_factor: float | None
    expectancy: float
    average_r_multiple: float
    max_drawdown_fraction: float | None

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class PaperEvaluationCheck:
    name: str
    passed: bool
    required: bool
    observed: float | int | bool | None
    threshold: float | int | bool | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class PaperPerformanceEvaluation:
    """Immutable paper-performance evidence bundle."""

    status: PaperEvaluationStatus
    metrics: PaperPerformanceMetrics
    checks: tuple[PaperEvaluationCheck, ...]
    groups: tuple[PaperGroupMetrics, ...]
    evidence_fingerprint: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def economically_credible(self) -> bool:
        return self.status is PaperEvaluationStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "metrics": self.metrics.to_dict(),
            "checks": [check.to_dict() for check in self.checks],
            "groups": [group.to_dict() for group in self.groups],
            "evidence_fingerprint": self.evidence_fingerprint,
            "metadata": dict(self.metadata),
            "economically_credible": self.economically_credible,
        }


def _durations(trades: Sequence[PaperTrade]) -> list[float]:
    values: list[float] = []
    for trade in trades:
        start = _timestamp(trade.entry_timestamp_utc, "trade entry_timestamp_utc")
        end = _timestamp(trade.exit_timestamp_utc, "trade exit_timestamp_utc")
        seconds = (end - start).total_seconds()
        if seconds < 0:
            raise PaperPerformanceError("trade exit timestamp cannot precede entry timestamp")
        values.append(seconds)
    return values


def _metrics_from_trades(result: PaperTradingResult, trades: Sequence[PaperTrade]) -> PaperPerformanceMetrics:
    initial = _number(result.initial_equity, "initial_equity")
    ending = _number(result.ending_equity, "ending_equity")
    total_costs = _number(result.total_costs, "total_costs", non_negative=True)
    trades = tuple(trades)
    pnls = [float(t.net_pnl) for t in trades]
    wins = [v for v in pnls if v > 0]
    losses = [v for v in pnls if v < 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    net = sum(pnls)
    # Result equity is authoritative; consistency is checked by the caller.
    profit_factor = gross_profit / gross_loss if gross_loss else (math.inf if gross_profit > 0 else None)
    if profit_factor is not None and not math.isfinite(profit_factor):
        profit_factor = None
    expectancy = mean(pnls) if pnls else 0.0
    average_win = mean(wins) if wins else 0.0
    average_loss = -mean(losses) if losses else 0.0
    payoff = average_win / average_loss if average_loss > 0 else None
    r_values = [float(t.r_multiple) for t in trades]
    durations = _durations(trades)
    durations_sorted = sorted(durations)
    median_duration = 0.0
    if durations_sorted:
        mid = len(durations_sorted) // 2
        median_duration = durations_sorted[mid] if len(durations_sorted) % 2 else (durations_sorted[mid - 1] + durations_sorted[mid]) / 2.0
    dd = _number(result.max_drawdown_fraction, "max_drawdown_fraction", non_negative=True)
    recovery = net / (initial * dd) if dd > 0 else None
    cost_burden = (total_costs / gross_profit) if gross_profit > 0 else None

    longs = tuple(t for t in trades if t.direction.upper() == "LONG")
    shorts = tuple(t for t in trades if t.direction.upper() == "SHORT")
    return PaperPerformanceMetrics(
        initial_equity=initial,
        ending_equity=ending,
        net_pnl=net,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        total_costs=total_costs,
        return_fraction=(ending - initial) / initial,
        return_pct=_pct(ending - initial, initial),
        trade_count=len(trades),
        winning_trades=len(wins),
        losing_trades=len(losses),
        breakeven_trades=len(trades) - len(wins) - len(losses),
        win_rate=(len(wins) / len(trades) if trades else 0.0),
        loss_rate=(len(losses) / len(trades) if trades else 0.0),
        profit_factor=profit_factor,
        expectancy=expectancy,
        average_win=average_win,
        average_loss=average_loss,
        payoff_ratio=payoff,
        average_r_multiple=(mean(r_values) if r_values else 0.0),
        best_trade=max(pnls, default=0.0),
        worst_trade=min(pnls, default=0.0),
        max_drawdown_fraction=dd,
        max_drawdown_pct=dd * 100.0,
        recovery_factor=recovery,
        cost_burden_fraction=cost_burden,
        cost_burden_pct=(cost_burden * 100.0 if cost_burden is not None else None),
        average_trade_duration_seconds=(mean(durations) if durations else 0.0),
        median_trade_duration_seconds=median_duration,
        duration_stddev_seconds=(pstdev(durations) if len(durations) > 1 else 0.0),
        long_trades=len(longs),
        short_trades=len(shorts),
        long_net_pnl=sum(t.net_pnl for t in longs),
        short_net_pnl=sum(t.net_pnl for t in shorts),
        take_profit_trades=sum(1 for t in trades if t.status.value == "TAKE_PROFIT"),
        stop_loss_trades=sum(1 for t in trades if t.status.value == "STOP_LOSS"),
        end_of_test_trades=sum(1 for t in trades if t.status.value == "END_OF_TEST"),
        rejected_entries=int(result.rejected_entries),
    )


def _group_metrics(key: str, value: str, trades: Sequence[PaperTrade]) -> PaperGroupMetrics:
    pnls = [float(t.net_pnl) for t in trades]
    wins = [v for v in pnls if v > 0]
    losses = [v for v in pnls if v < 0]
    gp = sum(wins)
    gl = -sum(losses)
    pf = gp / gl if gl > 0 else (math.inf if gp > 0 else None)
    if pf is not None and not math.isfinite(pf):
        pf = None
    return PaperGroupMetrics(
        group_key=key, group_value=value, trade_count=len(trades), net_pnl=sum(pnls),
        gross_profit=gp, gross_loss=gl, win_rate=(len(wins) / len(trades) if trades else 0.0),
        profit_factor=pf, expectancy=(mean(pnls) if pnls else 0.0),
        average_r_multiple=(mean(t.r_multiple for t in trades) if trades else 0.0),
        max_drawdown_fraction=None,
    )


class PaperPerformanceEngine:
    """Evaluate completed paper-trading results without changing them."""

    def __init__(self, policy: PaperPerformancePolicy | None = None) -> None:
        self.policy = policy or PaperPerformancePolicy()

    def evaluate(
        self,
        result: PaperTradingResult,
        *,
        group_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> PaperPerformanceEvaluation:
        if not isinstance(result, PaperTradingResult):
            raise PaperPerformanceError("result must be a PaperTradingResult")
        if group_metadata is not None and not isinstance(group_metadata, Mapping):
            raise PaperPerformanceError("group_metadata must be a mapping")

        trades = tuple(result.trades)
        if result.initial_equity <= 0:
            raise PaperPerformanceError("result.initial_equity must be positive")
        if abs(sum(t.net_pnl for t in trades) - result.realized_pnl) > 1e-9:
            raise PaperPerformanceError("trade net P&L does not reconcile with result.realized_pnl")
        if abs(result.initial_equity + result.realized_pnl - result.ending_equity) > 1e-9:
            raise PaperPerformanceError("result equity does not reconcile with realized_pnl")

        metrics = _metrics_from_trades(result, trades)
        checks: list[PaperEvaluationCheck] = []
        enough = metrics.trade_count >= self.policy.minimum_trades
        checks.append(PaperEvaluationCheck(
            "minimum_trade_count", enough, True, metrics.trade_count,
            self.policy.minimum_trades,
            "paper sample meets the minimum trade count" if enough else "paper sample is too small for a performance conclusion",
        ))
        positive_net = metrics.net_pnl > 0
        checks.append(PaperEvaluationCheck(
            "positive_net_pnl", positive_net, self.policy.require_positive_net_pnl,
            metrics.net_pnl, 0.0,
            "net P&L is positive" if positive_net else "net P&L is not positive",
        ))
        pf_ok = ((metrics.gross_loss == 0 and metrics.gross_profit > 0) or
                 (metrics.profit_factor is not None and metrics.profit_factor >= self.policy.minimum_profit_factor))
        checks.append(PaperEvaluationCheck(
            "profit_factor", pf_ok, True, metrics.profit_factor,
            self.policy.minimum_profit_factor,
            "profit factor meets the configured floor" if pf_ok else "profit factor is below the configured floor or unavailable",
        ))
        dd_ok = metrics.max_drawdown_fraction <= self.policy.maximum_drawdown_fraction
        checks.append(PaperEvaluationCheck(
            "maximum_drawdown", dd_ok, True, metrics.max_drawdown_fraction,
            self.policy.maximum_drawdown_fraction,
            "drawdown is within the configured ceiling" if dd_ok else "drawdown exceeds the configured ceiling",
        ))
        cost_ok = (metrics.cost_burden_fraction is not None and
                   metrics.cost_burden_fraction <= self.policy.maximum_cost_burden_fraction)
        checks.append(PaperEvaluationCheck(
            "transaction_cost_burden", cost_ok, True, metrics.cost_burden_fraction,
            self.policy.maximum_cost_burden_fraction,
            "transaction costs remain within the configured gross-profit burden" if cost_ok else "transaction costs consume too much gross profit",
        ))
        expectancy_ok = metrics.expectancy > self.policy.minimum_expectancy
        checks.append(PaperEvaluationCheck(
            "expectancy", expectancy_ok, True, metrics.expectancy,
            self.policy.minimum_expectancy,
            "trade expectancy is positive" if expectancy_ok else "trade expectancy does not exceed the configured floor",
        ))
        avg_r_ok = metrics.average_r_multiple > 0
        checks.append(PaperEvaluationCheck(
            "average_r_multiple", avg_r_ok, self.policy.require_positive_average_r,
            metrics.average_r_multiple, 0.0,
            "average R-multiple is positive" if avg_r_ok else "average R-multiple is not positive",
        ))

        groups: list[PaperGroupMetrics] = []
        if group_metadata:
            grouped: dict[tuple[str, str], list[PaperTrade]] = {}
            trade_ids = {trade.trade_id for trade in trades}
            for trade_id, metadata in group_metadata.items():
                if trade_id not in trade_ids:
                    raise PaperPerformanceError(f"group_metadata references unknown trade_id: {trade_id}")
                if not isinstance(metadata, Mapping):
                    raise PaperPerformanceError(f"metadata for {trade_id} must be a mapping")
                for key, value in metadata.items():
                    if value is None:
                        continue
                    grouped.setdefault((str(key), str(value)), []).append(next(t for t in trades if t.trade_id == trade_id))
            for (key, value), subset in sorted(grouped.items()):
                groups.append(_group_metrics(key, value, subset))

        required_checks = [check for check in checks if check.required]
        if not enough:
            status = PaperEvaluationStatus.INSUFFICIENT_DATA
        elif all(check.passed for check in required_checks):
            status = PaperEvaluationStatus.PASS
        else:
            status = PaperEvaluationStatus.FAIL

        payload = {
            "status": status.value,
            "metrics": metrics.to_dict(),
            "checks": [check.to_dict() for check in checks],
            "groups": [group.to_dict() for group in groups],
            "source_evidence_fingerprint": result.evidence_fingerprint,
            "policy": self.policy.to_dict(),
        }
        return PaperPerformanceEvaluation(
            status=status,
            metrics=metrics,
            checks=tuple(checks),
            groups=tuple(groups),
            evidence_fingerprint=_fingerprint(payload),
            metadata={
                "phase": "2.20",
                "research_only": True,
                "source_paper_evidence_fingerprint": result.evidence_fingerprint,
                "broker_access": False,
                "order_placement": False,
                "execution_authorization": False,
                "optimization": False,
                "strategy_selection": False,
                "profitability_guarantee": False,
            },
        )


def evaluate_paper_performance(
    result: PaperTradingResult,
    *,
    policy: PaperPerformancePolicy | None = None,
    group_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> PaperPerformanceEvaluation:
    """Convenience API for deterministic paper-performance evaluation."""
    return PaperPerformanceEngine(policy).evaluate(result, group_metadata=group_metadata)
