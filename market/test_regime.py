from market.regime import (
    MarketRegime,
    MarketRegimeEngine,
    MarketRegimeError,
    RegimePolicy,
    RegimeStatus,
    assess_market_regime,
)


def _analysis(trend="BULLISH", momentum="POSITIVE", volatility="MODERATE", close=1.1000):
    return {
        "success": True,
        "pair": "EURUSD",
        "interval": "5m",
        "latest_timestamp_utc": "2026-09-10T12:00:00+00:00",
        "classification": {
            "trend": trend,
            "momentum": momentum,
            "volatility": volatility,
        },
        "indicators": {
            "atr": {"value": 0.0011},
            "bollinger_bands": {
                "middle": 1.1000,
                "upper": 1.1020,
                "lower": 1.0980,
            },
            "macd": {"histogram": 0.0002},
        },
        "metadata": {"latest_close": close},
    }


def test_bullish_trend_with_positive_momentum_is_bullish_regime():
    result = assess_market_regime(_analysis())
    assert result.status == RegimeStatus.EVALUATED
    assert result.regime == MarketRegime.BULLISH_TREND
    assert result.momentum_alignment == "ALIGNED_BULLISH"
    assert result.analysis_usable is True


def test_bearish_trend_with_negative_momentum_is_bearish_regime():
    result = assess_market_regime(_analysis("BEARISH", "NEGATIVE"))
    assert result.regime == MarketRegime.BEARISH_TREND
    assert result.momentum_alignment == "ALIGNED_BEARISH"


def test_bullish_negative_momentum_is_transition():
    result = assess_market_regime(_analysis("BULLISH", "NEGATIVE"))
    assert result.regime == MarketRegime.BULLISH_TRANSITION
    assert result.momentum_alignment == "DIVERGENT_BEARISH"


def test_bearish_positive_momentum_is_transition():
    result = assess_market_regime(_analysis("BEARISH", "POSITIVE"))
    assert result.regime == MarketRegime.BEARISH_TRANSITION
    assert result.momentum_alignment == "DIVERGENT_BULLISH"


def test_neutral_low_volatility_is_low_volatility_regime():
    result = assess_market_regime(_analysis("NEUTRAL", "NEUTRAL", "LOW"))
    assert result.regime == MarketRegime.LOW_VOLATILITY


def test_neutral_high_volatility_is_high_volatility_regime():
    result = assess_market_regime(_analysis("NEUTRAL", "NEUTRAL", "HIGH"))
    assert result.regime == MarketRegime.HIGH_VOLATILITY


def test_neutral_moderate_volatility_is_range():
    result = assess_market_regime(_analysis("NEUTRAL", "NEUTRAL", "MODERATE"))
    assert result.regime == MarketRegime.RANGE


def test_mixed_trend_is_mixed_regime():
    result = assess_market_regime(_analysis("MIXED", "NEUTRAL", "MODERATE"))
    assert result.regime == MarketRegime.MIXED
    assert result.trend_strength == "TRANSITIONAL"


def test_bollinger_position_is_deterministic():
    result = assess_market_regime(_analysis(close=1.1016))
    assert round(result.bollinger_position, 6) == 0.9
    assert result.price_location == "UPPER_BAND_REGION"


def test_lower_bollinger_region_is_detected():
    result = assess_market_regime(_analysis(close=1.0984))
    assert round(result.bollinger_position, 6) == 0.1
    assert result.price_location == "LOWER_BAND_REGION"


def test_normalized_atr_is_calculated():
    result = assess_market_regime(_analysis(close=1.1))
    assert round(result.normalized_atr, 6) == round(0.001, 6)


def test_unsuccessful_analysis_is_blocked():
    analysis = _analysis()
    analysis["success"] = False
    result = assess_market_regime(analysis)
    assert result.status == RegimeStatus.BLOCKED
    assert result.regime == MarketRegime.UNKNOWN
    assert result.analysis_usable is False


def test_required_operational_state_blocks_when_missing():
    result = assess_market_regime(
        _analysis(),
        policy=RegimePolicy(require_operational_state=True),
    )
    assert result.status == RegimeStatus.BLOCKED
    assert result.analysis_usable is False


def test_unusable_operational_state_blocks():
    result = assess_market_regime(
        _analysis(),
        operational_state={"status": "UNUSABLE", "analysis_usable": False},
    )
    assert result.status == RegimeStatus.BLOCKED
    assert result.operational_state == "UNUSABLE"


def test_degraded_operational_state_can_be_allowed_by_policy():
    result = assess_market_regime(
        _analysis(),
        operational_state={"status": "DEGRADED", "analysis_usable": False},
        policy=RegimePolicy(
            allow_degraded_operational_state=True,
        ),
    )
    assert result.status == RegimeStatus.EVALUATED
    assert result.analysis_usable is True
    assert result.warnings


def test_missing_regime_dimension_is_insufficient():
    analysis = _analysis()
    analysis["classification"]["momentum"] = "UNKNOWN"
    result = assess_market_regime(analysis)
    assert result.status == RegimeStatus.INSUFFICIENT_DATA
    assert result.analysis_usable is False


def test_engine_uses_its_policy():
    engine = MarketRegimeEngine(
        RegimePolicy(
            bollinger_position_lower=0.10,
            bollinger_position_upper=0.90,
        )
    )
    result = engine.assess(_analysis(close=1.10156))
    assert result.price_location == "MID_BAND_REGION"


def test_invalid_policy_is_rejected():
    try:
        RegimePolicy(bollinger_position_lower=0.9, bollinger_position_upper=0.1)
    except MarketRegimeError:
        pass
    else:
        raise AssertionError("Expected MarketRegimeError")


def test_invalid_analysis_type_is_rejected():
    try:
        assess_market_regime(None)
    except MarketRegimeError:
        pass
    else:
        raise AssertionError("Expected MarketRegimeError")


def test_non_mapping_operational_state_is_rejected():
    try:
        assess_market_regime(_analysis(), operational_state="HEALTHY")
    except MarketRegimeError:
        pass
    else:
        raise AssertionError("Expected MarketRegimeError")


def test_to_dict_is_serializable_and_contains_evidence():
    result = assess_market_regime(_analysis()).to_dict()
    assert result["success"] is True
    assert result["analysis"] == "market_regime"
    assert result["regime"] == MarketRegime.BULLISH_TREND
    assert "trend=BULLISH" in result["evidence"]


def test_engine_matches_function():
    expected = assess_market_regime(_analysis()).to_dict()
    actual = MarketRegimeEngine().assess(_analysis()).to_dict()
    assert actual == expected
