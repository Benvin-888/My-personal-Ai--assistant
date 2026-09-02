"""
APEX / BENVIN Market Data Tests

Phase 2.4 - Market Data Foundation Hardening

This module tests the public market-data foundation.

The tests cover:

    1. Forex pair normalization.
    2. Current quote retrieval.
    3. Historical market-data retrieval.
    4. Invalid Forex pairs.
    5. Invalid historical intervals.
    6. Invalid historical ranges.
    7. Invalid historical limits.
    8. Cache behavior.
    9. Market-data service health.

These tests do NOT:

    - generate trading signals
    - recommend trades
    - execute trades
    - modify trading accounts
    - test trading strategies
"""

from .cache import MarketDataCache
from .provider import normalize_forex_pair
from .service import MarketDataService


# ============================================================
# TEST HELPERS
# ============================================================

PASSED = 0
FAILED = 0


def run_test(name, test_function):
    """
    Run one test and print its result.
    """

    global PASSED
    global FAILED

    try:
        test_function()

        PASSED += 1

        print(f"[PASS] {name}")

    except AssertionError as error:
        FAILED += 1

        print(f"[FAIL] {name}")

        if str(error):
            print(f"       {error}")

    except Exception as error:
        FAILED += 1

        print(f"[ERROR] {name}")
        print(
            f"        {type(error).__name__}: {error}"
        )


# ============================================================
# PAIR NORMALIZATION TESTS
# ============================================================

def test_normalize_standard_pair():
    """
    Standard six-letter Forex pair should remain unchanged.
    """

    result = normalize_forex_pair("EURUSD")

    assert result == "EURUSD"


def test_normalize_lowercase_pair():
    """
    Lowercase Forex pairs should be normalized.
    """

    result = normalize_forex_pair("eurusd")

    assert result == "EURUSD"


def test_normalize_slash_pair():
    """
    Slash-separated Forex pairs should be normalized.
    """

    result = normalize_forex_pair("EUR/USD")

    assert result == "EURUSD"


def test_normalize_dash_pair():
    """
    Dash-separated Forex pairs should be normalized.
    """

    result = normalize_forex_pair("EUR-USD")

    assert result == "EURUSD"


def test_normalize_space_pair():
    """
    Space-separated Forex pairs should be normalized.
    """

    result = normalize_forex_pair("EUR USD")

    assert result == "EURUSD"


def test_invalid_pair():
    """
    Unsupported Forex pair should be rejected.
    """

    result = normalize_forex_pair("ABCXYZ")

    assert result is None


def test_short_pair():
    """
    Pair with an invalid length should be rejected.
    """

    result = normalize_forex_pair("EUR")

    assert result is None


def test_same_currency_pair():
    """
    A pair containing the same base and quote currency
    should be rejected.
    """

    result = normalize_forex_pair("EUREUR")

    assert result is None


# ============================================================
# CURRENT QUOTE TESTS
# ============================================================

def test_current_quote():
    """
    MarketDataService should retrieve a current Forex quote.
    """

    service = MarketDataService()

    result = service.get_forex_quote(
        "EURUSD",
        use_cache=False
    )

    assert isinstance(result, dict)

    assert result.get("success") is True
    assert result.get("market") == "forex"
    assert result.get("pair") == "EURUSD"
    assert result.get("provider") == "Yahoo Finance"

    assert result.get("price") is not None

    candle = result.get("candle")

    assert isinstance(candle, dict)

    assert candle.get("timestamp") is not None
    assert candle.get("timestamp_utc") is not None
    assert candle.get("open") is not None
    assert candle.get("high") is not None
    assert candle.get("low") is not None
    assert candle.get("close") is not None


def test_invalid_quote_pair():
    """
    Invalid quote pair should produce a structured failure.
    """

    service = MarketDataService()

    result = service.get_forex_quote(
        "ABCXYZ",
        use_cache=False
    )

    assert isinstance(result, dict)

    assert result.get("success") is False
    assert result.get("market") == "forex"
    assert result.get("pair") == "ABCXYZ"
    assert "error" in result


# ============================================================
# HISTORICAL DATA TESTS
# ============================================================

