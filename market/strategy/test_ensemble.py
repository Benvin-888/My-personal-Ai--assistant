from __future__ import annotations

import pytest

from market.strategy import StrategyConfig, StrategyFactory, StrategyRegistry
from market.strategy.ensemble import (
    EnsembleConfig,
    EnsembleEngine,
    EnsembleStatus,
    StrategyContribution,
    score_contributions,
)
from market.strategy.models import EvaluationStatus, SignalDirection
from market.strategy.strategies import TrendMomentumStrategy


from market.strategy.base import Strategy
from market.strategy.models import StrategyDefinition, StrategyEvaluation, StrategySignal


class StaticStrategy(Strategy):
    def __init__(self, strategy_id, direction, score, timeframe="5m"):
        self._definition = StrategyDefinition(
            strategy_id=strategy_id,
            name=strategy_id,
            version="1.0.0",
            description="Deterministic test strategy.",
            timeframe=timeframe,
            supported_pairs=("EURUSD",),
            parameters={},
        )
        self._direction = direction
        self._score = score

    @property
    def definition(self):
        return self._definition

    def evaluate(self, analysis):
        signal = StrategySignal(
            self._direction,
            self._score,
            "Static deterministic test result.",
        )
        return StrategyEvaluation(
            self.definition,
            EvaluationStatus.EVALUATED,
            analysis["pair"],
            analysis["interval"],
            analysis.get("latest_timestamp_utc"),
            signal,
            1,
            1,
            0,
        )


def analysis(ema_fast=1.161, ema_slow=1.160, rsi=60, hist=.0002, candles=100):
    return {
        "success": True,
        "pair": "EURUSD",
        "interval": "5m",
        "candle_count": candles,
        "latest_timestamp_utc": "2026-09-04T00:00:00Z",
        "indicators": {
            "ema_fast": {"value": ema_fast},
            "ema_slow": {"value": ema_slow},
            "rsi": {"value": rsi},
            "macd": {"histogram": hist},
        },
        "classification": {
            "trend": "BULLISH" if ema_fast > ema_slow else "BEARISH" if ema_fast < ema_slow else "NEUTRAL",
            "volatility": "LOW",
        },
        "metadata": {"latest_close": 1.1611},
    }


def contribution(strategy_id, direction, score, weight=1.0):
    return StrategyContribution(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        direction=direction,
        score=score,
        weight=weight,
        weighted_score=score * weight,
        status=EvaluationStatus.EVALUATED,
    )


def factory():
    f = StrategyFactory()
    f.register("trend_momentum", TrendMomentumStrategy)
    return f


def registry(weight=1.0):
    r = StrategyRegistry()
    r.register(
        TrendMomentumStrategy(),
        StrategyConfig(strategy_id="trend_momentum", weight=weight),
    )
    return r


def test_ensemble_config_validates_thresholds():
    with pytest.raises(ValueError):
        EnsembleConfig(minimum_score=1.1)
    with pytest.raises(ValueError):
        EnsembleConfig(minimum_active_strategies=0)


def test_scoring_unanimous_long():
    result = score_contributions((
        contribution("a", SignalDirection.LONG, .8),
        contribution("b", SignalDirection.LONG, .6),
    ))
    assert result["decision"] == SignalDirection.LONG
    assert result["agreement"] == pytest.approx(1.0)
    assert result["conflict"] == pytest.approx(0.0)
    assert result["ensemble_score"] == pytest.approx(.7)


def test_scoring_conflict_is_not_majority_only():
    result = score_contributions((
        contribution("a", SignalDirection.LONG, .8),
        contribution("b", SignalDirection.SHORT, -.7),
    ))
    assert result["decision"] == SignalDirection.LONG
    assert result["agreement"] == pytest.approx(8 / 15)
    assert result["conflict"] == pytest.approx(7 / 15)


def test_scoring_neutral_does_not_create_opposition():
    result = score_contributions((
        contribution("a", SignalDirection.LONG, .8),
        contribution("b", SignalDirection.NEUTRAL, .0),
    ))
    assert result["decision"] == SignalDirection.LONG
    assert result["agreement"] == pytest.approx(1.0)
    assert result["ensemble_score"] == pytest.approx(.8)


def test_equal_opposing_evidence_is_neutral():
    result = score_contributions((
        contribution("a", SignalDirection.LONG, .8),
        contribution("b", SignalDirection.SHORT, -.8),
    ))
    assert result["decision"] == SignalDirection.NEUTRAL
    assert result["ensemble_score"] == pytest.approx(0.0)


