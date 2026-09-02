"""
APEX / BENVIN Historical Forex Market Data Engine

Phase 2.2 - Historical Market Data Foundation

Responsibilities:

    1. Retrieve historical Forex candles.
    2. Validate currency pairs.
    3. Validate supported chart intervals.
    4. Retrieve historical OHLC data from the provider.
    5. Convert provider timestamps into UTC ISO timestamps.
    6. Validate candle structure and OHLC relationships.
    7. Preserve provider/source information.
    8. Return clean chronological market data.

IMPORTANT:

    This module ONLY retrieves and validates historical
    market data.

    It does NOT:
        - place trades
        - modify trading accounts
        - generate trading signals
        - recommend entries
        - recommend exits
        - calculate position sizes
        - execute strategies
        - make trading decisions
"""

import json
from datetime import datetime, timezone

import requests

from .models import MarketDataError
from .provider import (
    MarketDataProvider,
    YahooFinanceProvider,
    normalize_forex_pair,
)


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_RANGE = "1d"

DEFAULT_INTERVAL = "5m"

DEFAULT_LIMIT = 500


# ============================================================
# SUPPORTED INTERVALS
# ============================================================

SUPPORTED_INTERVALS = {
    "1m",
    "2m",
    "5m",
    "15m",
    "30m",
    "60m",
    "90m",
    "1h",
    "1d",
    "5d",
    "1wk",
    "1mo",
    "3mo",
}


# ============================================================
# SUPPORTED RANGES
# ============================================================

SUPPORTED_RANGES = {
    "1d",
    "5d",
    "1mo",
    "3mo",
    "6mo",
    "1y",
    "2y",
    "5y",
    "10y",
    "ytd",
    "max",
}


# ============================================================
# NUMERIC VALIDATION
# ============================================================

def _valid_number(value):
    """
    Return True when a value is a usable numeric value.
    """

    return (
        isinstance(
            value,
            (int, float)
        )
        and not isinstance(
            value,
            bool
        )
    )


# ============================================================
# UTC TIME
# ============================================================

def _utc_now():
    """
    Return the current UTC timestamp.
    """

    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
        .replace(
            "+00:00",
            "Z"
        )
    )


# ============================================================
# TIMESTAMP
# ============================================================

def _unix_to_iso(timestamp):
    """
    Convert a Unix timestamp into an ISO UTC timestamp.

    Returns:

        str | None
    """

    if not _valid_number(
        timestamp
    ):
        return None

    try:

        return (
            datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z"
            )
        )

    except (
        OverflowError,
        OSError,
        ValueError
    ):

        return None


# ============================================================
# INTERVAL VALIDATION
# ============================================================

def is_supported_interval(interval):
    """
    Check whether an interval is supported.
    """

    if not isinstance(
        interval,
        str
    ):
        return False

    return (
        interval.strip().lower()
        in SUPPORTED_INTERVALS
    )


# ============================================================
# RANGE VALIDATION
# ============================================================

def is_supported_range(data_range):
    """
    Check whether a provider chart range is supported.
    """

    if not isinstance(
        data_range,
        str
    ):
        return False

    return (
        data_range.strip().lower()
        in SUPPORTED_RANGES
    )


# ============================================================
# CANDLE VALIDATION
# ============================================================

def _validate_candle(candle):
    """
    Validate the structure and basic OHLC relationships
    of a single candle.

    A valid candle must contain:

        timestamp
        timestamp_utc
        open
        high
        low
        close

    Volume is optional.
    """

    if not isinstance(
        candle,
        dict
    ):
        return False, "Candle must be a dictionary."

    timestamp = candle.get(
        "timestamp"
    )

    timestamp_utc = candle.get(
        "timestamp_utc"
    )

    open_price = candle.get(
        "open"
    )

    high = candle.get(
        "high"
    )

    low = candle.get(
        "low"
    )

    close = candle.get(
        "close"
    )

    if not _valid_number(
        timestamp
    ):
        return False, (
            "Candle timestamp is invalid."
        )

    if not timestamp_utc:
        return False, (
            "Candle UTC timestamp is missing."
        )

    required_prices = {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }

    for name, value in required_prices.items():

        if not _valid_number(
            value
        ):
            return False, (
                f"Candle {name} price is invalid."
            )

    if high < open_price:

        return False, (
            "Candle high is lower than candle open."
        )

    if high < close:

        return False, (
            "Candle high is lower than candle close."
        )

    if high < low:

        return False, (
            "Candle high is lower than candle low."
        )

    if low > open_price:

        return False, (
            "Candle low is higher than candle open."
        )

    if low > close:

        return False, (
            "Candle low is higher than candle close."
        )

    return True, None


