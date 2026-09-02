"""Phase 2.4.1 tests for the APEX Strategy Foundation."""

import pytest

from market.strategy import (
    ConditionStatus,
    EvaluationStatus,
    SignalDirection,
    Strategy,
    StrategyCondition,
    StrategyDefinition,
    StrategyEvaluation,
    StrategySignal,
)


def make_definition():
    return StrategyDefinition(
        strategy_id="ema_momentum",
        name="EMA Momentum",
        version="1.0.0",
        description="Example deterministic strategy contract.",
        timeframe="5m",
        supported_pairs=("EURUSD", "GBPUSD"),
        minimum_candles=50,
        parameters={"ema_fast": 20, "ema_slow": 50, "rsi": 14},
        tags=("trend", "momentum"),
    )


def make_condition(status=ConditionStatus.SATISFIED):
    return StrategyCondition(
        condition_id="ema_alignment",
        name="EMA alignment",
        description="Fast EMA is above slow EMA.",
        status=status,
        category="trend",
        value=1.1608,
        expected="fast_above_slow",
        weight=1.0,
    )


def make_signal():
    return StrategySignal(
        direction=SignalDirection.LONG,
        score=0.75,
        rationale="Trend conditions align positively.",
        conditions=(make_condition(),),
    )


def test_strategy_definition_is_serializable():
    result = make_definition().to_dict()

    assert result["strategy_id"] == "ema_momentum"
    assert result["supported_pairs"] == ["EURUSD", "GBPUSD"]
    assert result["minimum_candles"] == 50


def test_condition_is_serializable():
    result = make_condition().to_dict()

    assert result["status"] == "SATISFIED"
    assert result["category"] == "trend"
    assert result["weight"] == 1.0


def test_signal_score_is_bounded():
    signal = make_signal()
    assert signal.score == pytest.approx(0.75)
    assert signal.to_dict()["direction"] == "LONG"

    with pytest.raises(ValueError):
        StrategySignal(
            direction=SignalDirection.LONG,
            score=1.01,
            rationale="invalid",
        )


def test_evaluation_tracks_condition_completeness():
    evaluation = StrategyEvaluation(
        strategy=make_definition(),
        status=EvaluationStatus.EVALUATED,
        pair="EURUSD",
        interval="5m",
        timestamp_utc="2026-09-03T07:33:49Z",
        signal=make_signal(),
        condition_count=4,
        satisfied_count=3,
        unavailable_count=1,
    )

    assert evaluation.completeness_ratio == pytest.approx(0.75)
    result = evaluation.to_dict()
    assert result["success"] is True
    assert result["conditions"]["satisfied"] == 3


def test_evaluation_rejects_invalid_counts():
    with pytest.raises(ValueError):
        StrategyEvaluation(
            strategy=make_definition(),
            status=EvaluationStatus.EVALUATED,
            pair="EURUSD",
            interval="5m",
            timestamp_utc=None,
            signal=None,
            condition_count=2,
            satisfied_count=3,
            unavailable_count=0,
        )


def test_strategy_supports_pair_and_timeframe():
    class ExampleStrategy(Strategy):
        @property
        def definition(self):
            return make_definition()

        def evaluate(self, analysis):
            raise NotImplementedError

    strategy = ExampleStrategy()

    assert strategy.supports("EUR/USD", "5m") is True
    assert strategy.supports("GBP-USD", "5M") is True
    assert strategy.supports("USDJPY", "5m") is False
    assert strategy.supports("EURUSD", "1h") is False


def test_strategy_description_is_metadata_only():
    class ExampleStrategy(Strategy):
        @property
        def definition(self):
            return make_definition()

        def evaluate(self, analysis):
            raise NotImplementedError

    description = ExampleStrategy().describe()

    assert description["strategy_id"] == "ema_momentum"
    assert "broker" not in description
    assert "order" not in description
    assert "position_size" not in description


def test_neutral_signal_is_supported():
    signal = StrategySignal(
        direction=SignalDirection.NEUTRAL,
        score=0.0,
        rationale="Conditions do not establish directional alignment.",
        conditions=(make_condition(ConditionStatus.NOT_SATISFIED),),
    )

    assert signal.to_dict()["direction"] == "NEUTRAL"
    assert signal.to_dict()["score"] == 0.0


def test_unavailable_evaluation_can_be_structured_without_fake_signal():
    evaluation = StrategyEvaluation(
        strategy=make_definition(),
        status=EvaluationStatus.INSUFFICIENT_DATA,
        pair="EURUSD",
        interval="5m",
        timestamp_utc=None,
        signal=None,
        condition_count=4,
        satisfied_count=0,
        unavailable_count=4,
        error="Not enough candles for strategy evaluation.",
    )

    result = evaluation.to_dict()

    assert result["success"] is False
    assert result["signal"] is None
    assert result["conditions"]["completeness_ratio"] == 0.0
    assert result["error"] == "Not enough candles for strategy evaluation."