def test_weights_change_directional_evidence():
    result = score_contributions((
        contribution("a", SignalDirection.LONG, .7, weight=2.0),
        contribution("b", SignalDirection.SHORT, -.8, weight=1.0),
    ))
    assert result["decision"] == SignalDirection.LONG
    assert result["ensemble_score"] == pytest.approx((1.4 - .8) / 3)


def test_registry_weight_is_serializable_and_preserved():
    config = StrategyConfig(strategy_id="trend_momentum", weight=1.5)
    assert config.to_dict()["weight"] == 1.5
    r = StrategyRegistry()
    r.register(TrendMomentumStrategy(), config)
    r.set_enabled("trend_momentum", False)
    assert r.get_config("trend_momentum").weight == 1.5


def test_ensemble_single_strategy_can_be_evaluated_with_lower_threshold():
    engine = EnsembleEngine(
        EnsembleConfig(minimum_score=.5, minimum_agreement=.8, minimum_active_strategies=1)
    )
    result = engine.evaluate(analysis(), registry(), factory())
    assert result["status"] == EnsembleStatus.EVALUATED.value
    assert result["decision"] == SignalDirection.LONG.value
    assert result["strategies"]["evaluated"] == 1
    assert result["contributions"][0]["strategy_id"] == "trend_momentum"


def test_default_two_strategy_minimum_prevents_single_strategy_decision():
    result = EnsembleEngine().evaluate(analysis(), registry(), factory())
    assert result["status"] == EnsembleStatus.EVALUATED.value
    assert result["decision"] == SignalDirection.NEUTRAL.value
    assert result["metadata"]["thresholds_passed"] is False


def test_no_compatible_strategies_is_explicit():
    r = registry()
    r.set_enabled("trend_momentum", False)
    result = EnsembleEngine().evaluate(analysis(), r, factory())
    assert result["status"] == EnsembleStatus.NO_ACTIVE_STRATEGIES.value
    assert result["decision"] == SignalDirection.NEUTRAL.value


def test_unsuccessful_analysis_is_rejected():
    bad = analysis()
    bad["success"] = False
    result = EnsembleEngine().evaluate(bad, registry(), factory())
    assert result["status"] == EnsembleStatus.INVALID_INPUT.value


def test_contributions_are_deterministically_sorted():
    items = (
        contribution("z", SignalDirection.LONG, .5),
        contribution("a", SignalDirection.LONG, .5),
    )
    # Scoring itself is order-independent.
    first = score_contributions(items)
    second = score_contributions(tuple(reversed(items)))
    assert first == second


def test_two_configured_strategies_can_reach_consensus():
    r = StrategyRegistry()
    r.register(StaticStrategy("alpha", SignalDirection.LONG, .9), StrategyConfig("alpha", weight=1.0))
    r.register(StaticStrategy("beta", SignalDirection.LONG, .7), StrategyConfig("beta", weight=1.0))
    f = StrategyFactory()
    f.register("alpha", lambda parameters: StaticStrategy("alpha", SignalDirection.LONG, .9))
    f.register("beta", lambda parameters: StaticStrategy("beta", SignalDirection.LONG, .7))

    result = EnsembleEngine().evaluate(analysis(), r, f)
    assert result["decision"] == "LONG"
    assert result["strategies"]["evaluated"] == 2
    assert result["agreement"] == pytest.approx(1.0)


def test_weighted_conflict_can_still_produce_neutral():
    r = StrategyRegistry()
    r.register(StaticStrategy("alpha", SignalDirection.LONG, .7), StrategyConfig("alpha", weight=1.0))
    r.register(StaticStrategy("beta", SignalDirection.SHORT, -.8), StrategyConfig("beta", weight=1.0))
    f = StrategyFactory()
    f.register("alpha", lambda parameters: StaticStrategy("alpha", SignalDirection.LONG, .7))
    f.register("beta", lambda parameters: StaticStrategy("beta", SignalDirection.SHORT, -.8))

    result = EnsembleEngine(EnsembleConfig(minimum_score=.1, minimum_agreement=.8, minimum_active_strategies=2)).evaluate(analysis(), r, f)
    assert result["decision"] == "NEUTRAL"
    assert result["agreement"] == pytest.approx(8 / 15)


def test_invalid_weighted_score_is_rejected():
    with pytest.raises(ValueError):
        StrategyContribution(
            strategy_id="x", strategy_version="1.0.0",
            direction=SignalDirection.LONG, score=.5, weight=.2,
            weighted_score=.2, status=EvaluationStatus.EVALUATED,
        )
