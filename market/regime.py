"""
APEX / BENVIN Market Regime & Context Engine

Phase 2.6.11

This module converts an already-produced technical-analysis snapshot into a
structured, deterministic description of the market environment.

It does NOT:
    - generate trading signals
    - recommend an entry
    - calculate stop-loss or take-profit levels
    - calculate position size
    - authorize a trade
    - execute anything

The engine is deliberately provider-neutral and point-in-time friendly. It
uses only the analytical snapshot supplied by the caller and never performs
network I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping


class MarketRegimeError(ValueError):
    """Raised when regime input or configuration is invalid."""


class RegimeStatus:
    EVALUATED = "EVALUATED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class MarketRegime:
    BULLISH_TREND = "BULLISH_TREND"
    BEARISH_TREND = "BEARISH_TREND"
    BULLISH_TRANSITION = "BULLISH_TRANSITION"
    BEARISH_TRANSITION = "BEARISH_TRANSITION"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimePolicy:
    """Deterministic policy controlling descriptive regime classification."""

    require_successful_analysis: bool = True
    require_operational_state: bool = False
    allow_degraded_operational_state: bool = False
    bollinger_position_lower: float = 0.20
    bollinger_position_upper: float = 0.80
    minimum_directional_alignment: float = 0.67

    def __post_init__(self) -> None:
        for name in (
            "bollinger_position_lower",
            "bollinger_position_upper",
            "minimum_directional_alignment",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(float(value))
            ):
                raise MarketRegimeError(f"{name} must be finite numeric")

        if not 0.0 <= float(self.bollinger_position_lower) < float(self.bollinger_position_upper) <= 1.0:
            raise MarketRegimeError(
                "bollinger position thresholds must satisfy 0 <= lower < upper <= 1"
            )
        if not 0.0 < float(self.minimum_directional_alignment) <= 1.0:
            raise MarketRegimeError(
                "minimum_directional_alignment must be greater than 0 and at most 1"
            )


@dataclass(frozen=True)
class MarketRegimeContext:
    """Immutable descriptive snapshot of the current market environment."""

    pair: str
    interval: str
    timestamp_utc: str | None
    status: str
    regime: str
    trend: str
    momentum: str
    volatility: str
    trend_strength: str
    momentum_alignment: str
    volatility_context: str
    price_location: str
    bollinger_position: float | None
    normalized_atr: float | None
    latest_close: float | None
    analysis_usable: bool
    operational_state: str | None = None
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "success": self.status == RegimeStatus.EVALUATED,
            "market": "forex",
            "analysis": "market_regime",
            "status": self.status,
            "pair": self.pair,
            "interval": self.interval,
            "timestamp_utc": self.timestamp_utc,
            "regime": self.regime,
            "dimensions": {
                "trend": self.trend,
                "momentum": self.momentum,
                "volatility": self.volatility,
                "trend_strength": self.trend_strength,
                "momentum_alignment": self.momentum_alignment,
                "volatility_context": self.volatility_context,
                "price_location": self.price_location,
            },
            "measurements": {
                "bollinger_position": self.bollinger_position,
                "normalized_atr": self.normalized_atr,
                "latest_close": self.latest_close,
            },
            "analysis_usable": self.analysis_usable,
            "operational_state": self.operational_state,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "evidence": list(self.evidence),
            "metadata": dict(self.metadata),
        }
        if self.error is not None:
            result["error"] = self.error
        return result


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if isfinite(value) else None


def _mapping(value: Any, name: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise MarketRegimeError(f"{name} must be a mapping when supplied")
    return value


def _indicator_value(analysis: Mapping[str, Any], name: str) -> float | None:
    indicators = analysis.get("indicators")
    if not isinstance(indicators, Mapping):
        return None
    value = indicators.get(name)
    if isinstance(value, Mapping):
        return _finite(value.get("value"))
    return _finite(value)


def _macd_histogram(analysis: Mapping[str, Any]) -> float | None:
    indicators = analysis.get("indicators")
    if not isinstance(indicators, Mapping):
        return None
    macd = indicators.get("macd")
    if not isinstance(macd, Mapping):
        return None
    return _finite(macd.get("histogram"))


def _bollinger_position(analysis: Mapping[str, Any], close: float | None) -> float | None:
    indicators = analysis.get("indicators")
    if not isinstance(indicators, Mapping) or close is None:
        return None
    bands = indicators.get("bollinger_bands")
    if not isinstance(bands, Mapping):
        return None
    lower = _finite(bands.get("lower"))
    upper = _finite(bands.get("upper"))
    if lower is None or upper is None or upper <= lower:
        return None
    position = (close - lower) / (upper - lower)
    if not isfinite(position):
        return None
    return round(max(0.0, min(1.0, position)), 12)


def _operational_details(
    operational_state: Mapping[str, Any] | None,
    policy: RegimePolicy,
) -> tuple[str | None, bool, list[str], list[str]]:
    if operational_state is None:
        if policy.require_operational_state:
            return None, False, ["operational state is required"], []
        return None, True, [], []

    if not isinstance(operational_state, Mapping):
        raise MarketRegimeError("operational state must be a mapping when supplied")

    status = operational_state.get("status")
    if not isinstance(status, str) or not status.strip():
        raise MarketRegimeError("operational state status must be a non-empty string")

    usable = operational_state.get("analysis_usable")
    if not isinstance(usable, bool):
        raise MarketRegimeError("operational state analysis_usable must be boolean")

    reasons: list[str] = []
    warnings: list[str] = []
    if not usable:
        if policy.allow_degraded_operational_state and status == "DEGRADED":
            warnings.append("operational state is DEGRADED but policy permits analysis")
            return status, True, reasons, warnings
        reasons.append("operational state does not permit analysis")
        return status, False, reasons, warnings

    return status, True, reasons, warnings


def assess_market_regime(
    analysis: Mapping[str, Any],
    *,
    operational_state: Mapping[str, Any] | None = None,
    policy: RegimePolicy | None = None,
) -> MarketRegimeContext:
    """Assess a deterministic market regime from an existing TA snapshot."""
    policy = policy or RegimePolicy()
    if not isinstance(analysis, Mapping):
        raise MarketRegimeError("technical analysis must be a mapping")

    pair = str(analysis.get("pair", "UNKNOWN"))
    interval = str(analysis.get("interval", "UNKNOWN"))
    timestamp = analysis.get("latest_timestamp_utc")
    reasons: list[str] = []
    warnings: list[str] = []

    if policy.require_successful_analysis and analysis.get("success") is not True:
        return MarketRegimeContext(
            pair=pair,
            interval=interval,
            timestamp_utc=timestamp,
            status=RegimeStatus.BLOCKED,
            regime=MarketRegime.UNKNOWN,
            trend="UNKNOWN",
            momentum="UNKNOWN",
            volatility="UNKNOWN",
            trend_strength="UNKNOWN",
            momentum_alignment="UNKNOWN",
            volatility_context="UNKNOWN",
            price_location="UNKNOWN",
            bollinger_position=None,
            normalized_atr=None,
            latest_close=None,
            analysis_usable=False,
            reasons=("technical analysis is not successful",),
            warnings=(),
            evidence=(),
            metadata={"calculation": "deterministic_python"},
        )

    operational_name, operational_usable, op_reasons, op_warnings = _operational_details(
        operational_state,
        policy,
    )
    reasons.extend(op_reasons)
    warnings.extend(op_warnings)
    if not operational_usable:
        return MarketRegimeContext(
            pair=pair,
            interval=interval,
            timestamp_utc=timestamp,
            status=RegimeStatus.BLOCKED,
            regime=MarketRegime.UNKNOWN,
            trend=str(analysis.get("classification", {}).get("trend", "UNKNOWN")),
            momentum=str(analysis.get("classification", {}).get("momentum", "UNKNOWN")),
            volatility=str(analysis.get("classification", {}).get("volatility", "UNKNOWN")),
            trend_strength="UNKNOWN",
            momentum_alignment="UNKNOWN",
            volatility_context="UNKNOWN",
            price_location="UNKNOWN",
            bollinger_position=None,
            normalized_atr=None,
            latest_close=_finite(analysis.get("metadata", {}).get("latest_close")) if isinstance(analysis.get("metadata"), Mapping) else None,
            analysis_usable=False,
            operational_state=operational_name,
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            evidence=(),
            metadata={"calculation": "deterministic_python"},
        )

    classification = _mapping(analysis.get("classification"), "classification") or {}
    trend = str(classification.get("trend", "UNKNOWN"))
    momentum = str(classification.get("momentum", "UNKNOWN"))
    volatility = str(classification.get("volatility", "UNKNOWN"))

    metadata = _mapping(analysis.get("metadata"), "metadata") or {}
    close = _finite(metadata.get("latest_close"))
    if close is None:
        close = _finite(analysis.get("latest_close"))

    atr_value = _indicator_value(analysis, "atr")
    normalized_atr = None
    if atr_value is not None and close is not None and close != 0:
        normalized_atr = atr_value / abs(close)

    bb_position = _bollinger_position(analysis, close)

    if trend == "BULLISH":
        trend_strength = "DIRECTIONAL_UP"
    elif trend == "BEARISH":
        trend_strength = "DIRECTIONAL_DOWN"
    elif trend == "MIXED":
        trend_strength = "TRANSITIONAL"
    elif trend == "NEUTRAL":
        trend_strength = "NON_DIRECTIONAL"
    else:
        trend_strength = "UNKNOWN"

    if trend == "BULLISH" and momentum == "POSITIVE":
        momentum_alignment = "ALIGNED_BULLISH"
    elif trend == "BEARISH" and momentum == "NEGATIVE":
        momentum_alignment = "ALIGNED_BEARISH"
    elif trend == "BULLISH" and momentum == "NEGATIVE":
        momentum_alignment = "DIVERGENT_BEARISH"
    elif trend == "BEARISH" and momentum == "POSITIVE":
        momentum_alignment = "DIVERGENT_BULLISH"
    elif momentum == "NEUTRAL":
        momentum_alignment = "NEUTRAL"
    else:
        momentum_alignment = "MIXED"

    if volatility == "HIGH":
        volatility_context = "EXPANDED"
    elif volatility == "LOW":
        volatility_context = "COMPRESSED"
    elif volatility == "MODERATE":
        volatility_context = "NORMAL"
    else:
        volatility_context = "UNKNOWN"

    if bb_position is None:
        price_location = "UNKNOWN"
    elif bb_position <= policy.bollinger_position_lower:
        price_location = "LOWER_BAND_REGION"
    elif bb_position >= policy.bollinger_position_upper:
        price_location = "UPPER_BAND_REGION"
    else:
        price_location = "MID_BAND_REGION"

    evidence: list[str] = []
    if trend in {"BULLISH", "BEARISH"}:
        evidence.append(f"trend={trend}")
    if momentum in {"POSITIVE", "NEGATIVE"}:
        evidence.append(f"momentum={momentum}")
    if volatility in {"LOW", "MODERATE", "HIGH"}:
        evidence.append(f"volatility={volatility}")
    if bb_position is not None:
        evidence.append(f"bollinger_position={bb_position:.6f}")

    if trend == "BULLISH" and momentum == "POSITIVE":
        regime = MarketRegime.BULLISH_TREND
    elif trend == "BEARISH" and momentum == "NEGATIVE":
        regime = MarketRegime.BEARISH_TREND
    elif trend == "BULLISH" and momentum == "NEGATIVE":
        regime = MarketRegime.BULLISH_TRANSITION
    elif trend == "BEARISH" and momentum == "POSITIVE":
        regime = MarketRegime.BEARISH_TRANSITION
    elif trend == "MIXED":
        regime = MarketRegime.MIXED
    elif trend == "NEUTRAL" and volatility == "HIGH":
        regime = MarketRegime.HIGH_VOLATILITY
    elif trend == "NEUTRAL" and volatility == "LOW":
        regime = MarketRegime.LOW_VOLATILITY
    elif trend == "NEUTRAL" and volatility in {"MODERATE", "UNKNOWN"}:
        regime = MarketRegime.RANGE
    else:
        regime = MarketRegime.MIXED

    if trend == "BULLISH" and momentum == "POSITIVE":
        directional_alignment = 1.0
    elif trend == "BEARISH" and momentum == "NEGATIVE":
        directional_alignment = 1.0
    elif trend in {"BULLISH", "BEARISH"} and momentum == "NEUTRAL":
        directional_alignment = 0.5
    elif trend in {"BULLISH", "BEARISH"} and momentum in {"POSITIVE", "NEGATIVE"}:
        directional_alignment = 0.0
    else:
        directional_alignment = 0.0

    if directional_alignment < policy.minimum_directional_alignment and trend in {"BULLISH", "BEARISH"}:
        warnings.append("trend and momentum are not strongly aligned")

    if trend == "UNKNOWN" or momentum == "UNKNOWN" or volatility == "UNKNOWN":
        status = RegimeStatus.INSUFFICIENT_DATA
        usable = False
        reasons.append("one or more regime dimensions are unavailable")
    else:
        status = RegimeStatus.EVALUATED
        usable = operational_usable

    return MarketRegimeContext(
        pair=pair,
        interval=interval,
        timestamp_utc=timestamp,
        status=status,
        regime=regime,
        trend=trend,
        momentum=momentum,
        volatility=volatility,
        trend_strength=trend_strength,
        momentum_alignment=momentum_alignment,
        volatility_context=volatility_context,
        price_location=price_location,
        bollinger_position=bb_position,
        normalized_atr=normalized_atr,
        latest_close=close,
        analysis_usable=usable,
        operational_state=operational_name,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        evidence=tuple(evidence),
        metadata={
            "calculation": "deterministic_python",
            "policy": {
                "require_successful_analysis": policy.require_successful_analysis,
                "require_operational_state": policy.require_operational_state,
                "allow_degraded_operational_state": policy.allow_degraded_operational_state,
                "bollinger_position_lower": float(policy.bollinger_position_lower),
                "bollinger_position_upper": float(policy.bollinger_position_upper),
                "minimum_directional_alignment": float(policy.minimum_directional_alignment),
            },
            "directional_alignment": directional_alignment,
        },
    )


class MarketRegimeEngine:
    """Reusable facade for deterministic market-regime assessment."""

    def __init__(self, policy: RegimePolicy | None = None) -> None:
        self.policy = policy or RegimePolicy()

    def assess(
        self,
        analysis: Mapping[str, Any],
        *,
        operational_state: Mapping[str, Any] | None = None,
    ) -> MarketRegimeContext:
        return assess_market_regime(
            analysis,
            operational_state=operational_state,
            policy=self.policy,
        )


__all__ = [
    "MarketRegime",
    "MarketRegimeContext",
    "MarketRegimeEngine",
    "MarketRegimeError",
    "RegimePolicy",
    "RegimeStatus",
    "assess_market_regime",
]