def test_historical_data():
    """
    MarketDataService should retrieve validated historical
    Forex candles.
    """

    service = MarketDataService()

    result = service.get_forex_history(
        "EURUSD",
        data_range="1d",
        interval="5m",
        limit=100
    )

    assert isinstance(result, dict)

    assert result.get("success") is True
    assert result.get("market") == "forex"
    assert result.get("pair") == "EURUSD"
    assert result.get("interval") == "5m"

    assert isinstance(
        result.get("candles"),
        list
    )

    assert result.get("candle_count") == len(
        result.get("candles")
    )

    assert result.get("candle_count") <= 100

    assert result.get("invalid_candles") >= 0


def test_invalid_historical_interval():
    """
    Unsupported historical interval should be rejected.
    """

    service = MarketDataService()

    result = service.get_forex_history(
        "EURUSD",
        interval="999m"
    )

    assert isinstance(result, dict)

    assert result.get("success") is False
    assert result.get("pair") == "EURUSD"
    assert "error" in result


def test_invalid_historical_range():
    """
    Unsupported historical range should be rejected.
    """

    service = MarketDataService()

    result = service.get_forex_history(
        "EURUSD",
        data_range="999y"
    )

    assert isinstance(result, dict)

    assert result.get("success") is False
    assert result.get("pair") == "EURUSD"
    assert "error" in result


def test_zero_historical_limit():
    """
    A zero historical limit should be rejected.
    """

    service = MarketDataService()

    result = service.get_forex_history(
        "EURUSD",
        limit=0
    )

    assert isinstance(result, dict)

    assert result.get("success") is False
    assert result.get("pair") == "EURUSD"
    assert "error" in result


def test_negative_historical_limit():
    """
    A negative historical limit should be rejected.
    """

    service = MarketDataService()

    result = service.get_forex_history(
        "EURUSD",
        limit=-10
    )

    assert isinstance(result, dict)

    assert result.get("success") is False
    assert result.get("pair") == "EURUSD"
    assert "error" in result


# ============================================================
# HISTORICAL CHRONOLOGY TEST
# ============================================================

def test_historical_chronology():
    """
    Returned historical candles should be chronological.
    """

    service = MarketDataService()

    result = service.get_forex_history(
        "EURUSD",
        data_range="1d",
        interval="5m",
        limit=100
    )

    assert result.get("success") is True

    candles = result.get("candles")

    timestamps = [
        candle.get("timestamp")
        for candle in candles
    ]

    assert timestamps == sorted(timestamps)

    for index in range(
        1,
        len(timestamps)
    ):
        assert (
            timestamps[index]
            > timestamps[index - 1]
        )


# ============================================================
# HISTORICAL OHLC TEST
# ============================================================

def test_historical_ohlc_relationships():
    """
    Every returned candle should satisfy the basic OHLC
    relationship.
    """

    service = MarketDataService()

    result = service.get_forex_history(
        "EURUSD",
        data_range="1d",
        interval="5m",
        limit=100
    )

    assert result.get("success") is True

    candles = result.get("candles")

    for candle in candles:

        open_price = candle.get("open")
        high = candle.get("high")
        low = candle.get("low")
        close = candle.get("close")

        assert high >= open_price
        assert high >= close
        assert high >= low

        assert low <= open_price
        assert low <= close
        assert low <= high


# ============================================================
# CACHE TESTS
# ============================================================

def test_cache_set_and_get():
    """
    Cache should return a previously stored value.
    """

    cache = MarketDataCache(
        ttl_seconds=60
    )

    value = {
        "success": True,
        "pair": "EURUSD",
        "price": 1.2345
    }

    cache.set(
        "EURUSD",
        value,
        interval="5m",
        data_range="1d"
    )

    result = cache.get(
        "EURUSD",
        interval="5m",
        data_range="1d"
    )

    assert result == value


def test_cache_miss_for_different_interval():
    """
    Different intervals should not return the same cached
    entry.
    """

    cache = MarketDataCache(
        ttl_seconds=60
    )

    value = {
        "success": True,
        "pair": "EURUSD",
        "price": 1.2345
    }

    cache.set(
        "EURUSD",
        value,
        interval="5m",
        data_range="1d"
    )

    result = cache.get(
        "EURUSD",
        interval="15m",
        data_range="1d"
    )

    assert result is None