# ============================================================
# EXTRACT HISTORICAL CANDLES
# ============================================================

def _extract_historical_candles(data):
    """
    Extract all usable OHLC candles from provider data.

    Invalid candles are skipped.

    Returns:

        {
            "candles": [...],
            "invalid_candles": int,
            "total_provider_rows": int
        }
    """

    if not isinstance(
        data,
        dict
    ):
        raise ValueError(
            "Market provider returned invalid chart data."
        )

    timestamps = data.get(
        "timestamp"
    )

    indicators = data.get(
        "indicators"
    )

    if not isinstance(
        timestamps,
        list
    ):
        raise ValueError(
            "Market data does not contain timestamps."
        )

    if not isinstance(
        indicators,
        dict
    ):
        raise ValueError(
            "Market data does not contain indicators."
        )

    quotes = indicators.get(
        "quote"
    )

    if not isinstance(
        quotes,
        list
    ) or not quotes:

        raise ValueError(
            "Market data does not contain quote data."
        )

    quote = quotes[0]

    if not isinstance(
        quote,
        dict
    ):
        raise ValueError(
            "Market provider returned invalid quote data."
        )

    opens = quote.get(
        "open",
        []
    )

    highs = quote.get(
        "high",
        []
    )

    lows = quote.get(
        "low",
        []
    )

    closes = quote.get(
        "close",
        []
    )

    volumes = quote.get(
        "volume",
        []
    )

    if not isinstance(
        opens,
        list
    ):
        opens = []

    if not isinstance(
        highs,
        list
    ):
        highs = []

    if not isinstance(
        lows,
        list
    ):
        lows = []

    if not isinstance(
        closes,
        list
    ):
        closes = []

    if not isinstance(
        volumes,
        list
    ):
        volumes = []

    total_rows = len(
        timestamps
    )

    candles = []

    invalid_candles = 0

    for index, timestamp in enumerate(
        timestamps
    ):

        candle = {
            "timestamp": timestamp,

            "timestamp_utc": (
                _unix_to_iso(
                    timestamp
                )
            ),

            "open": (
                opens[index]
                if index < len(opens)
                else None
            ),

            "high": (
                highs[index]
                if index < len(highs)
                else None
            ),

            "low": (
                lows[index]
                if index < len(lows)
                else None
            ),

            "close": (
                closes[index]
                if index < len(closes)
                else None
            ),

            "volume": (
                volumes[index]
                if index < len(volumes)
                else None
            ),
        }

        valid, _ = _validate_candle(
            candle
        )

        if not valid:

            invalid_candles += 1

            continue

        candles.append(
            candle
        )

    return {
        "candles": candles,
        "invalid_candles": invalid_candles,
        "total_provider_rows": total_rows,
    }


# ============================================================
# CHRONOLOGICAL VALIDATION
# ============================================================

def _sort_and_validate_chronology(
    candles
):
    """
    Sort candles chronologically and verify timestamps
    are strictly increasing.
    """

    if not candles:
        return []

    candles = sorted(
        candles,
        key=lambda candle: candle["timestamp"]
    )

    previous_timestamp = None

    for candle in candles:

        timestamp = candle[
            "timestamp"
        ]

        if previous_timestamp is not None:

            if timestamp <= previous_timestamp:

                raise ValueError(
                    "Historical candles contain duplicate "
                    "or non-increasing timestamps."
                )

        previous_timestamp = timestamp

    return candles


# ============================================================
# CANDLE LIMIT
# ============================================================

