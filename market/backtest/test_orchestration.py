"""Tests for Phase 2.5.8 orchestration and Phase 2.5.10 timing semantics."""

import pytest

from market.backtest.models import (
    BacktestConfig,
    BacktestDataset,
    BacktestRunMetadata,
    ExecutionTiming,
)
from market.backtest.orchestration import (
    BacktestOrchestrationError,
    BacktestOrchestrator,
    run_backtest,
)
from market.backtest.trade import TradeSimulator
from market.models import Candle
from market.strategy.models import SignalDirection


def _candle(i, close, open_price=None):
    if open_price is None:
        open_price = close
    return Candle(
        timestamp=1704067200 + i * 300,
        timestamp_utc=f"2026-01-01T00:{i * 5:02d}:00+00:00",
        open=float(open_price),
        high=max(float(open_price), float(close)),
        low=min(float(open_price), float(close)),
        close=float(close),
        volume=0.0,
    )


def _dataset(candles=None):
    if candles is None:
        candles = tuple(_candle(i, p) for i, p in enumerate((100, 110, 120)))
    return BacktestDataset(pair="EURUSD", interval="5m", candles=tuple(candles), provider="test")


def _meta(capital=10000, warmup=0, candle_count=3):
    return BacktestRunMetadata(
        config=BacktestConfig(
            pair="EURUSD",
            interval="5m",
            initial_capital=capital,
            warmup_candles=warmup,
        ),
        dataset_pair="EURUSD",
        dataset_interval="5m",
        dataset_candle_count=candle_count,
        strategy_ids=("test",),
    )


def test_default_orchestration_uses_next_bar_open_and_does_not_same_bar_execute():
    dataset = _dataset(
        (
            _candle(0, 100, 100),
            _candle(1, 120, 110),
            _candle(2, 130, 125),
        )
    )
    report = run_backtest(dataset, _meta(candle_count=3), lambda frame: SignalDirection.LONG if frame.index == 0 else SignalDirection.NEUTRAL, close_at_end=True)
    assert report.run_metadata.config.execution_timing is ExecutionTiming.NEXT_BAR_OPEN
    assert report.performance.net_pnl == 20.0
    assert report.performance.trade_count == 1
    assert report.simulation.trades[0].entry_index == 1
    assert report.simulation.trades[0].entry_price == 110.0
    assert report.simulation.trades[0].exit_index == 2
    assert report.simulation.trades[0].exit_price == 130.0
    execution_event = next(event for event in report.simulation.events if event.index == 1)
    assert execution_event.signal_index == 0
    assert execution_event.signal_timestamp_utc == dataset.candles[0].timestamp_utc
    assert execution_event.price == 110.0


def test_last_bar_signal_is_not_executed_without_a_future_bar():
    dataset = _dataset((
        _candle(0, 100),
        _candle(1, 110),
    ))
    report = run_backtest(dataset, _meta(candle_count=2), lambda frame: SignalDirection.NEUTRAL if frame.index == 0 else SignalDirection.LONG)
    assert report.performance.trade_count == 0
    assert report.simulation.final_account.position_side.value == "FLAT"


def test_orchestrator_honors_warmup_before_calling_provider():
    calls = []
    report = run_backtest(
        _dataset(),
        _meta(warmup=2),
        lambda frame: calls.append(frame.index) or SignalDirection.LONG,
        close_at_end=True,
    )
    assert calls == [1, 2]
    assert report.performance.trade_count == 1
    # Signal at frame 1 executes at frame 2 open/close (120), so no P&L.
    assert report.performance.net_pnl == 0.0


def test_warmup_neutral_does_not_open_position():
    report = run_backtest(
        _dataset((
            _candle(0, 100),
            _candle(1, 110),
        )),
        _meta(warmup=3, candle_count=2),
        lambda frame: SignalDirection.LONG,
        close_at_end=True,
    )
    assert report.performance.trade_count == 0
    assert report.performance.net_pnl == 0.0


def test_injected_simulator_preserves_friction_and_quantity():
    simulator = TradeSimulator(initial_capital=10000, quantity=2)
    dataset = _dataset((
        _candle(0, 100),
        _candle(1, 120, 110),
        _candle(2, 130, 125),
    ))
    report = BacktestOrchestrator(simulator).run(
        dataset,
        _meta(candle_count=3),
        lambda frame: SignalDirection.LONG if frame.index == 0 else SignalDirection.NEUTRAL,
        close_at_end=True,
    )
    assert report.performance.net_pnl == 40.0


def test_capital_mismatch_is_rejected():
    with pytest.raises(BacktestOrchestrationError):
        BacktestOrchestrator(TradeSimulator(initial_capital=5000)).run(
            _dataset(), _meta(), lambda frame: SignalDirection.LONG
        )


def test_pair_mismatch_is_rejected():
    bad = BacktestDataset(pair="GBPUSD", interval="5m", candles=_dataset().candles, provider="test")
    with pytest.raises(BacktestOrchestrationError):
        run_backtest(bad, _meta(), lambda frame: SignalDirection.LONG)


def test_invalid_signal_from_provider_is_rejected():
    with pytest.raises(BacktestOrchestrationError):
        run_backtest(_dataset(), _meta(), lambda frame: "LONG")


def test_provider_failure_is_wrapped_with_frame_context():
    with pytest.raises(BacktestOrchestrationError, match="frame 0"):
        run_backtest(_dataset(), _meta(), lambda frame: (_ for _ in ()).throw(RuntimeError("boom")))


def test_empty_dataset_produces_empty_report():
    empty = BacktestDataset(pair="EURUSD", interval="5m", candles=(), provider="test")
    report = run_backtest(empty, _meta(), lambda frame: SignalDirection.LONG)
    assert report.performance.trade_count == 0
    assert report.equity_curve == ()


def test_deterministic_orchestration():
    a = run_backtest(
        _dataset(tuple(_candle(i, p) for i, p in enumerate((100, 110, 105)))),
        _meta(candle_count=3),
        lambda frame: SignalDirection.LONG if frame.index == 0 else SignalDirection.NEUTRAL,
        close_at_end=True,
    ).to_dict()
    b = run_backtest(
        _dataset(tuple(_candle(i, p) for i, p in enumerate((100, 110, 105)))),
        _meta(candle_count=3),
        lambda frame: SignalDirection.LONG if frame.index == 0 else SignalDirection.NEUTRAL,
        close_at_end=True,
    ).to_dict()
    assert a == b
