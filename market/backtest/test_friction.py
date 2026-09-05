"""Tests for Phase 2.5.5 execution friction."""

import pytest

from market.backtest.friction import (
    ExecutionFrictionConfig,
    ExecutionFrictionError,
    ExecutionFrictionModel,
)
from market.backtest.position import PositionSide
from market.backtest.trade import TradeSimulator
from market.backtest.models import BacktestFrame
from market.models import Candle
from market.strategy.models import SignalDirection


def _frame(index: int, close: float) -> BacktestFrame:
    candles = tuple(
        Candle(
            timestamp=f"2026-01-01T00:0{i}:00+00:00",
            timestamp_utc=f"2026-01-01T00:0{i}:00+00:00",
            open=100.0, high=100.0, low=100.0,
            close=float(close if i == index else 100.0), volume=0.0,
        )
        for i in range(index + 1)
    )
    return BacktestFrame(index=index, candle=candles[-1], available_candles=candles)


def test_zero_friction_preserves_baseline_pnl():
    result = TradeSimulator(quantity=2).simulate(
        [_frame(0, 100), _frame(1, 110)],
        lambda f: SignalDirection.LONG,
        close_at_end=True,
    )
    assert result.trades[0].realized_pnl == 20.0
    assert result.trades[0].transaction_costs == 0.0


def test_long_entry_and_exit_apply_half_spread_and_slippage():
    model = ExecutionFrictionModel(ExecutionFrictionConfig(spread=2.0, slippage=0.5))
    entry = model.fill(100.0, 1.0, PositionSide.LONG, is_entry=True)
    exit_ = model.fill(110.0, 1.0, PositionSide.LONG, is_entry=False)
    assert entry.execution_price == 101.5
    assert exit_.execution_price == 108.5


def test_short_entry_and_exit_apply_adverse_prices():
    model = ExecutionFrictionModel(ExecutionFrictionConfig(spread=2.0, slippage=0.5))
    entry = model.fill(100.0, 1.0, PositionSide.SHORT, is_entry=True)
    exit_ = model.fill(90.0, 1.0, PositionSide.SHORT, is_entry=False)
    assert entry.execution_price == 98.5
    assert exit_.execution_price == 91.5


def test_transaction_costs_are_quantity_and_execution_based():
    model = ExecutionFrictionModel(ExecutionFrictionConfig(transaction_cost_per_unit=0.25, fixed_transaction_cost=1.0))
    fill = model.fill(100.0, 4.0, PositionSide.LONG, is_entry=True)
    assert fill.transaction_cost == 2.0


def test_friction_reduces_long_realized_pnl():
    config = ExecutionFrictionConfig(spread=2.0, slippage=0.5, transaction_cost_per_unit=1.0, fixed_transaction_cost=1.0)
    result = TradeSimulator(quantity=2, friction=config).simulate(
        [_frame(0, 100), _frame(1, 110)],
        lambda f: SignalDirection.LONG,
        close_at_end=True,
    )
    trade = result.trades[0]
    assert trade.gross_pnl == 14.0
    assert trade.transaction_costs == 6.0
    assert trade.realized_pnl == 8.0


def test_friction_reduces_short_realized_pnl():
    config = ExecutionFrictionConfig(spread=2.0, slippage=0.5)
    result = TradeSimulator(quantity=2, friction=config).simulate(
        [_frame(0, 100), _frame(1, 90)],
        lambda f: SignalDirection.SHORT,
        close_at_end=True,
    )
    # Entry 98.5, exit 91.5 => 14 gross P&L.
    assert result.trades[0].gross_pnl == 14.0
    assert result.trades[0].realized_pnl == 14.0


def test_reversal_charges_friction_on_both_legs():
    config = ExecutionFrictionConfig(spread=2.0, slippage=0.5)
    result = TradeSimulator(quantity=1, friction=config).simulate(
        [_frame(0, 100), _frame(1, 110), _frame(2, 90)],
        lambda f: [SignalDirection.LONG, SignalDirection.LONG, SignalDirection.SHORT][f.index],
    )
    assert len(result.trades) == 1
    assert result.trades[0].realized_pnl == -13.0
    assert result.final_account.position_side is PositionSide.SHORT


def test_invalid_friction_values_rejected():
    with pytest.raises(ExecutionFrictionError):
        ExecutionFrictionConfig(spread=-1)
    with pytest.raises(ExecutionFrictionError):
        ExecutionFrictionConfig(slippage=float("nan"))


def test_friction_configuration_is_serializable_and_deterministic():
    config = ExecutionFrictionConfig(spread=0.0002, slippage=0.00005, transaction_cost_per_unit=0.1, fixed_transaction_cost=0.5)
    assert config.to_dict() == {
        "spread": 0.0002,
        "slippage": 0.00005,
        "transaction_cost_per_unit": 0.1,
        "fixed_transaction_cost": 0.5,
    }
    model = ExecutionFrictionModel(config)
    assert model.describe()["config"] == config.to_dict()
