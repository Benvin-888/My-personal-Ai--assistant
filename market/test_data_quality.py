import pytest

from market.data_quality import (
    DataQualityError,
    assess_candles,
    assess_market_data,
    assess_ticks,
    compare_prices,
)


def test_good_tick_history_is_high_quality():
    report = assess_ticks({
        "provider": "Deriv",
        "pair": "EURUSD",
        "ticks": [
            {"timestamp": 100, "price": 1.10, "provider_symbol": "frxEURUSD"},
            {"timestamp": 101, "price": 1.11, "provider_symbol": "frxEURUSD"},
        ],
    })
    assert report.success is True
    assert report.quality == "EXCELLENT"
    assert report.score == 100.0


def test_tick_history_detects_invalid_price():
    report = assess_ticks({
        "provider": "Deriv",
        "pair": "EURUSD",
        "ticks": [{"timestamp": 100, "price": 0}],
    })
    assert report.success is False
    assert any(i.code == "NON_POSITIVE_PRICE" for i in report.issues)


def test_tick_history_detects_mixed_symbols():
    report = assess_ticks({
        "provider": "Deriv",
        "pair": "EURUSD",
        "ticks": [
            {"timestamp": 100, "price": 1.1, "provider_symbol": "A"},
            {"timestamp": 101, "price": 1.2, "provider_symbol": "B"},
        ],
    })
    assert report.success is False
    assert any(i.code == "MIXED_PROVIDER_SYMBOLS" for i in report.issues)


def test_tick_history_detects_out_of_order_data():
    report = assess_ticks({
        "provider": "Deriv",
        "pair": "EURUSD",
        "ticks": [
            {"timestamp": 101, "price": 1.1},
            {"timestamp": 100, "price": 1.2},
        ],
    })
    assert report.success is True
    assert any(i.code == "OUT_OF_ORDER" for i in report.issues)


def test_tick_history_detects_duplicate_timestamps():
    report = assess_ticks({
        "provider": "Deriv",
        "pair": "EURUSD",
        "ticks": [
            {"timestamp": 100, "price": 1.1},
            {"timestamp": 100, "price": 1.2},
        ],
    })
    assert any(i.code == "DUPLICATE_TIMESTAMPS" for i in report.issues)


def test_valid_candles_pass():
    report = assess_candles({
        "provider": "Yahoo Finance",
        "pair": "EURUSD",
        "candles": [
            {"timestamp": 100, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15},
            {"timestamp": 200, "open": 1.15, "high": 1.3, "low": 1.1, "close": 1.25},
        ],
    })
    assert report.success is True
    assert report.quality == "EXCELLENT"


def test_invalid_high_is_rejected():
    report = assess_candles({
        "provider": "Yahoo Finance",
        "pair": "EURUSD",
        "candles": [{"timestamp": 100, "open": 1.2, "high": 1.1, "low": 1.0, "close": 1.15}],
    })
    assert report.success is False
    assert any(i.code == "INVALID_HIGH" for i in report.issues)


def test_invalid_low_is_rejected():
    report = assess_candles({
        "provider": "Yahoo Finance",
        "pair": "EURUSD",
        "candles": [{"timestamp": 100, "open": 1.2, "high": 1.3, "low": 1.25, "close": 1.15}],
    })
    assert report.success is False
    assert any(i.code == "INVALID_LOW" for i in report.issues)


def test_candles_must_be_strictly_chronological():
    report = assess_candles({
        "provider": "Yahoo Finance",
        "pair": "EURUSD",
        "candles": [
            {"timestamp": 100, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15},
            {"timestamp": 100, "open": 1.15, "high": 1.3, "low": 1.1, "close": 1.2},
        ],
    })
    assert report.success is False
    assert any(i.code == "NON_CHRONOLOGICAL" for i in report.issues)


def test_dispatch_selects_ticks():
    report = assess_market_data({"provider": "Deriv", "pair": "EURUSD", "ticks": []})
    assert report.data_type == "ticks"


def test_dispatch_selects_candles():
    report = assess_market_data({"provider": "Yahoo", "pair": "EURUSD", "candles": []})
    assert report.data_type == "candles"


def test_dispatch_rejects_unknown_payload():
    with pytest.raises(DataQualityError):
        assess_market_data({"provider": "Deriv"})


def test_price_comparison_within_tolerances():
    result = compare_prices(
        {"provider": "Deriv", "pair": "EURUSD", "timestamp": 100, "price": 1.10000},
        {"provider": "Provider B", "pair": "EURUSD", "timestamp": 101, "price": 1.10050},
        max_timestamp_delta_seconds=2,
        max_relative_difference=0.001,
    )
    assert result.comparable is True
    assert result.within_time_tolerance is True
    assert result.within_price_tolerance is True


def test_price_comparison_reports_timestamp_mismatch():
    result = compare_prices(
        {"provider": "A", "pair": "EURUSD", "timestamp": 100, "price": 1.1},
        {"provider": "B", "pair": "EURUSD", "timestamp": 110, "price": 1.1},
        max_timestamp_delta_seconds=2,
    )
    assert result.comparable is False
    assert result.within_time_tolerance is False


def test_price_comparison_reports_price_mismatch():
    result = compare_prices(
        {"provider": "A", "pair": "EURUSD", "timestamp": 100, "price": 1.1},
        {"provider": "B", "pair": "EURUSD", "timestamp": 100, "price": 1.2},
        max_relative_difference=0.001,
    )
    assert result.comparable is False
    assert result.within_price_tolerance is False


def test_price_comparison_rejects_different_pairs():
    with pytest.raises(DataQualityError):
        compare_prices(
            {"provider": "A", "pair": "EURUSD", "timestamp": 100, "price": 1.1},
            {"provider": "B", "pair": "GBPUSD", "timestamp": 100, "price": 1.2},
        )


def test_price_comparison_rejects_same_provider():
    with pytest.raises(DataQualityError):
        compare_prices(
            {"provider": "A", "pair": "EURUSD", "timestamp": 100, "price": 1.1},
            {"provider": "A", "pair": "EURUSD", "timestamp": 100, "price": 1.2},
        )


def test_empty_history_is_explicit_not_fabricated():
    report = assess_ticks({"provider": "Deriv", "pair": "EURUSD", "ticks": []})
    assert report.observations == 0
    assert report.score == 0.0
    assert report.first_timestamp is None
    assert report.last_timestamp is None
