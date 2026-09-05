"""APEX / BENVIN deterministic backtest performance metrics.

Phase 2.5.6 - Backtest Performance Metrics

Consumes a completed TradeSimulationResult and produces measurement only.
No strategy decisions, execution, optimization, or live trading behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from market.backtest.position import PositionSide
from market.backtest.trade import TradeRecord, TradeSimulationResult


class BacktestMetricsError(ValueError):
    """Raised when metrics receive invalid simulation data."""


def _finite(value: float, name: str) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise BacktestMetricsError(f"{name} must be finite.")
    return float(value)


@dataclass(frozen=True)
class BacktestPerformanceMetrics:
    """Deterministic summary of a completed hypothetical backtest."""

    initial_capital: float
    final_equity: float
    net_pnl: float
    total_return: float
    total_return_pct: float
    trade_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: float
    loss_rate: float
    gross_profit: float
    gross_loss: float
    profit_factor: float | None
    average_win: float
    average_loss: float
    best_trade: float
    worst_trade: float
    max_drawdown: float
    max_drawdown_pct: float
    long_trades: int
    short_trades: int
    long_net_pnl: float
    short_net_pnl: float
    exposure_events: int
    long_exposure_events: int
    short_exposure_events: int
    neutral_or_flat_events: int

    def __post_init__(self) -> None:
        for name in (
            "initial_capital", "final_equity", "net_pnl", "total_return",
            "total_return_pct", "win_rate", "loss_rate", "gross_profit",
            "gross_loss", "average_win", "average_loss", "best_trade",
            "worst_trade", "max_drawdown", "max_drawdown_pct",
            "long_net_pnl", "short_net_pnl",
        ):
            _finite(getattr(self, name), name)
        for name in (
            "trade_count", "winning_trades", "losing_trades", "breakeven_trades",
            "long_trades", "short_trades", "exposure_events",
            "long_exposure_events", "short_exposure_events", "neutral_or_flat_events",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 0:
                raise BacktestMetricsError(f"{name} must be a non-negative integer.")
        if self.initial_capital <= 0:
            raise BacktestMetricsError("initial_capital must be positive.")
        if self.profit_factor is not None and (not math.isfinite(self.profit_factor) or self.profit_factor < 0):
            raise BacktestMetricsError("profit_factor must be finite and non-negative when provided.")

    def to_dict(self) -> dict:
        return {
            "initial_capital": self.initial_capital,
            "final_equity": self.final_equity,
            "net_pnl": self.net_pnl,
            "total_return": self.total_return,
            "total_return_pct": self.total_return_pct,
            "trade_count": self.trade_count,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
            "win_rate": self.win_rate,
            "loss_rate": self.loss_rate,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "profit_factor": self.profit_factor,
            "average_win": self.average_win,
            "average_loss": self.average_loss,
            "best_trade": self.best_trade,
            "worst_trade": self.worst_trade,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "long_trades": self.long_trades,
            "short_trades": self.short_trades,
            "long_net_pnl": self.long_net_pnl,
            "short_net_pnl": self.short_net_pnl,
            "exposure_events": self.exposure_events,
            "long_exposure_events": self.long_exposure_events,
            "short_exposure_events": self.short_exposure_events,
            "neutral_or_flat_events": self.neutral_or_flat_events,
        }


class BacktestMetricsCalculator:
    """Calculate deterministic performance metrics from a trade simulation."""

    def calculate(self, result: TradeSimulationResult) -> BacktestPerformanceMetrics:
        if not isinstance(result, TradeSimulationResult):
            raise BacktestMetricsError("result must be a TradeSimulationResult.")

        initial = float(result.initial_capital)
        final = float(result.final_account.equity)
        net_pnl = final - initial
        total_return = net_pnl / initial
        total_return_pct = total_return * 100.0

        trades = result.trades
        winning = tuple(t for t in trades if t.realized_pnl > 0)
        losing = tuple(t for t in trades if t.realized_pnl < 0)
        breakeven = tuple(t for t in trades if t.realized_pnl == 0)
        gross_profit = sum(t.realized_pnl for t in winning)
        gross_loss = -sum(t.realized_pnl for t in losing)
        profit_factor = None if gross_loss == 0 else gross_profit / gross_loss
        average_win = gross_profit / len(winning) if winning else 0.0
        average_loss = sum(t.realized_pnl for t in losing) / len(losing) if losing else 0.0
        best = max((t.realized_pnl for t in trades), default=0.0)
        worst = min((t.realized_pnl for t in trades), default=0.0)

        peak = initial
        max_dd = 0.0
        max_dd_pct = 0.0
        for event in result.events:
            equity = float(event.equity)
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0

        long_trades = tuple(t for t in trades if t.side is PositionSide.LONG)
        short_trades = tuple(t for t in trades if t.side is PositionSide.SHORT)
        long_pnl = sum(t.realized_pnl for t in long_trades)
        short_pnl = sum(t.realized_pnl for t in short_trades)

        long_exposure = sum(1 for e in result.events if e.to_side is PositionSide.LONG)
        short_exposure = sum(1 for e in result.events if e.to_side is PositionSide.SHORT)
        exposure = long_exposure + short_exposure
        neutral_flat = len(result.events) - exposure

        count = len(trades)
        win_rate = len(winning) / count if count else 0.0
        loss_rate = len(losing) / count if count else 0.0

        return BacktestPerformanceMetrics(
            initial_capital=initial, final_equity=final, net_pnl=net_pnl,
            total_return=total_return, total_return_pct=total_return_pct,
            trade_count=count, winning_trades=len(winning), losing_trades=len(losing),
            breakeven_trades=len(breakeven), win_rate=win_rate, loss_rate=loss_rate,
            gross_profit=gross_profit, gross_loss=gross_loss, profit_factor=profit_factor,
            average_win=average_win, average_loss=average_loss, best_trade=best, worst_trade=worst,
            max_drawdown=max_dd, max_drawdown_pct=max_dd_pct,
            long_trades=len(long_trades), short_trades=len(short_trades),
            long_net_pnl=long_pnl, short_net_pnl=short_pnl,
            exposure_events=exposure, long_exposure_events=long_exposure,
            short_exposure_events=short_exposure, neutral_or_flat_events=neutral_flat,
        )


def calculate_performance(result: TradeSimulationResult) -> BacktestPerformanceMetrics:
    """Convenience API for deterministic backtest performance calculation."""
    return BacktestMetricsCalculator().calculate(result)
