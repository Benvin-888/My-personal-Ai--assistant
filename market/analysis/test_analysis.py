"""Tests for the APEX technical-analysis foundation."""

import pytest

from market.analysis import TechnicalAnalysisEngine
from market.analysis.momentum import classify_momentum, macd, rsi
from market.analysis.trend import classify_trend, ema, linear_slope, sma
from market.analysis.volatility import (
    atr,
    bollinger_bands,
    classify_volatility,
    true_range,
)


def make_history(count=100, *, trend="up"):
    candles = []
    price = 1.1000

    for i in range(count):
        if trend == "up":
            price += 0.00015 + ((i % 5) * 0.00001)
        elif trend == "down":
            price -= 0.00015 + ((i % 5) * 0.00001)
        else:
            price += 0.00001 if i % 2 == 0 else -0.00001

        candles.append({
            "timestamp": i,
            "timestamp_utc": f"2026-09-01T00:{i % 60:02d}:00Z",
            "open": price - 0.00010,
            "high": price + 0.00020,
            "low": price - 0.00020,
            "close": price,
            "volume": 1000,
        })

    return {
        "success": True,
        "market": "forex",
        "pair": "EURUSD",
        "provider": "TEST",
        "interval": "5m",
        "range": "1d",
        "candles": candles,
        "retrieved_at": "2026-09-01T00:00:00Z",
    }


def test_analysis_produces_structured_result():
    result = TechnicalAnalysisEngine().analyze_history(make_history())

    assert result["success"] is True
    assert result["pair"] == "EURUSD"
    assert result["candle_count"] == 100

    assert result["indicators"]["sma"]["valid"] is True
    assert result["indicators"]["ema_fast"]["valid"] is True
    assert result["indicators"]["ema_slow"]["valid"] is True
    assert result["indicators"]["rsi"]["valid"] is True
    assert result["indicators"]["macd"]["valid"] is True
    assert result["indicators"]["atr"]["valid"] is True
    assert result["indicators"]["bollinger_bands"]["valid"] is True

    assert result["metadata"]["calculation"] == "deterministic_python"


def test_analysis_rejects_failed_history():
    result = TechnicalAnalysisEngine().analyze_history({"success": False})

    assert result["success"] is False
    assert "unsuccessful" in result["error"].lower()


def test_analysis_requires_enough_data_for_slow_ema():
    history = make_history(20)

    result = TechnicalAnalysisEngine().analyze_history(history)

    assert result["success"] is True
    assert result["indicators"]["ema_slow"]["valid"] is False
    assert result["classification"]["trend"] == "INSUFFICIENT_DATA"


def test_sma_exact_values():
    result = sma([1.0, 2.0, 3.0, 4.0, 5.0], 3)

    assert result == [None, None, 2.0, 3.0, 4.0]


def test_ema_uses_sma_seed():
    result = ema([1.0, 2.0, 3.0, 4.0], 3)

    assert result[0] is None
    assert result[1] is None
    assert result[2] == pytest.approx(2.0)
    assert result[3] == pytest.approx(3.0)


def test_rsi_uptrend_reaches_100():
    result = rsi([1, 2, 3, 4, 5, 6], 3)

    assert result[3] == pytest.approx(100.0)
    assert result[-1] == pytest.approx(100.0)


def test_rsi_downtrend_reaches_zero():
    result = rsi([6, 5, 4, 3, 2, 1], 3)

    assert result[3] == pytest.approx(0.0)
    assert result[-1] == pytest.approx(0.0)


def test_macd_warmup_and_histogram():
    closes = [float(i) for i in range(1, 50)]

    line, signal, histogram = macd(
        closes,
        fast_period=3,
        slow_period=5,
        signal_period=2,
    )

    assert all(value is None for value in line[:4])
    assert line[4] is not None
    assert signal[4] is None
    assert signal[5] is not None
    assert histogram[5] is not None


def test_true_range_uses_previous_close():
    candles = [
        {"high": 10, "low": 8, "close": 9},
        {"high": 12, "low": 11, "close": 11.5},
        {"high": 13, "low": 10, "close": 12},
    ]

    result = true_range(candles)

    assert result == [2.0, 3.0, 3.0]


def test_atr_uses_wilder_smoothing():
    candles = [
        {"high": 10, "low": 8, "close": 9},
        {"high": 12, "low": 11, "close": 11.5},
        {"high": 13, "low": 10, "close": 12},
        {"high": 14, "low": 12, "close": 13},
    ]

    result = atr(candles, 3)

    assert result[2] == pytest.approx((2 + 3 + 3) / 3)
    assert result[3] == pytest.approx(
        (((2 + 3 + 3) / 3) * 2 + 2) / 3
    )


def test_bollinger_bands_exact_constant_window():
    middle, upper, lower = bollinger_bands(
        [10, 10, 10, 10],
        period=3,
        stddevs=2,
    )

    assert middle[2] == pytest.approx(10)
    assert upper[2] == pytest.approx(10)
    assert lower[2] == pytest.approx(10)


def test_classifications_are_centralized_and_deterministic():
    closes = [1, 2, 3, 4, 5]
    fast = [None, None, 2, 3, 4]
    slow = [None, None, 1.5, 2.5, 3.5]

    assert classify_trend(closes, fast, slow) == "BULLISH"
    assert classify_momentum(70, 0.01) == "POSITIVE"
    assert classify_momentum(30, -0.01) == "NEGATIVE"
    assert classify_momentum(50, 0.01) == "NEUTRAL"


def test_trend_detects_conflicting_fast_ema_slope():
    closes = [10, 11, 12, 13, 14]
    fast = [9, 10, 11, 10, 9]
    slow = [8, 8.5, 9, 9.5, 8]

    assert classify_trend(
        closes,
        fast,
        slow,
        slope_lookback=3,
    ) == "MIXED"


def test_linear_slope():
    assert linear_slope([1, 2, 3, 4, 5], 5) == pytest.approx(1.0)
    assert linear_slope([5, 4, 3, 2, 1], 5) == pytest.approx(-1.0)


def test_invalid_parameters_are_rejected():
    engine = TechnicalAnalysisEngine()
    history = make_history()

    assert engine.analyze_history(
        history,
        ema_fast_period=0,
    )["success"] is False

    assert engine.analyze_history(
        history,
        macd_fast=26,
        macd_slow=12,
    )["success"] is False

    assert engine.analyze_history(
        history,
        bollinger_stddevs=float("inf"),
    )["success"] is False

    assert engine.analyze_history(
        history,
        trend_slope_lookback=1,
    )["success"] is False


def test_invalid_ohlc_is_rejected():
    history = make_history()
    history["candles"][10]["close"] = float("nan")

    result = TechnicalAnalysisEngine().analyze_history(history)

    assert result["success"] is False
    assert "invalid OHLC" in result["error"]


def test_dictionary_and_object_candles_are_supported():
    class Candle:
        high = 1.2
        low = 1.0
        close = 1.1
        timestamp_utc = "2026-09-01T00:00:00Z"

    candles = [Candle() for _ in range(60)]

    history = make_history(60)
    history["candles"] = candles

    result = TechnicalAnalysisEngine().analyze_history(history)

    assert result["success"] is True


def test_insufficient_indicators_do_not_create_fake_values():
    result = TechnicalAnalysisEngine().analyze_history(
        make_history(10)
    )

    assert result["success"] is True
    assert result["indicators"]["ema_slow"]["value"] is None
    assert result["indicators"]["rsi"]["value"] is None
    assert result["classification"]["momentum"] == "INSUFFICIENT_DATA"
    assert result["classification"]["volatility"] == "INSUFFICIENT_DATA"
