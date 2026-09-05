"""Tests for Phase 2.5.4 trade simulation and P&L."""

import pytest

from market.backtest.models import BacktestFrame
from market.backtest.position import PositionSide
from market.backtest.trade import (
    TradeAction,
    TradeSimulationError,
    TradeSimulator,
)
from market.models import Candle
from market.strategy.models import SignalDirection


def _frame(index: int, close: float) -> BacktestFrame:
    candles = tuple(
        Candle(
            timestamp=f"2026-01-01T00:0{i}:00+00:00",
            timestamp_utc=f"2026-01-01T00:0{i}:00+00:00",
            open=float(i + 1), high=float(i + 1), low=float(i + 1),
            close=float(close if i == index else i + 1), volume=0.0,
        )
        for i in range(index + 1)
    )
    return BacktestFrame(index=index, candle=candles[-1], available_candles=candles)


def test_long_trade_realizes_profit():
    sim = TradeSimulator(initial_capital=10_000, quantity=2)
    sim.apply(_frame(0, 100), SignalDirection.LONG)
    result = sim.simulate([_frame(0, 100), _frame(1, 110)], lambda f: SignalDirection.LONG, close_at_end=True)

    assert len(result.trades) == 1
    assert result.trades[0].side is PositionSide.LONG
    assert result.trades[0].realized_pnl == 20.0
    assert result.final_account.realized_pnl == 20.0
    assert result.final_account.equity == 10020.0


def test_short_trade_realizes_profit():
    sim = TradeSimulator(initial_capital=10_000, quantity=2)
    result = sim.simulate(
        [_frame(0, 100), _frame(1, 90)],
        lambda f: SignalDirection.SHORT,
        close_at_end=True,
    )

    assert result.trades[0].side is PositionSide.SHORT
    assert result.trades[0].realized_pnl == 20.0
    assert result.final_account.equity == 10020.0


def test_long_trade_loss_is_realized_correctly():
    result = TradeSimulator(quantity=3).simulate(
        [_frame(0, 100), _frame(1, 95)],
        lambda f: SignalDirection.LONG,
        close_at_end=True,
    )
    assert result.trades[0].realized_pnl == -15.0
    assert result.final_account.equity == 9985.0


def test_open_position_has_unrealized_pnl_when_not_closed():
    result = TradeSimulator(quantity=2).simulate(
        [_frame(0, 100), _frame(1, 110)],
        lambda f: SignalDirection.LONG,
        close_at_end=False,
    )
    assert result.trades == ()
    assert result.final_account.position_side is PositionSide.LONG
    assert result.final_account.unrealized_pnl == 20.0
    assert result.final_account.equity == 10020.0


def test_neutral_does_not_close_trade():
    result = TradeSimulator().simulate(
        [_frame(0, 100), _frame(1, 105)],
        lambda f: SignalDirection.LONG if f.index == 0 else SignalDirection.NEUTRAL,
    )
    assert result.trades == ()
    assert result.final_account.position_side is PositionSide.LONG
    assert result.events[-1].action is TradeAction.HOLD


def test_reversal_closes_old_trade_and_opens_new_position():
    result = TradeSimulator(quantity=2).simulate(
        [_frame(0, 100), _frame(1, 110), _frame(2, 90)],
        lambda f: [SignalDirection.LONG, SignalDirection.LONG, SignalDirection.SHORT][f.index],
    )
    assert len(result.trades) == 1
    assert result.trades[0].realized_pnl == -20.0
    assert result.final_account.position_side is PositionSide.SHORT
    assert result.final_account.unrealized_pnl == 0.0
    assert result.events[-1].action is TradeAction.REVERSE


def test_close_at_end_liquidates_at_final_close():
    result = TradeSimulator().simulate(
        [_frame(0, 100), _frame(1, 103)],
        lambda f: SignalDirection.LONG,
        close_at_end=True,
    )
    assert len(result.trades) == 1
    assert result.events[-1].action is TradeAction.CLOSE
    assert result.final_account.position_side is PositionSide.FLAT
    assert result.final_account.unrealized_pnl == 0.0


def test_zero_or_negative_quantity_rejected():
    with pytest.raises(TradeSimulationError):
        TradeSimulator(quantity=0)
    with pytest.raises(TradeSimulationError):
        TradeSimulator(quantity=-1)


def test_invalid_signal_rejected():
    sim = TradeSimulator()
    with pytest.raises(TradeSimulationError):
        sim.apply(_frame(0, 100), "LONG")  # type: ignore[arg-type]


def test_frames_must_be_chronological():
    sim = TradeSimulator()
    sim.apply(_frame(1, 101), SignalDirection.LONG)
    with pytest.raises(TradeSimulationError):
        sim.apply(_frame(0, 100), SignalDirection.LONG)


def test_simulation_is_deterministic():
    frames = [_frame(0, 100), _frame(1, 105), _frame(2, 102)]
    signals = [SignalDirection.LONG, SignalDirection.LONG, SignalDirection.SHORT]
    a = TradeSimulator(quantity=2).simulate(frames, lambda f: signals[f.index])
    b = TradeSimulator(quantity=2).simulate(frames, lambda f: signals[f.index])
    assert a.to_dict() == b.to_dict()


def test_pnl_is_marked_only_from_current_frame():
    seen = []
    frames = [_frame(0, 100), _frame(1, 110)]

    def provider(frame):
        seen.append((frame.index, len(frame.available_candles)))
        return SignalDirection.LONG

    TradeSimulator().simulate(frames, provider)
    assert seen == [(0, 1), (1, 2)]


def test_reset_clears_accounting_history():
    sim = TradeSimulator()
    sim.simulate([_frame(0, 100), _frame(1, 105)], lambda f: SignalDirection.LONG, close_at_end=True)
    sim.reset()
    assert sim.trades == ()
    assert sim.events == ()
    assert sim.account.position_side is PositionSide.FLAT
    assert sim.account.equity == 10000.0
