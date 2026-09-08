"""Tests for Phase 2.6.3 deterministic tick -> OHLC aggregation."""

from market.tick_ohlc import (
    SUPPORTED_TICK_OHLC_INTERVALS,
    TickOHLCBuilder,
    aggregate_ticks_to_ohlc,
)
from market.ticks import ForexTickHistory, HistoricalTick


def make_history(ticks):
    return ForexTickHistory(
        pair="EURUSD",
        base_currency="EUR",
        quote_currency="USD",
        provider_symbol="frxEURUSD",
        provider="Deriv",
        ticks=tuple(ticks),
        requested_count=len(ticks),
        retrieved_at="2026-09-08T00:00:00Z",
    )


def tick(timestamp, price):
    return HistoricalTick(
        timestamp=timestamp,
        timestamp_utc="ignored",
        price=price,
        provider="Deriv",
        provider_symbol="frxEURUSD",
        raw_tick={"epoch": timestamp, "price": price},
    )


def test_one_minute_ohlc_uses_first_extrema_and_last_tick():
    history = make_history([
        tick(1700000041, 1.1000),
        tick(1700000050, 1.1010),
        tick(1700000055, 1.0990),
        tick(1700000059, 1.1005),
    ])

    result = aggregate_ticks_to_ohlc(history, interval="1m")
    candle = result["candles"][0]

    assert result["success"] is True
    assert result["candle_count"] == 1
    assert candle["timestamp"] == 1700000040
    assert candle["open"] == 1.1000
    assert candle["high"] == 1.1010
    assert candle["low"] == 1.0990
    assert candle["close"] == 1.1005
    assert candle["volume"] is None


def test_ticks_are_sorted_before_open_and_close_are_selected():
    history = make_history([
        tick(1700000100, 1.2000),
        tick(1700000045, 1.1000),
        tick(1700000050, 1.1500),
    ])

    result = aggregate_ticks_to_ohlc(history, interval="1m")
    candle = result["candles"][0]

    assert candle["open"] == 1.1000
    assert candle["high"] == 1.1500
    assert candle["low"] == 1.1000
    assert candle["close"] == 1.1500


def test_empty_intervals_are_not_fabricated():
    history = make_history([
        tick(1700000041, 1.10),
        tick(1700000160, 1.20),
    ])

    result = aggregate_ticks_to_ohlc(history, interval="1m")

    assert result["candle_count"] == 2
    assert [c["timestamp"] for c in result["candles"]] == [1700000040, 1700000160]


def test_equal_timestamp_ticks_preserve_input_order_for_close():
    history = make_history([
        tick(1700000041, 1.10),
        tick(1700000041, 1.20),
        tick(1700000041, 1.15),
    ])

    result = aggregate_ticks_to_ohlc(history, interval="1m")
    candle = result["candles"][0]

    assert candle["open"] == 1.10
    assert candle["high"] == 1.20
    assert candle["low"] == 1.10
    assert candle["close"] == 1.15


def test_daily_boundary_is_utc_not_local_time():
    history = make_history([
        tick(1704067199, 1.10),  # 2023-12-31 23:59:59 UTC
        tick(1704067200, 1.20),  # 2024-01-01 00:00:00 UTC
    ])

    result = aggregate_ticks_to_ohlc(history, interval="1d")

    assert result["candle_count"] == 2
    assert result["candles"][0]["timestamp"] == 1703980800
    assert result["candles"][1]["timestamp"] == 1704067200


def test_no_future_tick_can_change_an_earlier_candle():
    history = make_history([
        tick(1700000041, 1.10),
        tick(1700000059, 1.11),
        tick(1700000100, 1.50),
    ])

    result = aggregate_ticks_to_ohlc(history, interval="1m")

    first = result["candles"][0]
    second = result["candles"][1]

    assert first["high"] == 1.11
    assert first["close"] == 1.11
    assert second["open"] == 1.50


def test_raw_mapping_input_is_supported():
    result = aggregate_ticks_to_ohlc(
        {
            "pair": "eur/usd",
            "provider": "Deriv",
            "provider_symbol": "frxEURUSD",
            "ticks": [
                {"timestamp": 1700000041, "price": 1.10, "provider": "Deriv", "provider_symbol": "frxEURUSD"},
                {"timestamp": 1700000050, "price": 1.12, "provider": "Deriv", "provider_symbol": "frxEURUSD"},
            ],
        },
        interval="1m",
    )

    assert result["pair"] == "EURUSD"
    assert result["candles"][0]["open"] == 1.10
    assert result["candles"][0]["close"] == 1.12


def test_empty_history_is_valid_and_contains_no_synthetic_candles():
    result = aggregate_ticks_to_ohlc(make_history([]), interval="5m")

    assert result["success"] is True
    assert result["candle_count"] == 0
    assert result["candles"] == []


def test_invalid_interval_is_rejected():
    history = make_history([tick(1700000041, 1.10)])

    try:
        aggregate_ticks_to_ohlc(history, interval="3m")
    except ValueError as exc:
        assert "Unsupported tick OHLC interval" in str(exc)
    else:
        raise AssertionError("Expected invalid interval to be rejected.")


def test_invalid_pair_is_rejected():
    history = ForexTickHistory(
        pair="EUR",
        base_currency="EU",
        quote_currency="R",
        provider_symbol="frxEURUSD",
        provider="Deriv",
        ticks=(tick(1700000041, 1.10),),
    )

    try:
        aggregate_ticks_to_ohlc(history, interval="1m")
    except ValueError as exc:
        assert "Invalid Forex pair" in str(exc)
    else:
        raise AssertionError("Expected invalid pair to be rejected.")


def test_invalid_price_is_rejected():
    history = make_history([tick(1700000041, 0)])

    try:
        aggregate_ticks_to_ohlc(history, interval="1m")
    except ValueError as exc:
        assert "positive finite number" in str(exc)
    else:
        raise AssertionError("Expected invalid price to be rejected.")


def test_mixed_provider_symbols_are_rejected():
    history = make_history([
        tick(1700000041, 1.10),
        HistoricalTick(1700000042, "ignored", 1.11, "Deriv", "frxGBPUSD", {}),
    ])

    try:
        aggregate_ticks_to_ohlc(history, interval="1m")
    except ValueError as exc:
        assert "same provider symbol" in str(exc)
    else:
        raise AssertionError("Expected mixed provider symbols to be rejected.")


def test_supported_intervals_are_positive():
    assert SUPPORTED_TICK_OHLC_INTERVALS
    assert all(seconds > 0 for seconds in SUPPORTED_TICK_OHLC_INTERVALS.values())


def test_builder_facade_matches_function():
    history = make_history([tick(1700000041, 1.10)])

    direct = aggregate_ticks_to_ohlc(history, interval="5m")
    via_builder = TickOHLCBuilder().aggregate(history, interval="5m")

    assert direct["candles"] == via_builder["candles"]
    assert direct["pair"] == via_builder["pair"]
