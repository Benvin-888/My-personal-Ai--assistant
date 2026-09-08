"""
APEX / BENVIN Deterministic Tick -> OHLC Aggregation

Phase 2.6.3 - Deterministic Tick-to-OHLC Aggregation

This module converts validated point-in-time Forex ticks into deterministic
OHLC candles. It is deliberately provider-agnostic: it does not retrieve
market data, stream ticks, generate signals, or execute trades.

Design guarantees:
    - only supplied ticks are used
    - ticks are processed in chronological order
    - candle boundaries are deterministic UTC epoch buckets
    - open is the first tick in the bucket
    - high/low are extrema of ticks in the bucket
    - close is the last tick in the bucket
    - no traded volume is fabricated from tick data
    - no future data is used to construct an earlier candle
    - empty intervals are omitted rather than filled with synthetic values
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from .models import Candle, ForexHistory
from .provider import normalize_forex_pair
from .ticks import ForexTickHistory, HistoricalTick


SUPPORTED_TICK_OHLC_INTERVALS = {
    "1m": 60,
    "2m": 120,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "60m": 3600,
    "90m": 5400,
    "1h": 3600,
    "1d": 86400,
}


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _timestamp_to_utc(timestamp: int) -> str:
    try:
        return (
            datetime.fromtimestamp(timestamp, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("Invalid Unix timestamp.") from exc


def _validate_timestamp(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer Unix timestamp.")

    if isinstance(value, int):
        timestamp = value
    elif isinstance(value, float):
        if not isfinite(value) or not value.is_integer():
            raise ValueError(f"{field_name} must be a whole Unix timestamp.")
        timestamp = int(value)
    elif isinstance(value, str):
        try:
            numeric = float(value.strip())
        except ValueError:
            raise ValueError(f"{field_name} must be a valid Unix timestamp.") from None
        if not isfinite(numeric) or not numeric.is_integer():
            raise ValueError(f"{field_name} must be a whole Unix timestamp.")
        timestamp = int(numeric)
    else:
        raise ValueError(f"{field_name} must be a valid Unix timestamp.")

    if timestamp < 0:
        raise ValueError(f"{field_name} cannot be negative.")

    # Also verify that Python can represent it as UTC.
    _timestamp_to_utc(timestamp)
    return timestamp


def _validate_price(value: Any, field_name: str = "price") -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive finite number.")
    try:
        price = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a positive finite number.") from None

    if not isfinite(price) or price <= 0:
        raise ValueError(f"{field_name} must be a positive finite number.")
    return price


def _coerce_tick(value: HistoricalTick | Mapping[str, Any]) -> HistoricalTick:
    if isinstance(value, HistoricalTick):
        return HistoricalTick(
            timestamp=_validate_timestamp(value.timestamp, "tick timestamp"),
            timestamp_utc=_timestamp_to_utc(
                _validate_timestamp(value.timestamp, "tick timestamp")
            ),
            price=_validate_price(value.price),
            provider=str(value.provider),
            provider_symbol=str(value.provider_symbol),
            raw_tick=dict(value.raw_tick),
        )

    if isinstance(value, Mapping):
        timestamp = _validate_timestamp(value.get("timestamp"), "tick timestamp")
        price = _validate_price(value.get("price"))
        provider = value.get("provider")
        provider_symbol = value.get("provider_symbol")
        if not isinstance(provider, str) or not provider:
            raise ValueError("Each tick must contain a provider.")
        if not isinstance(provider_symbol, str) or not provider_symbol:
            raise ValueError("Each tick must contain a provider_symbol.")
        raw_tick = value.get("raw_tick", {})
        if not isinstance(raw_tick, Mapping):
            raise ValueError("tick raw_tick must be a mapping when supplied.")
        return HistoricalTick(
            timestamp=timestamp,
            timestamp_utc=_timestamp_to_utc(timestamp),
            price=price,
            provider=provider,
            provider_symbol=provider_symbol,
            raw_tick=dict(raw_tick),
        )

    raise TypeError("Ticks must be HistoricalTick objects or mappings.")


def _extract_metadata(
    tick_history: ForexTickHistory | Mapping[str, Any] | Sequence[HistoricalTick | Mapping[str, Any]],
) -> tuple[str | None, str | None, str | None, Sequence[Any]]:
    if isinstance(tick_history, ForexTickHistory):
        return (
            tick_history.pair,
            tick_history.provider_symbol,
            tick_history.provider,
            tick_history.ticks,
        )

    if isinstance(tick_history, Mapping):
        ticks = tick_history.get("ticks")
        if not isinstance(ticks, Sequence) or isinstance(ticks, (str, bytes, bytearray)):
            raise ValueError("Tick history mapping must contain a ticks sequence.")
        return (
            tick_history.get("pair"),
            tick_history.get("provider_symbol"),
            tick_history.get("provider"),
            ticks,
        )

    if isinstance(tick_history, Sequence) and not isinstance(tick_history, (str, bytes, bytearray)):
        return None, None, None, tick_history

    raise TypeError("tick_history must be ForexTickHistory, a mapping, or a sequence of ticks.")


def _validate_interval(interval: str) -> int:
    if not isinstance(interval, str):
        raise ValueError("interval must be a string.")
    seconds = SUPPORTED_TICK_OHLC_INTERVALS.get(interval.strip())
    if seconds is None:
        supported = ", ".join(SUPPORTED_TICK_OHLC_INTERVALS)
        raise ValueError(f"Unsupported tick OHLC interval '{interval}'. Supported: {supported}.")
    return seconds


def _validate_pair(pair: str | None) -> str:
    if not isinstance(pair, str):
        raise ValueError("A normalized Forex pair is required for OHLC aggregation.")
    normalized = normalize_forex_pair(pair)
    if normalized is None:
        raise ValueError("Invalid Forex pair. Use a six-letter pair such as EURUSD.")
    return normalized


def aggregate_ticks_to_ohlc(
    tick_history: ForexTickHistory | Mapping[str, Any] | Sequence[HistoricalTick | Mapping[str, Any]],
    *,
    interval: str,
) -> dict[str, Any]:
    """
    Aggregate validated point-in-time ticks into deterministic Forex candles.

    Candle timestamps are UTC epoch bucket starts. Empty buckets are omitted.
    Volume remains None because tick count is not traded volume.
    """
    seconds = _validate_interval(interval)
    pair, provider_symbol, provider, raw_ticks = _extract_metadata(tick_history)

    if pair is None:
        raise ValueError("pair metadata is required when a raw tick sequence is supplied.")
    normalized_pair = _validate_pair(pair)

    ticks = [_coerce_tick(tick) for tick in raw_ticks]
    if not ticks:
        return ForexHistory(
            pair=normalized_pair,
            base_currency=normalized_pair[:3],
            quote_currency=normalized_pair[3:],
            provider_symbol=provider_symbol or "",
            provider=provider or "",
            interval=interval,
            data_range="tick_aggregation",
            candles=tuple(),
            total_provider_rows=0,
            invalid_candles=0,
            retrieved_at=_utc_now(),
        ).to_dict()

    ticks.sort(key=lambda tick: tick.timestamp)

    if provider is None:
        provider = ticks[0].provider
    if provider_symbol is None:
        provider_symbol = ticks[0].provider_symbol

    for tick in ticks:
        if tick.provider != provider:
            raise ValueError("All ticks must use the same provider.")
        if tick.provider_symbol != provider_symbol:
            raise ValueError("All ticks must use the same provider symbol.")

    candles: list[Candle] = []
    bucket_start: int | None = None
    bucket_ticks: list[HistoricalTick] = []

    def flush_bucket() -> None:
        if not bucket_ticks or bucket_start is None:
            return
        prices = [tick.price for tick in bucket_ticks]
        candles.append(
            Candle(
                timestamp=bucket_start,
                timestamp_utc=_timestamp_to_utc(bucket_start),
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                # Deriv historical ticks do not provide traded volume.
                volume=None,
            )
        )

    for tick in ticks:
        current_bucket = (tick.timestamp // seconds) * seconds
        if bucket_start is None:
            bucket_start = current_bucket
        elif current_bucket != bucket_start:
            flush_bucket()
            bucket_ticks = []
            bucket_start = current_bucket
        bucket_ticks.append(tick)

    flush_bucket()

    return ForexHistory(
        pair=normalized_pair,
        base_currency=normalized_pair[:3],
        quote_currency=normalized_pair[3:],
        provider_symbol=provider_symbol,
        provider=provider,
        interval=interval,
        data_range="tick_aggregation",
        candles=tuple(candles),
        total_provider_rows=len(ticks),
        invalid_candles=0,
        retrieved_at=_utc_now(),
    ).to_dict()


class TickOHLCBuilder:
    """Small deterministic facade around :func:`aggregate_ticks_to_ohlc`."""

    def aggregate(
        self,
        tick_history: ForexTickHistory | Mapping[str, Any] | Sequence[HistoricalTick | Mapping[str, Any]],
        *,
        interval: str,
    ) -> dict[str, Any]:
        return aggregate_ticks_to_ohlc(tick_history, interval=interval)
