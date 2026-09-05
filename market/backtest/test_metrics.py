"""Tests for Phase 2.5.6 backtest performance metrics."""

from market.backtest.metrics import BacktestMetricsCalculator, BacktestMetricsError, calculate_performance
from market.backtest.models import BacktestFrame
from market.backtest.position import PositionSide
from market.backtest.trade import TradeSimulator
from market.models import Candle
from market.strategy.models import SignalDirection
import pytest


def _frame(index: int, close: float) -> BacktestFrame:
    candles = tuple(Candle(timestamp=f"2026-01-01T00:0{i}:00+00:00", timestamp_utc=f"2026-01-01T00:0{i}:00+00:00", open=100.0, high=100.0, low=100.0, close=float(close if i == index else 100.0), volume=0.0) for i in range(index + 1))
    return BacktestFrame(index=index, candle=candles[-1], available_candles=candles)


def test_basic_profit_metrics():
    result = TradeSimulator(quantity=2).simulate([_frame(0,100), _frame(1,110)], lambda f: SignalDirection.LONG, close_at_end=True)
    m = calculate_performance(result)
    assert m.net_pnl == 20.0
    assert m.final_equity == 10020.0
    assert m.total_return == 0.002
    assert m.total_return_pct == 0.2
    assert m.trade_count == 1
    assert m.winning_trades == 1
    assert m.win_rate == 1.0
    assert m.gross_profit == 20.0
    assert m.profit_factor is None


def test_loss_and_profit_factor():
    frames=[_frame(0,100),_frame(1,110),_frame(2,100),_frame(3,90)]
    signals=[SignalDirection.LONG,SignalDirection.LONG,SignalDirection.SHORT,SignalDirection.SHORT]
    result=TradeSimulator(quantity=1).simulate(frames, lambda f: signals[f.index], close_at_end=True)
    m=BacktestMetricsCalculator().calculate(result)
    assert m.trade_count == 2
    assert m.winning_trades == 1
    assert m.losing_trades == 0
    assert m.breakeven_trades == 1
    assert m.gross_profit == 10.0
    assert m.gross_loss == 0.0
    assert m.profit_factor is None
    assert m.average_win == 10.0
    assert m.average_loss == 0.0


def test_long_short_breakdown_and_exposure():
    frames=[_frame(0,100),_frame(1,110),_frame(2,105)]
    signals=[SignalDirection.LONG,SignalDirection.SHORT,SignalDirection.SHORT]
    result=TradeSimulator().simulate(frames, lambda f: signals[f.index], close_at_end=True)
    m=calculate_performance(result)
    assert m.long_trades == 1
    assert m.short_trades == 1
    assert m.long_net_pnl == 10.0
    assert m.short_net_pnl == 5.0
    assert m.exposure_events == 3
    assert m.long_exposure_events == 1
    assert m.short_exposure_events == 2
    assert m.neutral_or_flat_events == 1


def test_max_drawdown_uses_marked_equity():
    frames=[_frame(0,100),_frame(1,120),_frame(2,90),_frame(3,100)]
    result=TradeSimulator().simulate(frames, lambda f: SignalDirection.LONG, close_at_end=True)
    m=calculate_performance(result)
    assert m.max_drawdown == 30.0
    assert m.max_drawdown_pct == (30.0/10020.0)*100.0


def test_empty_simulation_metrics_are_defined():
    result=TradeSimulator().simulate([], lambda f: SignalDirection.LONG)
    m=calculate_performance(result)
    assert m.trade_count == 0
    assert m.net_pnl == 0.0
    assert m.win_rate == 0.0
    assert m.loss_rate == 0.0
    assert m.max_drawdown == 0.0
    assert m.profit_factor is None


def test_serialization_is_deterministic():
    result=TradeSimulator().simulate([_frame(0,100),_frame(1,105)], lambda f: SignalDirection.LONG, close_at_end=True)
    a=calculate_performance(result).to_dict()
    b=calculate_performance(result).to_dict()
    assert a == b


def test_invalid_result_rejected():
    with pytest.raises(BacktestMetricsError):
        calculate_performance(object())
