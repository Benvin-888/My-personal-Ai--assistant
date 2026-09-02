"""
APEX / BENVIN Technical Analysis Models

Phase 2.3 - Technical Analysis Foundation

These models describe deterministic analytical results derived from
validated market candles.

They do NOT represent:
    - trading signals
    - trade recommendations
    - entries or exits
    - position sizing
    - broker actions
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IndicatorValue:
    """One calculated indicator value."""

    name: str
    period: int | None
    value: float | None
    timestamp_utc: str | None
    valid: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "name": self.name,
            "period": self.period,
            "value": self.value,
            "timestamp_utc": self.timestamp_utc,
            "valid": self.valid,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class TechnicalAnalysis:
    """Structured technical-analysis snapshot."""

    pair: str
    interval: str
    candle_count: int
    provider: str | None
    source_range: str | None
    latest_timestamp_utc: str | None
    trend: str
    momentum: str
    volatility: str
    indicators: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "success": True,
            "market": "forex",
            "analysis": "technical",
            "pair": self.pair,
            "interval": self.interval,
            "candle_count": self.candle_count,
            "provider": self.provider,
            "range": self.source_range,
            "latest_timestamp_utc": self.latest_timestamp_utc,
            "classification": {
                "trend": self.trend,
                "momentum": self.momentum,
                "volatility": self.volatility,
            },
            "indicators": self.indicators,
            "metadata": self.metadata,
        }
