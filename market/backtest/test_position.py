"""Tests for Phase 2.5.3 signal and position simulation."""

from dataclasses import replace

import pytest

from market.backtest.models import BacktestFrame
from market.backtest.position import (
    PositionAction,
    PositionSide,
    PositionSimulationError,
    PositionSimulator,
)
from market.strategy.models import SignalDirection


def _candle(ts: str, close: float):
    from market.models import Candle
    return Candle(
        timestamp=ts,
        timestamp_utc=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0.0,
    )


def _frame(index: int, close: float) -> BacktestFrame:
    candles = tuple(
        _candle(f"2026-01-01T00:0{i}:00+00:00", float(i + 1))
        for i in range(index + 1)
    )
    if index == 0:
        candles = (_candle("2026-01-01T00:00:00+00:00", close),)
    else:
        candles = tuple(
            _candle(f"2026-01-01T00:0{i}:00+00:00", float(i + 1))
            for i in range(index)
        ) + (_candle(f"2026-01-01T00:0{index}:00+00:00", close),)
    return BacktestFrame(index=index, candle=candles[-1], available_candles=candles)


def test_flat_long_opens_position():
    sim = PositionSimulator()
    event = sim.apply(_frame(0, 100.0), SignalDirection.LONG)

    assert event.action is PositionAction.OPEN
    assert event.from_side is PositionSide.FLAT
    assert event.to_side is PositionSide.LONG
    assert sim.state.side is PositionSide.LONG
    assert sim.state.entry_price == 100.0


def test_flat_short_opens_position():
    sim = PositionSimulator()
    event = sim.apply(_frame(0, 100.0), SignalDirection.SHORT)

    assert event.action is PositionAction.OPEN
    assert event.to_side is PositionSide.SHORT
    assert sim.state.side is PositionSide.SHORT


def test_same_signal_holds_existing_position_and_preserves_entry():
    sim = PositionSimulator()
    sim.apply(_frame(0, 100.0), SignalDirection.LONG)
    event = sim.apply(_frame(1, 105.0), SignalDirection.LONG)

    assert event.action is PositionAction.HOLD
    assert sim.state.entry_price == 100.0
    assert sim.state.entry_timestamp_utc == "2026-01-01T00:00:00+00:00"


def test_neutral_does_not_close_position():
    sim = PositionSimulator()
    sim.apply(_frame(0, 100.0), SignalDirection.LONG)
    event = sim.apply(_frame(1, 105.0), SignalDirection.NEUTRAL)

    assert event.action is PositionAction.HOLD
    assert event.from_side is PositionSide.LONG
    assert event.to_side is PositionSide.LONG
    assert sim.state.side is PositionSide.LONG
    assert sim.state.last_signal is SignalDirection.NEUTRAL


def test_opposite_signal_reverses_long_to_short():
    sim = PositionSimulator()
    sim.apply(_frame(0, 100.0), SignalDirection.LONG)
    event = sim.apply(_frame(1, 95.0), SignalDirection.SHORT)

    assert event.action is PositionAction.REVERSE
    assert event.from_side is PositionSide.LONG
    assert event.to_side is PositionSide.SHORT
    assert sim.state.entry_price == 95.0


def test_opposite_signal_reverses_short_to_long():
    sim = PositionSimulator()
    sim.apply(_frame(0, 100.0), SignalDirection.SHORT)
    event = sim.apply(_frame(1, 105.0), SignalDirection.LONG)

    assert event.action is PositionAction.REVERSE
    assert event.from_side is PositionSide.SHORT
    assert event.to_side is PositionSide.LONG
    assert sim.state.entry_price == 105.0


def test_every_frame_produces_one_auditable_event():
    sim = PositionSimulator()
    frames = [_frame(0, 100.0), _frame(1, 101.0), _frame(2, 99.0)]
    signals = iter(
        [SignalDirection.LONG, SignalDirection.LONG, SignalDirection.SHORT]
    )

    events = sim.simulate(frames, lambda frame: next(signals))

    assert len(events) == 3
    assert [event.index for event in events] == [0, 1, 2]
    assert [event.action for event in events] == [
        PositionAction.OPEN,
        PositionAction.HOLD,
        PositionAction.REVERSE,
    ]


def test_simulation_is_deterministic():
    frames = [_frame(0, 100.0), _frame(1, 101.0), _frame(2, 102.0)]
    signals = [SignalDirection.LONG, SignalDirection.NEUTRAL, SignalDirection.SHORT]

    first = PositionSimulator().simulate(frames, lambda frame: signals[frame.index])
    second = PositionSimulator().simulate(frames, lambda frame: signals[frame.index])

    assert [event.to_dict() for event in first] == [event.to_dict() for event in second]


def test_events_never_use_a_future_frame():
    sim = PositionSimulator()
    frames = [_frame(0, 100.0), _frame(1, 110.0)]
    seen = []

    def provider(frame):
        seen.append((frame.index, len(frame.available_candles)))
        return SignalDirection.LONG

    sim.simulate(frames, provider)

    assert seen == [(0, 1), (1, 2)]


def test_frames_must_be_chronological():
    sim = PositionSimulator()

    with pytest.raises(PositionSimulationError):
        sim.simulate(
            [_frame(1, 101.0), _frame(0, 100.0)],
            lambda frame: SignalDirection.LONG,
        )


def test_invalid_signal_is_rejected():
    sim = PositionSimulator()

    with pytest.raises(PositionSimulationError):
        sim.apply(_frame(0, 100.0), "LONG")  # type: ignore[arg-type]


def test_reset_returns_simulator_to_flat():
    sim = PositionSimulator()
    sim.apply(_frame(0, 100.0), SignalDirection.LONG)
    sim.reset()

    assert sim.state.side is PositionSide.FLAT
    assert sim.events == ()
