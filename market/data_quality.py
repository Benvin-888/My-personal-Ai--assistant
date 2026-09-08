"""
APEX / BENVIN Market Data Quality Foundation

Phase 2.6.6 - Provider-Normalized Data Quality & Comparison

This module evaluates already-retrieved, normalized market-data payloads.
It does not retrieve data, authenticate accounts, place trades, generate
signals, or modify provider state.

Design goals:
    - deterministic, provider-neutral quality checks
    - explicit point-in-time semantics
    - no fabricated values
    - separate structural quality from cross-provider comparison
    - useful diagnostics for later research and execution validation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable, Mapping


class DataQualityError(ValueError):
    """Raised when a quality-analysis request is structurally invalid."""


@dataclass(frozen=True)
class QualityIssue:
    code: str
    severity: str
    message: str
    index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "index": self.index,
        }


@dataclass(frozen=True)
class DataQualityReport:
    """Deterministic structural-quality assessment for normalized data."""

    provider: str | None
    pair: str | None
    data_type: str
    success: bool
    quality: str
    score: float
    observations: int
    issues: tuple[QualityIssue, ...] = field(default_factory=tuple)
    first_timestamp: float | None = None
    last_timestamp: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "pair": self.pair,
            "data_type": self.data_type,
            "success": self.success,
            "quality": self.quality,
            "score": self.score,
            "observations": self.observations,
            "issues": [issue.to_dict() for issue in self.issues],
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
        }


@dataclass(frozen=True)
class ProviderPriceComparison:
    """Point-in-time comparison between two normalized price observations."""

    pair: str
    provider_a: str
    provider_b: str
    timestamp_a: float
    timestamp_b: float
    price_a: float
    price_b: float
    timestamp_delta_seconds: float
    absolute_price_difference: float
    relative_price_difference: float
    within_time_tolerance: bool
    within_price_tolerance: bool

    @property
    def comparable(self) -> bool:
        return self.within_time_tolerance and self.within_price_tolerance

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "provider_a": self.provider_a,
            "provider_b": self.provider_b,
            "timestamp_a": self.timestamp_a,
            "timestamp_b": self.timestamp_b,
            "price_a": self.price_a,
            "price_b": self.price_b,
            "timestamp_delta_seconds": self.timestamp_delta_seconds,
            "absolute_price_difference": self.absolute_price_difference,
            "relative_price_difference": self.relative_price_difference,
            "within_time_tolerance": self.within_time_tolerance,
            "within_price_tolerance": self.within_price_tolerance,
            "comparable": self.comparable,
        }


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise DataQualityError("Market-data observation must be a mapping.")


def _number(value: Any, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DataQualityError(f"{field_name} must be numeric.") from exc
    if not isfinite(result):
        raise DataQualityError(f"{field_name} must be finite.")
    return result


def _timestamp(value: Any, field_name: str = "timestamp") -> float:
    result = _number(value, field_name)
    if result <= 0:
        raise DataQualityError(f"{field_name} must be positive.")
    return result


def _provider(data: Mapping[str, Any]) -> str | None:
    value = data.get("provider")
    return str(value) if value not in (None, "") else None


def _pair(data: Mapping[str, Any]) -> str | None:
    value = data.get("pair")
    return str(value).upper() if value not in (None, "") else None


def _classify(score: float, issues: Iterable[QualityIssue]) -> str:
    issues = tuple(issues)
    if any(issue.severity == "ERROR" for issue in issues):
        return "INVALID"
    if score >= 99:
        return "EXCELLENT"
    if score >= 95:
        return "GOOD"
    if score >= 85:
        return "FAIR"
    return "POOR"


def _score(observations: int, issues: list[QualityIssue]) -> float:
    if observations <= 0:
        return 0.0
    deductions = 0.0
    for issue in issues:
        deductions += {"ERROR": 100.0, "WARNING": 10.0, "INFO": 1.0}.get(issue.severity, 5.0)
    return round(max(0.0, 100.0 - deductions / observations), 3)


def assess_ticks(data: Mapping[str, Any]) -> DataQualityReport:
    """Assess normalized tick-history payloads."""

    data = _as_mapping(data)
    ticks = data.get("ticks", [])
    if ticks is None:
        ticks = []
    if not isinstance(ticks, (list, tuple)):
        raise DataQualityError("ticks must be a list or tuple.")

    issues: list[QualityIssue] = []
    timestamps: list[float] = []
    provider_symbols: set[str] = set()
    pair = _pair(data)
    provider = _provider(data)

    for index, raw in enumerate(ticks):
        try:
            tick = _as_mapping(raw)
            ts = _timestamp(tick.get("timestamp"))
            price = _number(tick.get("price"), "price")
        except DataQualityError as exc:
            issues.append(QualityIssue("INVALID_TICK", "ERROR", str(exc), index))
            continue

        if price <= 0:
            issues.append(QualityIssue("NON_POSITIVE_PRICE", "ERROR", "Tick price must be positive.", index))
        timestamps.append(ts)
        symbol = tick.get("provider_symbol")
        if symbol:
            provider_symbols.add(str(symbol))

        if index and ts < timestamps[-2]:
            issues.append(QualityIssue("OUT_OF_ORDER", "WARNING", "Ticks are not chronological.", index))

    if len(provider_symbols) > 1:
        issues.append(QualityIssue("MIXED_PROVIDER_SYMBOLS", "ERROR", "Tick history contains multiple provider symbols."))

    if len(timestamps) != len(set(timestamps)):
        issues.append(QualityIssue("DUPLICATE_TIMESTAMPS", "WARNING", "Duplicate tick timestamps are present."))

    score = _score(len(ticks), issues)
    quality = _classify(score, issues)
    return DataQualityReport(
        provider=provider,
        pair=pair,
        data_type="ticks",
        success=not any(issue.severity == "ERROR" for issue in issues),
        quality=quality,
        score=score,
        observations=len(ticks),
        issues=tuple(issues),
        first_timestamp=min(timestamps) if timestamps else None,
        last_timestamp=max(timestamps) if timestamps else None,
    )


def assess_candles(data: Mapping[str, Any]) -> DataQualityReport:
    """Assess normalized OHLC history without changing its values."""

    data = _as_mapping(data)
    candles = data.get("candles", [])
    if candles is None:
        candles = []
    if not isinstance(candles, (list, tuple)):
        raise DataQualityError("candles must be a list or tuple.")

    issues: list[QualityIssue] = []
    timestamps: list[float] = []
    pair = _pair(data)
    provider = _provider(data)

    for index, raw in enumerate(candles):
        try:
            candle = _as_mapping(raw)
            ts = _timestamp(candle.get("timestamp"))
            open_price = _number(candle.get("open"), "open")
            high = _number(candle.get("high"), "high")
            low = _number(candle.get("low"), "low")
            close = _number(candle.get("close"), "close")
        except DataQualityError as exc:
            issues.append(QualityIssue("INVALID_CANDLE", "ERROR", str(exc), index))
            continue

        if min(open_price, high, low, close) <= 0:
            issues.append(QualityIssue("NON_POSITIVE_PRICE", "ERROR", "OHLC prices must be positive.", index))
        if high < max(open_price, close, low):
            issues.append(QualityIssue("INVALID_HIGH", "ERROR", "High must be at least open, close, and low.", index))
        if low > min(open_price, close, high):
            issues.append(QualityIssue("INVALID_LOW", "ERROR", "Low must be at most open, close, and high.", index))
        if index and ts <= timestamps[-1]:
            issues.append(QualityIssue("NON_CHRONOLOGICAL", "ERROR", "Candle timestamps must be strictly increasing.", index))
        timestamps.append(ts)

    score = _score(len(candles), issues)
    quality = _classify(score, issues)
    return DataQualityReport(
        provider=provider,
        pair=pair,
        data_type="candles",
        success=not any(issue.severity == "ERROR" for issue in issues),
        quality=quality,
        score=score,
        observations=len(candles),
        issues=tuple(issues),
        first_timestamp=min(timestamps) if timestamps else None,
        last_timestamp=max(timestamps) if timestamps else None,
    )


def _extract_price_observation(data: Mapping[str, Any]) -> tuple[str, str, float, float]:
    provider = _provider(data)
    pair = _pair(data)
    if not provider:
        raise DataQualityError("Provider is required for comparison.")
    if not pair:
        raise DataQualityError("Pair is required for comparison.")
    timestamp = _timestamp(data.get("timestamp"))
    price = _number(data.get("price"), "price")
    if price <= 0:
        raise DataQualityError("price must be positive.")
    return provider, pair, timestamp, price


def compare_prices(
    observation_a: Mapping[str, Any],
    observation_b: Mapping[str, Any],
    *,
    max_timestamp_delta_seconds: float = 2.0,
    max_relative_difference: float = 0.001,
) -> ProviderPriceComparison:
    """Compare two point-in-time provider observations.

    Comparison never declares which provider is correct. It only reports
    whether the observations fall within explicit temporal and price
    tolerances.
    """

    if max_timestamp_delta_seconds < 0:
        raise DataQualityError("max_timestamp_delta_seconds cannot be negative.")
    if max_relative_difference < 0:
        raise DataQualityError("max_relative_difference cannot be negative.")

    provider_a, pair_a, timestamp_a, price_a = _extract_price_observation(_as_mapping(observation_a))
    provider_b, pair_b, timestamp_b, price_b = _extract_price_observation(_as_mapping(observation_b))

    if pair_a != pair_b:
        raise DataQualityError(f"Cannot compare different pairs: {pair_a} vs {pair_b}.")
    if provider_a.casefold() == provider_b.casefold():
        raise DataQualityError("Provider comparison requires two different providers.")

    timestamp_delta = abs(timestamp_a - timestamp_b)
    absolute_difference = abs(price_a - price_b)
    relative_difference = absolute_difference / ((price_a + price_b) / 2.0)

    return ProviderPriceComparison(
        pair=pair_a,
        provider_a=provider_a,
        provider_b=provider_b,
        timestamp_a=timestamp_a,
        timestamp_b=timestamp_b,
        price_a=price_a,
        price_b=price_b,
        timestamp_delta_seconds=round(timestamp_delta, 9),
        absolute_price_difference=round(absolute_difference, 12),
        relative_price_difference=round(relative_difference, 12),
        within_time_tolerance=timestamp_delta <= max_timestamp_delta_seconds,
        within_price_tolerance=relative_difference <= max_relative_difference,
    )


def assess_market_data(data: Mapping[str, Any]) -> DataQualityReport:
    """Dispatch quality assessment from a normalized payload."""

    data = _as_mapping(data)
    if "ticks" in data:
        return assess_ticks(data)
    if "candles" in data:
        return assess_candles(data)
    raise DataQualityError("Payload must contain either 'ticks' or 'candles'.")
