"""APEX / BENVIN deterministic backtest reporting.

Phase 2.5.7 - Backtest Reporting & Result Aggregation

Aggregates the reproducibility metadata, trade simulation result, performance
metrics, and marked equity timeline into one immutable report contract.

This layer is measurement/reporting only. It does not change trades, make
strategy decisions, optimize parameters, or execute orders.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

from market.backtest.metrics import BacktestPerformanceMetrics, calculate_performance
from market.backtest.models import BacktestRunMetadata
from market.backtest.position import PositionSide
from market.backtest.trade import TradeSimulationResult


class BacktestReportingError(ValueError):
    """Raised when report aggregation receives invalid input."""


def _finite(value: float, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise BacktestReportingError(f"{name} must be finite.")
    return float(value)


@dataclass(frozen=True)
class EquityPoint:
    """One immutable marked-equity observation from the trade simulation."""

    index: int
    timestamp_utc: str
    equity: float
    cumulative_realized_pnl: float
    position_side: PositionSide

    def __post_init__(self) -> None:
        if not isinstance(self.index, int) or isinstance(self.index, bool) or self.index < 0:
            raise BacktestReportingError("index must be a non-negative integer.")
        if not isinstance(self.timestamp_utc, str) or not self.timestamp_utc.strip():
            raise BacktestReportingError("timestamp_utc must be a non-empty string.")
        _finite(self.equity, "equity")
        _finite(self.cumulative_realized_pnl, "cumulative_realized_pnl")
        if not isinstance(self.position_side, PositionSide):
            raise BacktestReportingError("position_side must be PositionSide.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "timestamp_utc": self.timestamp_utc,
            "equity": self.equity,
            "cumulative_realized_pnl": self.cumulative_realized_pnl,
            "position_side": self.position_side.value,
        }


@dataclass(frozen=True)
class BacktestReport:
    """Complete deterministic reporting artifact for one backtest simulation."""

    run_metadata: BacktestRunMetadata
    simulation: TradeSimulationResult
    performance: BacktestPerformanceMetrics
    equity_curve: tuple[EquityPoint, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.run_metadata, BacktestRunMetadata):
            raise BacktestReportingError("run_metadata must be a BacktestRunMetadata.")
        if not isinstance(self.simulation, TradeSimulationResult):
            raise BacktestReportingError("simulation must be a TradeSimulationResult.")
        if not isinstance(self.performance, BacktestPerformanceMetrics):
            raise BacktestReportingError("performance must be a BacktestPerformanceMetrics.")
        if not isinstance(self.equity_curve, tuple):
            raise BacktestReportingError("equity_curve must be a tuple.")

        expected_capital = float(self.run_metadata.config.initial_capital)
        if not math.isclose(expected_capital, float(self.simulation.initial_capital), rel_tol=0.0, abs_tol=1e-12):
            raise BacktestReportingError("run metadata capital must match simulation capital.")

        if self.run_metadata.dataset_pair != self.run_metadata.config.pair:
            raise BacktestReportingError("run metadata dataset_pair must match config pair.")
        if self.run_metadata.dataset_interval != self.run_metadata.config.interval:
            raise BacktestReportingError("run metadata dataset_interval must match config interval.")

        previous_index = -1
        for point in self.equity_curve:
            if not isinstance(point, EquityPoint):
                raise BacktestReportingError("equity_curve must contain EquityPoint values.")
            if point.index < previous_index:
                raise BacktestReportingError("equity_curve must be chronological.")
            previous_index = point.index

        if len(self.equity_curve) != len(self.simulation.events):
            raise BacktestReportingError("equity_curve must contain one point per simulation event.")

        expected_performance = calculate_performance(self.simulation)
        if self.performance != expected_performance:
            raise BacktestReportingError("performance must match the supplied simulation.")

        for point, event in zip(self.equity_curve, self.simulation.events):
            if (
                point.index != event.index
                or point.timestamp_utc != event.timestamp_utc
                or not math.isclose(point.equity, event.equity, rel_tol=0.0, abs_tol=1e-12)
                or not math.isclose(
                    point.cumulative_realized_pnl,
                    event.cumulative_realized_pnl,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                or point.position_side is not event.to_side
            ):
                raise BacktestReportingError("equity_curve must match simulation events exactly.")

    @property
    def pair(self) -> str:
        return self.run_metadata.config.pair

    @property
    def interval(self) -> str:
        return self.run_metadata.config.interval

    @property
    def strategy_ids(self) -> tuple[str, ...]:
        return self.run_metadata.strategy_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_metadata": self.run_metadata.to_dict(),
            "simulation": self.simulation.to_dict(),
            "performance": self.performance.to_dict(),
            "equity_curve": [point.to_dict() for point in self.equity_curve],
        }


class BacktestReportBuilder:
    """Build a deterministic report without modifying simulation data."""

    def build(
        self,
        run_metadata: BacktestRunMetadata,
        simulation: TradeSimulationResult,
    ) -> BacktestReport:
        if not isinstance(run_metadata, BacktestRunMetadata):
            raise BacktestReportingError("run_metadata must be a BacktestRunMetadata.")
        if not isinstance(simulation, TradeSimulationResult):
            raise BacktestReportingError("simulation must be a TradeSimulationResult.")

        if not math.isclose(
            float(run_metadata.config.initial_capital),
            float(simulation.initial_capital),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise BacktestReportingError("run metadata capital must match simulation capital.")

        performance = calculate_performance(simulation)
        equity_curve = tuple(
            EquityPoint(
                index=event.index,
                timestamp_utc=event.timestamp_utc,
                equity=float(event.equity),
                cumulative_realized_pnl=float(event.cumulative_realized_pnl),
                position_side=event.to_side,
            )
            for event in simulation.events
        )

        return BacktestReport(
            run_metadata=run_metadata,
            simulation=simulation,
            performance=performance,
            equity_curve=equity_curve,
        )


def build_report(
    run_metadata: BacktestRunMetadata,
    simulation: TradeSimulationResult,
) -> BacktestReport:
    """Convenience API for deterministic backtest report construction."""
    return BacktestReportBuilder().build(run_metadata, simulation)
