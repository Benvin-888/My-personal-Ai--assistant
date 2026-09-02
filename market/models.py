"""
APEX / BENVIN Market Data Models

Phase 2 - Market Intelligence Foundation

This module contains standardized data structures used by
the market-data system.

IMPORTANT:

    These models describe market information.

    They do NOT:
        - generate trading signals
        - recommend trades
        - execute trades
        - calculate position sizes
        - modify broker accounts
"""

from dataclasses import dataclass, field
from typing import Any


# ============================================================
# CANDLE
# ============================================================

@dataclass(frozen=True)
class Candle:
    """
    Standard OHLCV market candle.
    """

    timestamp: int | float | None
    timestamp_utc: str | None

    open: float | int | None
    high: float | int | None
    low: float | int | None
    close: float | int | None

    volume: float | int | None = None

    def to_dict(self):
        """
        Convert the candle into a serializable dictionary.
        """

        return {
            "timestamp": self.timestamp,
            "timestamp_utc": self.timestamp_utc,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


# ============================================================
# FOREX QUOTE
# ============================================================

@dataclass(frozen=True)
class ForexQuote:
    """
    Standardized Forex quote returned by the market-data layer.
    """

    pair: str

    base_currency: str
    quote_currency: str

    provider_symbol: str
    provider: str

    interval: str
    data_range: str

    price: float | int

    candle: Candle

    currency: str | None = None
    exchange_timezone: str | None = None
    market_state: str | None = None

    retrieved_at: str | None = None

    def to_dict(self):
        """
        Convert the quote into a serializable dictionary.
        """

        return {
            "success": True,
            "market": "forex",
            "pair": self.pair,
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
            "provider_symbol": self.provider_symbol,
            "provider": self.provider,
            "interval": self.interval,
            "range": self.data_range,
            "price": self.price,
            "candle": self.candle.to_dict(),
            "currency": self.currency,
            "exchange_timezone": self.exchange_timezone,
            "market_state": self.market_state,
            "retrieved_at": self.retrieved_at,
        }


# ============================================================
# FOREX HISTORY
# ============================================================

@dataclass(frozen=True)
class ForexHistory:
    """
    Standardized historical Forex market data.

    This model represents a chronological collection of
    validated market candles.

    The candles themselves contain only market data.

    This model does NOT contain:
        - trading signals
        - strategies
        - recommendations
        - entries
        - exits
        - position sizes
        - trading decisions
    """

    pair: str

    base_currency: str
    quote_currency: str

    provider_symbol: str
    provider: str

    interval: str
    data_range: str

    candles: tuple[Candle, ...]

    total_provider_rows: int = 0
    invalid_candles: int = 0

    currency: str | None = None
    exchange_timezone: str | None = None
    market_state: str | None = None

    retrieved_at: str | None = None

    def to_dict(self):
        """
        Convert the historical dataset into a serializable
        dictionary.
        """

        candle_list = [
            candle.to_dict()
            for candle in self.candles
        ]

        first_timestamp = None
        latest_timestamp = None

        if self.candles:

            first_timestamp = (
                self.candles[0].timestamp_utc
            )

            latest_timestamp = (
                self.candles[-1].timestamp_utc
            )

        return {
            "success": True,
            "market": "forex",
            "pair": self.pair,
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
            "provider_symbol": self.provider_symbol,
            "provider": self.provider,
            "interval": self.interval,
            "range": self.data_range,
            "currency": self.currency,
            "exchange_timezone": self.exchange_timezone,
            "market_state": self.market_state,
            "candle_count": len(candle_list),
            "total_provider_rows": self.total_provider_rows,
            "invalid_candles": self.invalid_candles,
            "first_candle_timestamp": first_timestamp,
            "latest_candle_timestamp": latest_timestamp,
            "candles": candle_list,
            "retrieved_at": self.retrieved_at,
        }


# ============================================================
# MARKET DATA ERROR
# ============================================================

@dataclass(frozen=True)
class MarketDataError:
    """
    Standardized market-data error.
    """

    market: str
    error: str

    pair: str | None = None
    provider: str | None = None

    details: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self):
        """
        Convert the error into a serializable dictionary.
        """

        result = {
            "success": False,
            "market": self.market,
        }

        if self.pair is not None:
            result["pair"] = self.pair

        if self.provider is not None:
            result["provider"] = self.provider

        result["error"] = self.error

        if self.details:
            result["details"] = self.details

        return result