"""
APEX / BENVIN OANDA Market Data Provider

Phase 2.6.1 - OANDA Provider Foundation

This module provides a read-only OANDA REST v20 market-data
provider.

It intentionally does NOT:
    - place orders
    - modify trades
    - close positions
    - modify accounts
    - execute strategies

Credentials are read from environment variables:

    OANDA_API_TOKEN
    OANDA_ACCOUNT_ID
    OANDA_ENVIRONMENT=practice|live

Practice is the default environment.
"""

import os
from datetime import datetime, timedelta, timezone

import requests

from .models import Candle
from .provider import (
    MarketDataProvider,
    normalize_forex_pair,
)


PROVIDER_NAME = "OANDA"
REQUEST_TIMEOUT = 20
DEFAULT_ENVIRONMENT = "practice"

BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

# APEX/Yahoo-style intervals -> OANDA granularity.
INTERVAL_MAP = {
    "1m": "M1",
    "2m": "M2",
    "5m": "M5",
    "15m": "M15",
    "30m": "M30",
    "60m": "H1",
    "1h": "H1",
    "2h": "H2",
    "4h": "H4",
    "1d": "D",
    "1wk": "W",
    "1mo": "M",
}

# Approximate range windows used only to translate the existing
# APEX range abstraction into OANDA's from/to API parameters.
RANGE_DAYS = {
    "1d": 1,
    "5d": 5,
    "1mo": 31,
    "3mo": 93,
    "6mo": 186,
    "1y": 365,
    "2y": 730,
    "5y": 1825,
    "10y": 3650,
}


class OANDAConfigurationError(RuntimeError):
    """Raised when OANDA credentials/configuration are incomplete."""