def test_cache_miss_for_different_range():
    """
    Different ranges should not return the same cached entry.
    """

    cache = MarketDataCache(
        ttl_seconds=60
    )

    value = {
        "success": True,
        "pair": "EURUSD",
        "price": 1.2345
    }

    cache.set(
        "EURUSD",
        value,
        interval="5m",
        data_range="1d"
    )

    result = cache.get(
        "EURUSD",
        interval="5m",
        data_range="5d"
    )

    assert result is None


def test_cache_delete():
    """
    Cache delete should remove a specific entry.
    """

    cache = MarketDataCache(
        ttl_seconds=60
    )

    value = {
        "success": True,
        "pair": "EURUSD",
        "price": 1.2345
    }

    cache.set(
        "EURUSD",
        value,
        interval="5m",
        data_range="1d"
    )

    cache.delete(
        "EURUSD",
        interval="5m",
        data_range="1d"
    )

    result = cache.get(
        "EURUSD",
        interval="5m",
        data_range="1d"
    )

    assert result is None


def test_cache_clear():
    """
    Cache clear should remove stored entries.
    """

    cache = MarketDataCache(
        ttl_seconds=60
    )

    value = {
        "success": True,
        "pair": "EURUSD",
        "price": 1.2345
    }

    cache.set(
        "EURUSD",
        value,
        interval="5m",
        data_range="1d"
    )

    cache.clear()

    result = cache.get(
        "EURUSD",
        interval="5m",
        data_range="1d"
    )

    assert result is None


# ============================================================
# SERVICE HEALTH TEST
# ============================================================

def test_service_health():
    """
    MarketDataService health check should return a structured
    result.
    """

    service = MarketDataService()

    result = service.check_market_data()

    assert isinstance(result, dict)

    assert "success" in result
    assert result.get("provider") == "Yahoo Finance"
    assert result.get("test_pair") == "EURUSD"
    assert "result" in result


# ============================================================
# TEST RUNNER
# ============================================================

def main():
    """
    Run the Phase 2.4 market-data test suite.
    """

    tests = [
        (
            "Normalize standard Forex pair",
            test_normalize_standard_pair
        ),
        (
            "Normalize lowercase Forex pair",
            test_normalize_lowercase_pair
        ),
        (
            "Normalize slash Forex pair",
            test_normalize_slash_pair
        ),
        (
            "Normalize dash Forex pair",
            test_normalize_dash_pair
        ),
        (
            "Normalize space Forex pair",
            test_normalize_space_pair
        ),
        (
            "Reject invalid Forex pair",
            test_invalid_pair
        ),
        (
            "Reject short Forex pair",
            test_short_pair
        ),
        (
            "Reject same-currency pair",
            test_same_currency_pair
        ),
        (
            "Retrieve current Forex quote",
            test_current_quote
        ),
        (
            "Reject invalid quote pair",
            test_invalid_quote_pair
        ),
        (
            "Retrieve historical Forex data",
            test_historical_data
        ),
        (
            "Reject invalid historical interval",
            test_invalid_historical_interval
        ),
        (
            "Reject invalid historical range",
            test_invalid_historical_range
        ),
        (
            "Reject zero historical limit",
            test_zero_historical_limit
        ),
        (
            "Reject negative historical limit",
            test_negative_historical_limit
        ),
        (
            "Validate historical chronology",
            test_historical_chronology
        ),
        (
            "Validate historical OHLC relationships",
            test_historical_ohlc_relationships
        ),
        (
            "Cache set and get",
            test_cache_set_and_get
        ),
        (
            "Cache interval isolation",
            test_cache_miss_for_different_interval
        ),
        (
            "Cache range isolation",
            test_cache_miss_for_different_range
        ),
        (
            "Cache delete",
            test_cache_delete
        ),
        (
            "Cache clear",
            test_cache_clear
        ),
        (
            "Market-data service health",
            test_service_health
        ),
    ]

    print()
    print("=" * 60)
    print("APEX / BENVIN MARKET DATA TEST SUITE")
    print("Phase 2.4 - Foundation Hardening")
    print("=" * 60)
    print()

    for name, test_function in tests:
        run_test(
            name,
            test_function
        )

    print()
    print("=" * 60)
    print(f"PASSED: {PASSED}")
    print(f"FAILED: {FAILED}")
    print("=" * 60)

    if FAILED:
        print()
        print("MARKET DATA TEST SUITE: FAILED")
        return 1

    print()
    print("MARKET DATA TEST SUITE: PASSED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