def _apply_limit(
    candles,
    limit
):
    """
    Apply an optional candle limit.

    The newest candles are returned.

    Chronological order is preserved.
    """

    if limit is None:
        return candles

    if not isinstance(
        limit,
        int
    ) or isinstance(
        limit,
        bool
    ):

        raise ValueError(
            "limit must be an integer or None."
        )

    if limit <= 0:

        raise ValueError(
            "limit must be greater than zero."
        )

    if len(candles) <= limit:

        return candles

    return candles[-limit:]


# ============================================================
# HISTORICAL MARKET DATA ENGINE
# ============================================================

class HistoricalMarketData:
    """
    Historical Forex market-data engine.

    This layer sits above the provider abstraction and is
    responsible for validating and standardizing historical
    market data.
    """

    def __init__(
        self,
        provider: MarketDataProvider | None = None
    ):
        self.provider = (
            provider
            if provider is not None
            else YahooFinanceProvider()
        )

    # ========================================================
    # GET FOREX HISTORY
    # ========================================================

    def get_forex_history(
        self,
        pair,
        *,
        data_range=DEFAULT_RANGE,
        interval=DEFAULT_INTERVAL,
        limit=DEFAULT_LIMIT
    ):
        """
        Retrieve validated historical Forex candles.
        """

        normalized_pair = normalize_forex_pair(
            pair
        )

        if normalized_pair is None:

            return MarketDataError(
                market="forex",
                pair=(
                    str(pair)
                    if pair is not None
                    else None
                ),
                error=(
                    "Invalid Forex pair. "
                    "Use a six-letter pair such as EURUSD."
                )
            ).to_dict()

        normalized_interval = (
            interval.strip().lower()
            if isinstance(
                interval,
                str
            )
            else interval
        )

        normalized_range = (
            data_range.strip().lower()
            if isinstance(
                data_range,
                str
            )
            else data_range
        )

        if not is_supported_interval(
            normalized_interval
        ):

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                error=(
                    f"Unsupported interval: {interval}. "
                    "Use a supported Yahoo Finance interval."
                )
            ).to_dict()

        if not is_supported_range(
            normalized_range
        ):

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                error=(
                    f"Unsupported range: {data_range}. "
                    "Use a supported Yahoo Finance range."
                )
            ).to_dict()

        if limit is not None:

            if not isinstance(
                limit,
                int
            ) or isinstance(
                limit,
                bool
            ):

                return MarketDataError(
                    market="forex",
                    pair=normalized_pair,
                    error=(
                        "limit must be an integer or None."
                    )
                ).to_dict()

            if limit <= 0:

                return MarketDataError(
                    market="forex",
                    pair=normalized_pair,
                    error=(
                        "limit must be greater than zero."
                    )
                ).to_dict()

        try:

            provider_result = (
                self.provider.get_forex_history(
                    normalized_pair,
                    data_range=normalized_range,
                    interval=normalized_interval
                )
            )

            raw_data = provider_result.get(
                "data"
            )

            extracted = (
                _extract_historical_candles(
                    raw_data
                )
            )

            candles = extracted[
                "candles"
            ]

            if not candles:

                return MarketDataError(
                    market="forex",
                    pair=normalized_pair,
                    provider=self.provider.name,
                    error=(
                        "Market provider returned no valid "
                        "historical candles."
                    ),
                    details={
                        "provider_symbol": (
                            provider_result.get(
                                "provider_symbol"
                            )
                        ),
                        "interval": normalized_interval,
                        "range": normalized_range,
                        "total_provider_rows": (
                            extracted[
                                "total_provider_rows"
                            ]
                        ),
                        "invalid_candles": (
                            extracted[
                                "invalid_candles"
                            ]
                        ),
                    }
                ).to_dict()

            candles = (
                _sort_and_validate_chronology(
                    candles
                )
            )

            candles = _apply_limit(
                candles,
                limit
            )

            meta = raw_data.get(
                "meta",
                {}
            )

            if not isinstance(
                meta,
                dict
            ):
                meta = {}

            first_candle = candles[0]

            latest_candle = candles[-1]

            return {
                "success": True,
                "market": "forex",
                "pair": normalized_pair,
                "base_currency": normalized_pair[:3],
                "quote_currency": normalized_pair[3:],
                "provider_symbol": (
                    provider_result[
                        "provider_symbol"
                    ]
                ),
                "provider": (
                    provider_result[
                        "provider"
                    ]
                ),
                "interval": normalized_interval,
                "range": normalized_range,
                "currency": (
                    provider_result.get(
                        "currency"
                    )
                ),
                "exchange_timezone": (
                    provider_result.get(
                        "exchange_timezone"
                    )
                ),
                "market_state": (
                    provider_result.get(
                        "market_state"
                    )
                ),
                "candle_count": len(
                    candles
                ),
                "total_provider_rows": (
                    extracted[
                        "total_provider_rows"
                    ]
                ),
                "invalid_candles": (
                    extracted[
                        "invalid_candles"
                    ]
                ),
                "first_candle_timestamp": (
                    first_candle[
                        "timestamp_utc"
                    ]
                ),
                "latest_candle_timestamp": (
                    latest_candle[
                        "timestamp_utc"
                    ]
                ),
                "candles": candles,
                "retrieved_at": _utc_now(),
            }

        except requests.Timeout:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=(
                    "The market-data provider timed out."
                )
            ).to_dict()

        except requests.ConnectionError:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=(
                    "Could not connect to the "
                    "market-data provider."
                )
            ).to_dict()

        except requests.HTTPError as error:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=(
                    f"Market provider HTTP error: {error}"
                )
            ).to_dict()

        except requests.RequestException as error:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=(
                    f"Market provider request failed: {error}"
                )
            ).to_dict()

        except ValueError as error:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=str(error)
            ).to_dict()

        except Exception as error:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=(
                    "Unexpected historical market-data "
                    f"error: {error}"
                )
            ).to_dict()

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def check_market_history(self):
        """
        Test historical market-data retrieval.

        EURUSD 5-minute candles are used only as a
        connectivity and data-integrity test.
        """

        result = self.get_forex_history(
            "EURUSD",
            data_range="1d",
            interval="5m",
            limit=100
        )

        return {
            "success": bool(
                result.get(
                    "success",
                    False
                )
            ),
            "provider": self.provider.name,
            "test_pair": "EURUSD",
            "interval": "5m",
            "result": result,
        }


