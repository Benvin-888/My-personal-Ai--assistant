"""Phase 2.5.2 HistoricalReplayEngine tests."""

from datetime import datetime, timedelta, timezone

import pytest

from market.models import Candle
from market.backtest.models import BacktestConfig, BacktestDataset
from market.backtest.replay import HistoricalReplayEngine, HistoricalReplayError


def candles(count=6):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        Candle(
            timestamp=int((base + timedelta(minutes=i * 5)).timestamp()),
            timestamp_utc=(base + timedelta(minutes=i * 5)).isoformat().replace("+00:00", "Z"),
            open=1.1000 + i * 0.001,
            high=1.1020 + i * 0.001,
            low=1.0980 + i * 0.001,
            close=1.1010 + i * 0.001,
            volume=100 + i,
        )
        for i in range(count)
    )


def dataset(count=6):
    return BacktestDataset(pair="EURUSD", interval="5m", candles=candles(count))


def test_chronological_prefix_only():
    frames = list(HistoricalReplayEngine().frames(dataset()))
    assert [f.index for f in frames] == list(range(6))
    assert [len(f.available_candles) for f in frames] == [1, 2, 3, 4, 5, 6]
    for frame in frames:
        assert frame.available_candles == dataset().candles[: frame.index + 1]


def test_future_candles_are_never_exposed():
    ds = dataset()
    for frame in HistoricalReplayEngine().frames(ds):
        assert not any(c in frame.available_candles for c in ds.candles[frame.index + 1 :])


def test_time_bounds_are_inclusive():
    ds = dataset()
    cfg = BacktestConfig(
        "EURUSD", "5m",
        start_timestamp_utc=ds.candles[1].timestamp_utc,
        end_timestamp_utc=ds.candles[3].timestamp_utc,
    )
    assert [f.candle for f in HistoricalReplayEngine(cfg).frames(ds)] == list(ds.candles[1:4])


def test_max_candles_applies_after_filter():
    ds = dataset()
    cfg = BacktestConfig(
        "EURUSD", "5m",
        start_timestamp_utc=ds.candles[1].timestamp_utc,
        max_candles=2,
    )
    assert [f.candle for f in HistoricalReplayEngine(cfg).frames(ds)] == list(ds.candles[1:3])


def test_pair_and_interval_mismatch_rejected():
    ds = dataset()
    with pytest.raises(HistoricalReplayError):
        list(HistoricalReplayEngine(BacktestConfig("GBPUSD", "5m")).frames(ds))
    with pytest.raises(HistoricalReplayError):
        list(HistoricalReplayEngine(BacktestConfig("EURUSD", "15m")).frames(ds))


def test_warmup_boundary():
    engine = HistoricalReplayEngine(BacktestConfig("EURUSD", "5m", warmup_candles=3))
    assert [engine.is_warmup_complete(f) for f in engine.frames(dataset())] == [
        False, False, True, True, True, True
    ]


def test_callback_runs_once_in_order():
    seen = []
    result = HistoricalReplayEngine().replay(
        dataset(), lambda frame: seen.append(frame.index) or frame.index
    )
    assert seen == list(range(6))
    assert result == list(range(6))


def test_empty_dataset_and_count():
    ds = dataset(0)
    engine = HistoricalReplayEngine(BacktestConfig("EURUSD", "5m"))
    assert list(engine.frames(ds)) == []
    assert engine.count(ds) == 0


def test_invalid_inputs_rejected():
    engine = HistoricalReplayEngine()
    with pytest.raises(HistoricalReplayError):
        list(engine.frames(object()))
    with pytest.raises(HistoricalReplayError):
        engine.replay(dataset(), None)


def test_replay_is_deterministic():
    ds = dataset()
    engine = HistoricalReplayEngine(BacktestConfig("EURUSD", "5m"))
    first = [f.to_dict() for f in engine.frames(ds)]
    second = [f.to_dict() for f in engine.frames(ds)]
    assert first == second


def test_explicit_iterator_matches_frames():
    ds = dataset()
    engine = HistoricalReplayEngine()
    assert [f.to_dict() for f in engine.frames(ds)] == [
        f.to_dict() for f in engine.iter_frames(ds)
    ]
