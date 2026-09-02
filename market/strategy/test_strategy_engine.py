from market.strategy import EvaluationStatus, SignalDirection, StrategyEngine
from market.strategy.strategies import TrendMomentumStrategy

def analysis(ema_fast=1.161, ema_slow=1.160, rsi=60, hist=.0002, candles=100, interval="5m"):
    return {"success": True, "pair":"EURUSD", "interval":interval, "candle_count":candles, "latest_timestamp_utc":"2026-09-03T07:33:49Z", "indicators":{"ema_fast":{"value":ema_fast},"ema_slow":{"value":ema_slow},"rsi":{"value":rsi},"macd":{"histogram":hist}}, "classification":{"trend":"BULLISH" if ema_fast > ema_slow else "BEARISH", "volatility":"LOW"}, "metadata":{"latest_close":1.1611}}

def test_register_and_list():
    e=StrategyEngine([TrendMomentumStrategy()]); assert e.get("trend_momentum"); assert e.list_strategies()[0]["strategy_id"]=="trend_momentum"
def test_bullish_long():
    r=StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum",analysis()); assert r["signal"]["direction"]=="LONG"; assert r["signal"]["score"]>=.6
def test_bearish_short():
    r=StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum",analysis(1.159,1.160,40,-.0002)); assert r["signal"]["direction"]=="SHORT"; assert r["signal"]["score"]<=-.6
def test_mixed_neutral():
    r=StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum",analysis(rsi=50,hist=-.0002)); assert r["signal"]["direction"]=="NEUTRAL"
def test_insufficient():
    r=StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum",analysis(candles=20)); assert r["status"]==EvaluationStatus.INSUFFICIENT_DATA.value; assert r["signal"] is None
def test_bad_timeframe():
    r=StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum",analysis(interval="1h")); assert r["status"]==EvaluationStatus.INVALID_INPUT.value
def test_unknown_strategy():
    r=StrategyEngine().evaluate("missing",analysis()); assert r["status"]==EvaluationStatus.INVALID_INPUT.value
def test_failed_analysis():
    a=analysis(); a["success"]=False; r=StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum",a); assert r["status"]==EvaluationStatus.INVALID_INPUT.value
def test_deterministic():
    e=StrategyEngine([TrendMomentumStrategy()]); assert e.evaluate("trend_momentum",analysis())==e.evaluate("trend_momentum",analysis())
def test_duplicate_registration():
    e=StrategyEngine([TrendMomentumStrategy()])
    try: e.register(TrendMomentumStrategy()); assert False
    except ValueError: pass