# ============================================================
# PUBLIC API
# ============================================================

_history_service = HistoricalMarketData()


def get_forex_history(
    pair,
    *,
    data_range=DEFAULT_RANGE,
    interval=DEFAULT_INTERVAL,
    limit=DEFAULT_LIMIT
):
    """
    Public historical Forex data API.

    Example:

        get_forex_history(
            "EURUSD",
            data_range="1d",
            interval="5m",
            limit=100
        )
    """

    return _history_service.get_forex_history(
        pair,
        data_range=data_range,
        interval=interval,
        limit=limit
    )


def check_market_history():
    """
    Public historical market-data health check.
    """

    return _history_service.check_market_history()


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print(
        "APEX / BENVIN HISTORICAL FOREX DATA TEST"
    )
    print("=" * 60)

    print()

    print("Provider:")
    print(
        _history_service.provider.name
    )

    print()

    print(
        "Testing EURUSD historical candles:"
    )

    result = get_forex_history(
        "EURUSD",
        data_range="1d",
        interval="5m",
        limit=100
    )

    print()

    if result.get("success"):

        print("Success:")
        print(
            result["success"]
        )

        print()

        print("Pair:")
        print(
            result["pair"]
        )

        print()

        print("Interval:")
        print(
            result["interval"]
        )

        print()

        print("Range:")
        print(
            result["range"]
        )

        print()

        print("Candles returned:")
        print(
            result["candle_count"]
        )

        print()

        print("Provider rows:")
        print(
            result["total_provider_rows"]
        )

        print()

        print("Invalid candles:")
        print(
            result["invalid_candles"]
        )

        print()

        print("First candle:")
        print(
            json.dumps(
                result["candles"][0],
                indent=2,
                ensure_ascii=False
            )
        )

        print()

        print("Latest candle:")
        print(
            json.dumps(
                result["candles"][-1],
                indent=2,
                ensure_ascii=False
            )
        )

    else:

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False
            )
        )

    print()

    print("=" * 60)
    print(
        "HISTORICAL MARKET DATA TEST COMPLETE"
    )
    print("=" * 60)