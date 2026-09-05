from market.strategy import EvaluationStatus, SignalDirection, StrategyEngine
from market.strategy.models import ConditionStatus
from market.strategy.strategies import TrendMomentumStrategy


def analysis(ema_fast=1.161, ema_slow=1.160, rsi=60, hist=.0002, candles=100, interval="5m", trend=None):
    return {
        "success": True, "pair": "EURUSD", "interval": interval, "candle_count": candles,
        "latest_timestamp_utc": "2026-09-03T07:33:49Z",
        "indicators": {"ema_fast": {"value": ema_fast}, "ema_slow": {"value": ema_slow}, "rsi": {"value": rsi}, "macd": {"histogram": hist}},
        "classification": {"trend": trend or ("BULLISH" if ema_fast > ema_slow else "BEARISH" if ema_fast < ema_slow else "NEUTRAL"), "volatility": "LOW"},
        "metadata": {"latest_close": 1.1611},
    }


def test_register_and_list():
    e = StrategyEngine([TrendMomentumStrategy()])
    assert e.get("trend_momentum")
    assert e.list_strategies()[0]["strategy_id"] == "trend_momentum"


def test_bullish_long():
    r = StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum", analysis())
    assert r["signal"]["direction"] == "LONG"
    assert r["signal"]["score"] >= .6
    assert r["signal"]["metadata"]["agreement"] == 1.0


def test_bearish_short():
    r = StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum", analysis(1.159, 1.160, 40, -.0002))
    assert r["signal"]["direction"] == "SHORT"
    assert r["signal"]["score"] <= -.6


def test_mixed_neutral():
    r = StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum", analysis(rsi=50, hist=-.0002))
    assert r["signal"]["direction"] == "NEUTRAL"


def test_insufficient():
    r = StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum", analysis(candles=20))
    assert r["status"] == EvaluationStatus.INSUFFICIENT_DATA.value
    assert r["signal"] is None


def test_bad_timeframe():
    r = StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum", analysis(interval="1h"))
    assert r["status"] == EvaluationStatus.INVALID_INPUT.value


def test_unknown_strategy():
    r = StrategyEngine().evaluate("missing", analysis())
    assert r["status"] == EvaluationStatus.INVALID_INPUT.value


def test_failed_analysis():
    a = analysis(); a["success"] = False
    r = StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum", a)
    assert r["status"] == EvaluationStatus.INVALID_INPUT.value


def test_deterministic():
    e = StrategyEngine([TrendMomentumStrategy()])
    assert e.evaluate("trend_momentum", analysis()) == e.evaluate("trend_momentum", analysis())


def test_duplicate_registration():
    e = StrategyEngine([TrendMomentumStrategy()])
    try:
        e.register(TrendMomentumStrategy())
        assert False
    except ValueError:
        pass


def test_positive_macd_cannot_confirm_bearish_direction():
    r = StrategyEngine([TrendMomentumStrategy()]).evaluate(
        "trend_momentum", analysis(1.159, 1.160, 40, .0002)
    )
    conditions = {c["condition_id"]: c for c in r["signal"]["conditions"]}
    assert conditions["macd_confirmation"]["status"] == ConditionStatus.NOT_SATISFIED.value
    assert conditions["macd_confirmation"]["expected"] == "MACD histogram > 0"
    assert r["signal"]["direction"] == "NEUTRAL"


def test_negative_macd_cannot_confirm_bullish_direction():
    r = StrategyEngine([TrendMomentumStrategy()]).evaluate(
        "trend_momentum", analysis(1.161, 1.160, 60, -.0002)
    )
    conditions = {c["condition_id"]: c for c in r["signal"]["conditions"]}
    assert conditions["macd_confirmation"]["status"] == ConditionStatus.NOT_SATISFIED.value
    assert conditions["macd_confirmation"]["expected"] == "MACD histogram < 0"
    assert r["signal"]["direction"] == "NEUTRAL"


def test_trend_and_ema_conflict_does_not_create_direction():
    a = analysis(trend="BEARISH")
    r = StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum", a)
    assert r["signal"]["direction"] == "NEUTRAL"
    assert r["signal"]["metadata"]["directional_bias"] is None


def test_rsi_confirmation_is_direction_specific():
    strategy = TrendMomentumStrategy()
    bullish = strategy.evaluate(analysis(rsi=60))
    bearish = strategy.evaluate(analysis(1.159, 1.160, 40, -.0002))
    b = {c.condition_id: c for c in strategy.evaluate(analysis(rsi=60)).signal.conditions}
    s = {c.condition_id: c for c in strategy.evaluate(analysis(1.159, 1.160, 40, -.0002)).signal.conditions}
    assert b["rsi_confirmation"].status == ConditionStatus.SATISFIED
    assert s["rsi_confirmation"].status == ConditionStatus.SATISFIED
    assert bullish.signal.direction == SignalDirection.LONG
    assert bearish.signal.direction == SignalDirection.SHORT


def test_rsi_near_midpoint_does_not_count_as_confirmation():
    r = TrendMomentumStrategy().evaluate(analysis(rsi=50.5))
    conditions = {c.condition_id: c for c in r.signal.conditions}
    assert conditions["rsi_confirmation"].status == ConditionStatus.UNAVAILABLE


def test_signal_conditions_expose_direction():
    r = TrendMomentumStrategy().evaluate(analysis())
    assert all(c["direction"] == "LONG" for c in r.signal.to_dict()["conditions"])


def test_evaluated_result_requires_signal_contract():
    from market.strategy.models import EvaluationStatus, StrategyEvaluation
    strategy = TrendMomentumStrategy()
    try:
        StrategyEvaluation(strategy.definition, EvaluationStatus.EVALUATED, "EURUSD", "5m", None, None, 0, 0, 0)
        assert False
    except ValueError:
        pass


def test_engine_rejects_mismatched_strategy_result_identity():
    class BadStrategy(TrendMomentumStrategy):
        def evaluate(self, a):
            result = super().evaluate(a)
            return result.__class__(result.strategy, result.status, "GBPUSD", result.interval, result.timestamp_utc, result.signal, result.condition_count, result.satisfied_count, result.unavailable_count, result.metadata, result.error)

    e = StrategyEngine([BadStrategy()])
    r = e.evaluate("trend_momentum", analysis())
    assert r["status"] == EvaluationStatus.INVALID_INPUT.value


def test_invalid_strategy_parameters_are_rejected():
    for params in (
        {"minimum_agreement": 2},
        {"minimum_score": -1},
        {"rsi_bullish_min": 49},
        {"macd_weight": float("inf")},
    ):
        try:
            TrendMomentumStrategy(params)
            assert False
        except ValueError:
            pass


def test_evaluation_preserves_strategy_identity_and_timeframe():
    r = StrategyEngine([TrendMomentumStrategy()]).evaluate("trend_momentum", analysis())
    assert r["strategy_id"] == "trend_momentum"
    assert r["strategy_version"] == "1.1.1"
    assert r["interval"] == "5m"
    assert r["timeframe"] == "5m"


def test_evaluation_timeframe_alias_matches_interval():
    result = TrendMomentumStrategy().evaluate(analysis())
    assert result.timeframe == result.interval == "5m"
