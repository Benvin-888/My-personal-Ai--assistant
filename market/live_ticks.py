"""
APEX / BENVIN Live Tick Stream Models

Phase 2.6.4 - Live Deriv Tick Streaming

Provider-agnostic normalized models for a live, point-in-time tick stream.
This module contains no WebSocket transport and no trading authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class LiveTick:
    """A validated point-in-time market tick received from a live provider."""

    timestamp: int
    timestamp_utc: str
    price: float
    provider: str
    provider_symbol: str
    raw_tick: dict[str, Any]
    received_at: str
    sequence: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "timestamp_utc": self.timestamp_utc,
            "price": self.price,
            "provider": self.provider,
            "provider_symbol": self.provider_symbol,
            "raw_tick": dict(self.raw_tick),
            "received_at": self.received_at,
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class StreamEvent:
    """Lifecycle/diagnostic event emitted by the live stream."""

    event_type: str
    provider: str
    provider_symbol: str
    occurred_at: str
    reconnect_attempt: int = 0
    error: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "provider": self.provider,
            "provider_symbol": self.provider_symbol,
            "occurred_at": self.occurred_at,
            "reconnect_attempt": self.reconnect_attempt,
            "error": self.error,
            "details": dict(self.details or {}),
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
