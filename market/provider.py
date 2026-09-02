"""
APEX / BENVIN Market Data Providers

Phase 2 - Market Intelligence Foundation

This module provides the external market-data provider
abstraction.

The rest of APEX should communicate with providers through
this interface rather than depending directly on Yahoo Finance.

Current provider:

    Yahoo Finance

Future providers can be added without redesigning the
market-data service.
"""

import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import requests

from .models import Candle


# ============================================================
# CONFIGURATION
# ============================================================

PROVIDER_NAME = "Yahoo Finance"

PROVIDER_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart"
)

REQUEST_TIMEOUT = 20


# ============================================================
# SUPPORTED FOREX CURRENCIES
# ============================================================

SUPPORTED_CURRENCIES = {
    "AUD",
    "CAD",
    "CHF",
    "EUR",
    "GBP",
    "JPY",
    "NZD",
    "USD",
}


# ============================================================
# COMMON FOREX PAIRS
# ============================================================

COMMON_FOREX_PAIRS = {
    "AUDCAD",
    "AUDCHF",
    "AUDJPY",
    "AUDNZD",
    "AUDUSD",

    "CADCHF",
    "CADJPY",

    "CHFJPY",

    "EURAUD",
    "EURCAD",
    "EURCHF",
    "EURGBP",
    "EURJPY",
    "EURNZD",
    "EURUSD",

    "GBPAUD",
    "GBPCAD",
    "GBPCHF",
    "GBPJPY",
    "GBPNZD",
    "GBPUSD",

    "NZDCAD",
    "NZDCHF",
    "NZDJPY",
    "NZDUSD",

    "USDCAD",
    "USDCHF",
    "USDJPY",
}


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_forex_pair(pair):
    """
    Normalize a Forex pair.

    Accepted examples:

        EURUSD
        eurusd
        EUR/USD
        eur/usd
        EUR-USD
        EUR USD

    Returns:

        str | None
    """

    if not isinstance(pair, str):
        return None

    pair = pair.strip().upper()

    if not pair:
        return None

    pair = re.sub(
        r"[^A-Z]",
        "",
        pair
    )

    if len(pair) != 6:
        return None

    base = pair[:3]
    quote = pair[3:]

    if base not in SUPPORTED_CURRENCIES:
        return None

    if quote not in SUPPORTED_CURRENCIES:
        return None

    if base == quote:
        return None

    return pair


# ============================================================
# ABSTRACT PROVIDER
# ============================================================

class MarketDataProvider(ABC):
    """
    Abstract interface for market-data providers.

    APEX depends on this interface rather than on a specific
    provider implementation.
    """

    name = "Unknown Provider"

    @abstractmethod
    def get_forex_quote(
        self,
        pair,
        *,
        data_range="1d",
        interval="5m"
    ):
        """
        Retrieve the latest Forex quote.
        """

        raise NotImplementedError

    @abstractmethod
    def get_forex_history(
        self,
        pair,
        *,
        data_range="1d",
        interval="5m"
    ):
        """
        Retrieve raw historical Forex market data.

        The provider is responsible for communicating with
        the external data source.

        Higher layers are responsible for validating and
        standardizing the returned historical candles.
        """

        raise NotImplementedError


# ============================================================
# YAHOO FINANCE PROVIDER
# ============================================================

