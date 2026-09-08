"""
APEX / BENVIN Tick Market Models

Phase 2.6.2 - Historical Tick Data

These models represent validated point-in-time market ticks.

They contain market observations only. They do not contain:
    - trading signals
    - strategies
    - recommendations
    - entries/exits
    - position sizing
    - account state
    - execution authority
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HistoricalTick:
    """One validated historical market tick."""

    timestamp: int
    timestamp_utc: str
    price: float
    provider: str
    provider_symbol: str
    raw_tick: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "timestamp_utc": self.timestamp_utc,
            "price": self.price,
            "provider": self.provider,
            "provider_symbol": self.provider_symbol,
            "raw_tick": dict(self.raw_tick),
        }


@dataclass(frozen=True)
class ForexTickHistory:
    """Chronologically ordered validated historical Forex ticks."""

    pair: str
    base_currency: str
    quote_currency: str
    provider_symbol: str
    provider: str
    ticks: tuple[HistoricalTick, ...]
    requested_count: int | None = None
    start_timestamp: int | None = None
    end_timestamp: int | None = None
    retrieved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        first_timestamp = self.ticks[0].timestamp_utc if self.ticks else None
        latest_timestamp = self.ticks[-1].timestamp_utc if self.ticks else None

        return {
            "success": True,
            "market": "forex",
            "data_type": "historical_ticks",
            "pair": self.pair,
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
            "provider_symbol": self.provider_symbol,
            "provider": self.provider,
            "tick_count": len(self.ticks),
            "requested_count": self.requested_count,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "first_tick_timestamp": first_timestamp,
            "latest_tick_timestamp": latest_timestamp,
            "ticks": [tick.to_dict() for tick in self.ticks],
            "retrieved_at": self.retrieved_at,
        }
