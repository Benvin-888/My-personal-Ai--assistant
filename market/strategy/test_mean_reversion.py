"""Tests for the deterministic APEX mean-reversion strategy."""

import pytest

from market.strategy.models import ConditionStatus, EvaluationStatus, SignalDirection
from market.strategy.strategies import MeanReversionStrategy


def analysis(*, rsi=25.0, close=0.99, middle=1.0, upper=1.01, lower=0.99, candles=100):
    return {
        "success": True,
        "market": "forex",
        "analysis": "technical",
        "pair": "EURUSD",
        "interval": "5m",
        "candle_count": candles,
        "latest_timestamp_utc": "2026-09-05T12:00:00Z",
        "indicators": {
            "rsi": {"value": rsi},
            "bollinger_bands": {
                "middle": middle,
                "upper": upper,
                "lower": lower,
            },
        },
        "metadata": {"latest_close": close},
    }


def test_oversold_and_lower_band_produce_long():
    result = MeanReversionStrategy().evaluate(analysis())

    assert result.status == EvaluationStatus.EVALUATED
    assert result.signal.direction == SignalDirection.LONG
    assert result.signal.score == pytest.approx(1.0)
    assert result.signal.metadata["agreement"] == pytest.approx(1.0)
    assert result.satisfied_count == 2
    assert result.unavailable_count == 0


def test_overbought_and_upper_band_produce_short():
    result = MeanReversionStrategy().evaluate(
        analysis(rsi=75.0, close=1.01)
    )

    assert result.signal.direction == SignalDirection.SHORT
    assert result.signal.score == pytest.approx(-1.0)
    assert all(
        condition.direction == SignalDirection.SHORT
        for condition in result.signal.conditions
    )


def test_non_extreme_market_is_neutral_and_not_satisfied():
    result = MeanReversionStrategy().evaluate(
        analysis(rsi=50.0, close=1.0)
    )

    assert result.signal.direction == SignalDirection.NEUTRAL
    assert result.signal.score == pytest.approx(0.0)
    assert result.satisfied_count == 0
    assert result.unavailable_count == 0
    assert all(
        condition.status == ConditionStatus.NOT_SATISFIED
        for condition in result.signal.conditions
    )


def test_conflicting_extremes_are_conservatively_neutral():
    result = MeanReversionStrategy().evaluate(
        analysis(rsi=25.0, close=1.01)
    )

    assert result.signal.direction == SignalDirection.NEUTRAL
    assert result.signal.score == pytest.approx(0.0)
    assert result.signal.metadata["agreement"] == pytest.approx(0.55)
    assert result.satisfied_count == 2
    assert result.unavailable_count == 0


def test_one_directional_condition_is_neutral_without_confirmation():
    result = MeanReversionStrategy().evaluate(
        analysis(rsi=25.0, close=1.0)
    )

    assert result.signal.direction == SignalDirection.NEUTRAL
    assert result.signal.score == pytest.approx(0.0)
    assert result.satisfied_count == 1
    assert result.unavailable_count == 0


def test_insufficient_candles():
    result = MeanReversionStrategy().evaluate(analysis(candles=19))

    assert result.status == EvaluationStatus.INSUFFICIENT_DATA
    assert result.signal is None


def test_missing_required_indicator_is_insufficient():
    payload = analysis()
    del payload["indicators"]["bollinger_bands"]

    result = MeanReversionStrategy().evaluate(payload)

    assert result.status == EvaluationStatus.INSUFFICIENT_DATA
    assert result.signal is None


def test_invalid_bollinger_relationship_is_rejected():
    result = MeanReversionStrategy().evaluate(
        analysis(middle=1.02, upper=1.01, lower=0.99)
    )

    assert result.status == EvaluationStatus.INSUFFICIENT_DATA
    assert "Bollinger Band relationships" in result.error


def test_parameters_are_exposed_in_definition():
    strategy = MeanReversionStrategy(
        {
            "rsi_oversold_max": 28.0,
            "minimum_score": 0.70,
            "rsi_weight": 0.60,
            "bollinger_weight": 0.40,
        }
    )

    assert strategy.definition.parameters["rsi_oversold_max"] == 28.0
    assert strategy.definition.parameters["minimum_score"] == 0.70
    assert strategy.definition.parameters["rsi_weight"] == 0.60


@pytest.mark.parametrize(
    "parameters",
    [
        {"minimum_score": -0.1},
        {"minimum_score": 1.1},
        {"minimum_agreement": -0.1},
        {"rsi_oversold_max": 55.0},
        {"rsi_overbought_min": 45.0},
        {"rsi_weight": -1.0},
        {"bollinger_weight": -1.0},
        {"rsi_weight": 0.0, "bollinger_weight": 0.0},
    ],
)
def test_invalid_parameters_are_rejected(parameters):
    with pytest.raises(ValueError):
        MeanReversionStrategy(parameters)