class YahooFinanceProvider(MarketDataProvider):
    """
    Yahoo Finance implementation of the market-data provider.
    """

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        timeout=REQUEST_TIMEOUT
    ):
        self.timeout = timeout

        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                )
            }
        )

    # ========================================================
    # PROVIDER SYMBOL
    # ========================================================

    def forex_pair_to_provider_symbol(
        self,
        pair
    ):
        """
        Convert a normalized Forex pair into Yahoo's symbol.

        Example:

            EURUSD
                ↓
            EURUSD=X
        """

        normalized = normalize_forex_pair(
            pair
        )

        if normalized is None:
            return None

        return f"{normalized}=X"

    # ========================================================
    # FETCH RAW DATA
    # ========================================================

    def _fetch_provider_data(
        self,
        provider_symbol,
        *,
        data_range="1d",
        interval="5m"
    ):
        """
        Retrieve raw chart data from Yahoo Finance.
        """

        if not isinstance(
            provider_symbol,
            str
        ):
            raise ValueError(
                "Provider symbol must be a string."
            )

        if not provider_symbol.strip():
            raise ValueError(
                "Provider symbol cannot be empty."
            )

        params = {
            "range": data_range,
            "interval": interval,
        }

        response = self.session.get(
            f"{PROVIDER_URL}/{provider_symbol}",
            params=params,
            timeout=self.timeout
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(
            data,
            dict
        ):
            raise ValueError(
                "Market provider returned invalid JSON."
            )

        chart = data.get(
            "chart"
        )

        if not isinstance(
            chart,
            dict
        ):
            raise ValueError(
                "Market provider response is missing chart data."
            )

        error = chart.get(
            "error"
        )

        if error:
            raise ValueError(
                f"Market provider returned an error: {error}"
            )

        results = chart.get(
            "result"
        )

        if not isinstance(
            results,
            list
        ) or not results:

            raise ValueError(
                "Market provider returned no chart results."
            )

        result = results[0]

        if not isinstance(
            result,
            dict
        ):
            raise ValueError(
                "Market provider returned invalid chart data."
            )

        return result

    # ========================================================
    # TIMESTAMP
    # ========================================================

    @staticmethod
    def _unix_to_iso(timestamp):
        """
        Convert a Unix timestamp into ISO UTC.
        """

        if not isinstance(
            timestamp,
            (int, float)
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

    # ========================================================
    # NUMERIC VALIDATION
    # ========================================================

    @staticmethod
    def _valid_number(value):
        """
        Return True when a value is numeric and usable.
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

    # ========================================================
    # CANDLE EXTRACTION
    # ========================================================

    def _extract_latest_candle(
        self,
        data
    ):
        """
        Extract the latest valid candle from provider data.
        """

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

        if not isinstance(opens, list):
            opens = []

        if not isinstance(highs, list):
            highs = []

        if not isinstance(lows, list):
            lows = []

        if not isinstance(closes, list):
            closes = []

        if not isinstance(volumes, list):
            volumes = []

        latest_index = None

        limit = min(
            len(timestamps),
            len(closes)
        )

        for index in range(
            limit - 1,
            -1,
            -1
        ):

            close = closes[index]

            if self._valid_number(
                close
            ):

                latest_index = index
                break

        if latest_index is None:

            raise ValueError(
                "Market provider returned no valid price."
            )

        timestamp = timestamps[
            latest_index
        ]

        close = closes[
            latest_index
        ]

        open_price = (
            opens[latest_index]
            if latest_index < len(opens)
            else None
        )

        high = (
            highs[latest_index]
            if latest_index < len(highs)
            else None
        )

        low = (
            lows[latest_index]
            if latest_index < len(lows)
            else None
        )

        volume = (
            volumes[latest_index]
            if latest_index < len(volumes)
            else None
        )

        return Candle(
            timestamp=timestamp,
            timestamp_utc=self._unix_to_iso(
                timestamp
            ),
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume
        )

    # ========================================================
    # GET FOREX QUOTE
    # ========================================================

    def get_forex_quote(
        self,
        pair,
        *,
        data_range="1d",
        interval="5m"
    ):
        """
        Retrieve standardized Forex provider data.

        Returns:

            {
                "pair": ...,
                "provider_symbol": ...,
                "provider": ...,
                "candle": ...,
                "meta": ...
            }
        """

        normalized_pair = normalize_forex_pair(
            pair
        )

        if normalized_pair is None:

            raise ValueError(
                "Invalid Forex pair. "
                "Use a six-letter pair such as EURUSD."
            )

        provider_symbol = (
            self.forex_pair_to_provider_symbol(
                normalized_pair
            )
        )

        data = self._fetch_provider_data(
            provider_symbol,
            data_range=data_range,
            interval=interval
        )

        candle = self._extract_latest_candle(
            data
        )

        if not self._valid_number(
            candle.close
        ):

            raise ValueError(
                "Provider returned an invalid price."
            )

        meta = data.get(
            "meta",
            {}
        )

        if not isinstance(
            meta,
            dict
        ):
            meta = {}

        return {
            "pair": normalized_pair,
            "provider_symbol": provider_symbol,
            "provider": self.name,
            "interval": interval,
            "range": data_range,
            "candle": candle,
            "currency": meta.get(
                "currency"
            ),
            "exchange_timezone": meta.get(
                "exchangeTimezoneName"
            ),
            "market_state": meta.get(
                "marketState"
            ),
        }

    # ========================================================
    # GET FOREX HISTORY
    # ========================================================

    def get_forex_history(
        self,
        pair,
        *,
        data_range="1d",
        interval="5m"
    ):
        """
        Retrieve raw historical Forex data.

        This method deliberately does not perform historical
        candle validation.

        It retrieves the provider response and leaves
        historical validation to the historical-data layer.
        """

        normalized_pair = normalize_forex_pair(
            pair
        )

        if normalized_pair is None:

            raise ValueError(
                "Invalid Forex pair. "
                "Use a six-letter pair such as EURUSD."
            )

        provider_symbol = (
            self.forex_pair_to_provider_symbol(
                normalized_pair
            )
        )

        data = self._fetch_provider_data(
            provider_symbol,
            data_range=data_range,
            interval=interval
        )

        meta = data.get(
            "meta",
            {}
        )

        if not isinstance(
            meta,
            dict
        ):
            meta = {}

        return {
            "pair": normalized_pair,
            "provider_symbol": provider_symbol,
            "provider": self.name,
            "interval": interval,
            "range": data_range,
            "data": data,
            "currency": meta.get(
                "currency"
            ),
            "exchange_timezone": meta.get(
                "exchangeTimezoneName"
            ),
            "market_state": meta.get(
                "marketState"
            ),
        }

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(self):
        """
        Check provider connectivity using EURUSD.
        """

        try:

            result = self.get_forex_quote(
                "EURUSD"
            )

            return {
                "success": True,
                "provider": self.name,
                "test_pair": "EURUSD",
                "result": {
                    "price": result["candle"].close,
                    "timestamp_utc": (
                        result["candle"].timestamp_utc
                    ),
                },
            }

        except Exception as error:

            return {
                "success": False,
                "provider": self.name,
                "test_pair": "EURUSD",
                "error": str(error),
            }