class OANDAProvider(MarketDataProvider):
    """Read-only OANDA REST v20 provider."""

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        api_token=None,
        account_id=None,
        environment=None,
        timeout=REQUEST_TIMEOUT,
        session=None,
    ):
        self.api_token = (
            api_token
            if api_token is not None
            else os.getenv("OANDA_API_TOKEN")
        )
        self.account_id = (
            account_id
            if account_id is not None
            else os.getenv("OANDA_ACCOUNT_ID")
        )
        self.environment = (
            environment
            if environment is not None
            else os.getenv(
                "OANDA_ENVIRONMENT",
                DEFAULT_ENVIRONMENT,
            )
        ).strip().lower()

        if self.environment not in BASE_URLS:
            raise OANDAConfigurationError(
                "OANDA_ENVIRONMENT must be 'practice' or 'live'."
            )

        self.timeout = timeout
        self.base_url = BASE_URLS[self.environment]
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_token or ''}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "APEX-BENVIN/2.6.1",
            }
        )

    @staticmethod
    def forex_pair_to_provider_symbol(pair):
        normalized = normalize_forex_pair(pair)
        if normalized is None:
            return None
        return f"{normalized[:3]}_{normalized[3:]}"

    @staticmethod
    def interval_to_granularity(interval):
        if not isinstance(interval, str):
            return None
        return INTERVAL_MAP.get(interval.strip().lower())

    def _require_configuration(self):
        if not self.api_token:
            raise OANDAConfigurationError(
                "OANDA_API_TOKEN is not configured."
            )
        if not self.account_id:
            raise OANDAConfigurationError(
                "OANDA_ACCOUNT_ID is not configured."
            )

    @staticmethod
    def _iso_to_unix(value):
        if not isinstance(value, str):
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _iso_now():
        return (
            datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _number(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _get(self, path, *, params=None):
        self._require_configuration()
        response = self.session.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("OANDA returned invalid JSON.")
        return data

    def _price(self, pair):
        symbol = self.forex_pair_to_provider_symbol(pair)
        data = self._get(
            f"/v3/accounts/{self.account_id}/pricing",
            params={"instruments": symbol},
        )

        prices = data.get("prices")
        if not isinstance(prices, list) or not prices:
            raise ValueError("OANDA returned no pricing data.")

        price = prices[0]
        if not isinstance(price, dict):
            raise ValueError("OANDA returned invalid pricing data.")

        bids = price.get("bids") or []
        asks = price.get("asks") or []
        bid = self._number(bids[0].get("price")) if bids else None
        ask = self._number(asks[0].get("price")) if asks else None

        if bid is None or ask is None:
            raise ValueError("OANDA pricing response lacks bid/ask prices.")

        mid = (bid + ask) / 2.0
        timestamp = price.get("time")
        unix_timestamp = self._iso_to_unix(timestamp)

        candle = Candle(
            timestamp=unix_timestamp,
            timestamp_utc=timestamp,
            open=mid,
            high=mid,
            low=mid,
            close=mid,
            volume=None,
        )

        return {
            "pair": normalize_forex_pair(pair),
            "provider_symbol": symbol,
            "provider": self.name,
            "interval": "tick",
            "range": "current",
            "candle": candle,
            "currency": None,
            "exchange_timezone": "UTC",
            "market_state": price.get("status"),
            "bid": bid,
            "ask": ask,
            "spread": ask - bid,
            "retrieved_at": self._iso_now(),
        }

    def get_forex_quote(self, pair, *, data_range="1d", interval="5m"):
        """Retrieve the current OANDA bid/ask and midpoint quote."""
        normalized = normalize_forex_pair(pair)
        if normalized is None:
            raise ValueError(
                "Invalid Forex pair. Use a six-letter pair such as EURUSD."
            )
        return self._price(normalized)

    def _range_params(self, data_range):
        if not isinstance(data_range, str):
            raise ValueError("OANDA historical range must be a string.")
        key = data_range.strip().lower()
        if key == "max":
            return {}
        if key == "ytd":
            now = datetime.now(timezone.utc)
            start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
            return {"from": start.isoformat().replace("+00:00", "Z")}
        days = RANGE_DAYS.get(key)
        if days is None:
            raise ValueError(f"Unsupported OANDA range: {data_range}")
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        return {
            "from": start.isoformat().replace("+00:00", "Z"),
            "to": end.isoformat().replace("+00:00", "Z"),
        }

    @staticmethod
    def _oanda_to_apex_data(response):
        candles = response.get("candles")
        if not isinstance(candles, list):
            raise ValueError("OANDA response does not contain candles.")

        timestamps = []
        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []

        for candle in candles:
            if not isinstance(candle, dict) or not candle.get("complete", True):
                continue
            mid = candle.get("mid")
            if not isinstance(mid, dict):
                continue
            timestamps.append(candle.get("time"))
            opens.append(mid.get("o"))
            highs.append(mid.get("h"))
            lows.append(mid.get("l"))
            closes.append(mid.get("c"))
            volumes.append(candle.get("volume"))

        return {
            "timestamp": timestamps,
            "indicators": {
                "quote": [{
                    "open": [OANDAProvider._number(v) for v in opens],
                    "high": [OANDAProvider._number(v) for v in highs],
                    "low": [OANDAProvider._number(v) for v in lows],
                    "close": [OANDAProvider._number(v) for v in closes],
                    "volume": [OANDAProvider._number(v) for v in volumes],
                }]
            },
        }

    def get_forex_history(self, pair, *, data_range="1d", interval="5m"):
        """Retrieve completed OANDA candles and normalize their shape."""
        normalized = normalize_forex_pair(pair)
        if normalized is None:
            raise ValueError(
                "Invalid Forex pair. Use a six-letter pair such as EURUSD."
            )

        granularity = self.interval_to_granularity(interval)
        if granularity is None:
            raise ValueError(
                f"Unsupported OANDA interval: {interval}"
            )

        symbol = self.forex_pair_to_provider_symbol(normalized)
        params = {
            "granularity": granularity,
            "price": "M",
            "smooth": "false",
            "includeFirst": "true",
            "count": 5000,
        }
        params.update(self._range_params(data_range))

        # OANDA does not allow count together with from/to.
        if "from" in params:
            params.pop("count", None)

        raw = self._get(
            f"/v3/accounts/{self.account_id}/instruments/{symbol}/candles",
            params=params,
        )

        return {
            "pair": normalized,
            "provider_symbol": symbol,
            "provider": self.name,
            "interval": interval,
            "range": data_range,
            "data": self._oanda_to_apex_data(raw),
            "currency": None,
            "exchange_timezone": "UTC",
            "market_state": None,
        }

    def health_check(self):
        """Perform a read-only EURUSD connectivity check."""
        try:
            result = self.get_forex_quote("EURUSD")
            return {
                "success": True,
                "provider": self.name,
                "environment": self.environment,
                "test_pair": "EURUSD",
                "result": {
                    "price": result["candle"].close,
                    "bid": result["bid"],
                    "ask": result["ask"],
                    "spread": result["spread"],
                    "timestamp_utc": result["candle"].timestamp_utc,
                },
            }
        except Exception as error:
            return {
                "success": False,
                "provider": self.name,
                "environment": self.environment,
                "error": str(error),
            }
