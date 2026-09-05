"""Tests for Phase 2.5.1 backtesting foundation models."""
from __future__ import annotations
import pytest
from market.backtest import BacktestConfig, BacktestDataset, BacktestFrame, BacktestRunMetadata, BacktestStatus, ReplayMode, ExecutionTiming
from market.models import Candle

def make_candles(count=4):
    return tuple(Candle(timestamp=1700000000+i*300, timestamp_utc=f"2023-11-14T22:{13+i*5:02d}:20Z", open=1.10+i*.001, high=1.101+i*.001, low=1.099+i*.001, close=1.1005+i*.001, volume=1000+i) for i in range(count))

def test_backtest_config_is_serializable():
    c=BacktestConfig("EURUSD","5m",25000,50,"2023-01-01T00:00:00Z","2023-01-02T00:00:00Z",500,metadata={"purpose":"regression"})
    d=c.to_dict(); assert d["pair"]=="EURUSD"; assert d["initial_capital"]==25000.0; assert d["replay_mode"]=="BAR_BY_BAR"; assert d["execution_timing"]=="NEXT_BAR_OPEN"; assert d["metadata"]["purpose"]=="regression"

def test_backtest_config_rejects_invalid_values():
    with pytest.raises(ValueError): BacktestConfig("EURUSD","5m",0)
    with pytest.raises(ValueError): BacktestConfig("EURUSD","5m",warmup_candles=-1)
    with pytest.raises(ValueError): BacktestConfig("EURUSD","5m",max_candles=0)
    with pytest.raises(ValueError): BacktestConfig("EURUSD","5m",start_timestamp_utc="2023-01-02T00:00:00Z",end_timestamp_utc="2023-01-01T00:00:00Z")

def test_dataset_validates_and_serializes():
    cs=make_candles(); d=BacktestDataset("EURUSD","5m",cs,"test-provider","EURUSD=X","1d")
    assert d.candle_count==4 and d.first_timestamp_utc==cs[0].timestamp_utc and d.latest_timestamp_utc==cs[-1].timestamp_utc
    assert len(d.to_dict()["candles"])==4

def test_dataset_rejects_invalid_candles():
    cs=make_candles()
    with pytest.raises(ValueError): BacktestDataset("EURUSD","5m",list(cs))
    with pytest.raises(ValueError): BacktestDataset("EURUSD","5m",(cs[0],{"close":1.0}))
    with pytest.raises(ValueError): BacktestDataset("EURUSD","5m",(cs[1],cs[0],cs[2]))

def test_empty_dataset_is_allowed():
    d=BacktestDataset("EURUSD","5m",()); assert d.candle_count==0 and d.first_timestamp_utc is None and d.latest_timestamp_utc is None

def test_frame_enforces_no_lookahead_prefix():
    cs=make_candles(); f=BacktestFrame(2,cs[2],cs[:3]); assert f.index==2 and f.timestamp_utc==cs[2].timestamp_utc and len(f.available_candles)==3

def test_frame_rejects_future_candles_and_mismatch():
    cs=make_candles()
    with pytest.raises(ValueError): BacktestFrame(1,cs[1],cs)
    with pytest.raises(ValueError): BacktestFrame(1,cs[2],cs[:2])

def test_run_metadata_is_serializable_and_unique():
    c=BacktestConfig("EURUSD","5m",warmup_candles=20); m=BacktestRunMetadata(c,"EURUSD","5m",1000,("mean_reversion","trend_momentum"))
    d=m.to_dict(); assert d["dataset_candle_count"]==1000 and d["strategy_ids"]==["mean_reversion","trend_momentum"]
    with pytest.raises(ValueError): BacktestRunMetadata(c,"EURUSD","5m",10,("trend_momentum","trend_momentum"))

def test_enums_are_stable_strings():
    assert BacktestStatus.READY.value=="READY" and BacktestStatus.COMPLETED.value=="COMPLETED" and ReplayMode.BAR_BY_BAR.value=="BAR_BY_BAR" and ExecutionTiming.NEXT_BAR_OPEN.value=="NEXT_BAR_OPEN"
