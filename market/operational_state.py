"""APEX Phase 2.6.10 - unified market operational state.

This module combines already-observed provider health, reliability, freshness,
and data-quality facts into one deterministic operational-state snapshot.

It does not fetch market data, select providers, generate trading signals,
calculate position size, manage accounts, or execute trades.

The central safety rule is deliberate:
    data readiness != trading permission

A state marked ``analysis_usable`` only means that the supplied market-data
observation satisfies this layer's operational-data policy. A later strategy
or execution layer must make its own independent decisions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Mapping


class OperationalStateError(ValueError):
    """Raised when operational-state inputs or policy are invalid."""


_ALLOWED_STATUSES = frozenset({"HEALTHY", "DEGRADED", "UNUSABLE", "UNKNOWN"})
_ALLOWED_FRESHNESS = frozenset({"FRESH", "STALE", "VERY_STALE", "UNAVAILABLE", "UNKNOWN", "INVALID"})
_ALLOWED_QUALITY = frozenset({"EXCELLENT", "GOOD", "FAIR", "POOR", "INVALID"})


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise OperationalStateError("timestamp must be a datetime")
    if value.tzinfo is None:
        raise OperationalStateError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OperationalStateError(f"{name} must be a non-empty string")
    return value.strip()


def _mapping(value: Any, name: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise OperationalStateError(f"{name} must be a mapping or None")
    return value


@dataclass(frozen=True)
class OperationalStatePolicy:
    """Conservative policy for classifying market-data operational readiness."""

    minimum_reliability_success_rate: float = 0.95
    maximum_consecutive_failures: int = 2
    allow_stale_for_analysis: bool = False
    allow_fair_quality_for_analysis: bool = False
    require_health_observation: bool = False
    require_reliability_history: bool = False

    def __post_init__(self) -> None:
        rate = self.minimum_reliability_success_rate
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not isfinite(float(rate)):
            raise OperationalStateError("minimum_reliability_success_rate must be finite")
        if not 0 <= float(rate) <= 1:
            raise OperationalStateError("minimum_reliability_success_rate must be between 0 and 1")
        failures = self.maximum_consecutive_failures
        if isinstance(failures, bool) or not isinstance(failures, int) or failures < 0:
            raise OperationalStateError("maximum_consecutive_failures must be a non-negative integer")
        for name in (
            "allow_stale_for_analysis",
            "allow_fair_quality_for_analysis",
            "require_health_observation",
            "require_reliability_history",
        ):
            if not isinstance(getattr(self, name), bool):
                raise OperationalStateError(f"{name} must be boolean")


@dataclass(frozen=True)
class MarketOperationalState:
    """Auditable point-in-time operational assessment."""

    provider: str
    pair: str | None
    status: str
    analysis_usable: bool
    assessed_at: str
    freshness: str
    observation_age_seconds: float | None
    data_quality: str
    data_quality_score: float | None
    provider_health: str | None
    provider_health_success: bool | None
    reliability_success_rate: float | None
    reliability_consecutive_failures: int | None
    reliability_total_checks: int | None
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "pair": self.pair,
            "status": self.status,
            "analysis_usable": self.analysis_usable,
            "assessed_at": self.assessed_at,
            "freshness": self.freshness,
            "observation_age_seconds": self.observation_age_seconds,
            "data_quality": self.data_quality,
            "data_quality_score": self.data_quality_score,
            "provider_health": self.provider_health,
            "provider_health_success": self.provider_health_success,
            "reliability_success_rate": self.reliability_success_rate,
            "reliability_consecutive_failures": self.reliability_consecutive_failures,
            "reliability_total_checks": self.reliability_total_checks,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


def _freshness_details(value: Mapping[str, Any] | None) -> tuple[str, float | None]:
    if value is None:
        return "UNKNOWN", None
    raw = value.get("freshness", value)
    if not isinstance(raw, Mapping):
        raise OperationalStateError("freshness must be a mapping when supplied")
    status = raw.get("status", "UNKNOWN")
    if status not in _ALLOWED_FRESHNESS:
        raise OperationalStateError(f"unsupported freshness status: {status!r}")
    age = raw.get("age_seconds")
    if age is not None:
        if isinstance(age, bool) or not isinstance(age, (int, float)) or not isfinite(float(age)):
            raise OperationalStateError("freshness age_seconds must be finite numeric or None")
    return str(status), float(age) if age is not None else None


def _quality_details(value: Mapping[str, Any] | None) -> tuple[str, float | None]:
    if value is None:
        return "UNKNOWN", None
    status = value.get("quality", "UNKNOWN")
    if status not in _ALLOWED_QUALITY and status != "UNKNOWN":
        raise OperationalStateError(f"unsupported data-quality status: {status!r}")
    score = value.get("score")
    if score is not None:
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not isfinite(float(score)):
            raise OperationalStateError("data-quality score must be finite numeric or None")
        if not 0 <= float(score) <= 100:
            raise OperationalStateError("data-quality score must be between 0 and 100")
    return str(status), float(score) if score is not None else None


def _health_details(value: Mapping[str, Any] | None) -> tuple[str | None, bool | None]:
    if value is None:
        return None, None
    success = value.get("success")
    if not isinstance(success, bool):
        raise OperationalStateError("provider health success must be boolean")
    status = value.get("status")
    if status is not None:
        status = _non_empty_string(status, "provider health status")
    return status, success


def _reliability_details(value: Mapping[str, Any] | None) -> tuple[float | None, int | None, int | None]:
    if value is None:
        return None, None, None
    rate = value.get("success_rate")
    if rate is not None:
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not isfinite(float(rate)):
            raise OperationalStateError("reliability success_rate must be finite numeric or None")
        if not 0 <= float(rate) <= 1:
            raise OperationalStateError("reliability success_rate must be between 0 and 1")
        rate = float(rate)
    failures = value.get("consecutive_failures")
    if failures is not None and (isinstance(failures, bool) or not isinstance(failures, int) or failures < 0):
        raise OperationalStateError("reliability consecutive_failures must be a non-negative integer or None")
    total = value.get("total_checks")
    if total is not None and (isinstance(total, bool) or not isinstance(total, int) or total < 0):
        raise OperationalStateError("reliability total_checks must be a non-negative integer or None")
    return rate, failures, total


def assess_market_operational_state(
    *,
    provider: str,
    pair: str | None = None,
    assessed_at: datetime,
    freshness: Mapping[str, Any] | None = None,
    data_quality: Mapping[str, Any] | None = None,
    provider_health: Mapping[str, Any] | None = None,
    reliability: Mapping[str, Any] | None = None,
    policy: OperationalStatePolicy | None = None,
) -> MarketOperationalState:
    """Combine previously-observed facts into one deterministic state.

    No network calls occur here. Every input is an observation supplied by a
    lower-level component, making the function suitable for live assessment and
    point-in-time replay when the inputs themselves are time-bounded.
    """
    provider_name = _non_empty_string(provider, "provider")
    pair_name = pair.strip().upper() if isinstance(pair, str) and pair.strip() else None
    assessed = _iso(assessed_at)
    policy = policy or OperationalStatePolicy()

    freshness_data = _mapping(freshness, "freshness")
    quality_data = _mapping(data_quality, "data_quality")
    health_data = _mapping(provider_health, "provider_health")
    reliability_data = _mapping(reliability, "reliability")

    freshness_status, age = _freshness_details(freshness_data)
    quality_status, quality_score = _quality_details(quality_data)
    health_status, health_success = _health_details(health_data)
    success_rate, consecutive_failures, total_checks = _reliability_details(reliability_data)

    reasons: list[str] = []
    warnings: list[str] = []

    if freshness_status in {"INVALID", "VERY_STALE", "UNAVAILABLE"}:
        reasons.append(f"freshness status is {freshness_status}")
    elif freshness_status == "STALE":
        if policy.allow_stale_for_analysis:
            warnings.append("observation is stale but policy permits analysis")
        else:
            reasons.append("observation is stale")

    if quality_status in {"INVALID", "POOR"}:
        reasons.append(f"data quality is {quality_status}")
    elif quality_status == "FAIR":
        if policy.allow_fair_quality_for_analysis:
            warnings.append("data quality is fair but policy permits analysis")
        else:
            reasons.append("data quality is fair")

    if policy.require_health_observation and health_data is None:
        warnings.append("provider health observation is required")
    elif health_success is False:
        reasons.append("latest provider health check failed")

    if policy.require_reliability_history and (reliability_data is None or total_checks == 0):
        warnings.append("provider reliability history is required")

    if success_rate is not None and success_rate < policy.minimum_reliability_success_rate:
        reasons.append("provider reliability success rate is below policy threshold")

    if consecutive_failures is not None and consecutive_failures > policy.maximum_consecutive_failures:
        reasons.append("provider consecutive failures exceed policy threshold")

    unknown_components = []
    if freshness_data is None:
        unknown_components.append("freshness")
    if quality_data is None:
        unknown_components.append("data quality")
    if health_data is None and policy.require_health_observation:
        unknown_components.append("provider health")
    if reliability_data is None and policy.require_reliability_history:
        unknown_components.append("reliability")

    if reasons:
        status = "UNUSABLE" if any(
            item in reasons
            for item in (
                "observation is stale",
                "data quality is POOR",
                "data quality is INVALID",
                "latest provider health check failed",
            )
        ) or freshness_status in {"INVALID", "VERY_STALE", "UNAVAILABLE"} or quality_status in {"INVALID", "POOR"} else "DEGRADED"
        analysis_usable = False
    elif unknown_components:
        status = "UNKNOWN"
        analysis_usable = False
        warnings.append("missing operational observations: " + ", ".join(unknown_components))
    elif freshness_status == "UNKNOWN" or quality_status == "UNKNOWN":
        status = "UNKNOWN"
        analysis_usable = False
        warnings.append("required operational evidence is incomplete")
    else:
        status = "HEALTHY"
        analysis_usable = True

    # A provider can be operationally degraded even when no hard blocker was
    # supplied. Explicit warning-level observations remain visible to callers.
    if warnings and status == "HEALTHY":
        status = "DEGRADED"
        analysis_usable = False

    return MarketOperationalState(
        provider=provider_name,
        pair=pair_name,
        status=status,
        analysis_usable=analysis_usable,
        assessed_at=assessed,
        freshness=freshness_status,
        observation_age_seconds=age,
        data_quality=quality_status,
        data_quality_score=quality_score,
        provider_health=health_status,
        provider_health_success=health_success,
        reliability_success_rate=success_rate,
        reliability_consecutive_failures=consecutive_failures,
        reliability_total_checks=total_checks,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


class MarketOperationalStateEngine:
    """Small reusable facade for deterministic operational-state assessment."""

    def __init__(self, policy: OperationalStatePolicy | None = None) -> None:
        self.policy = policy or OperationalStatePolicy()

    def assess(self, **kwargs: Any) -> MarketOperationalState:
        kwargs.setdefault("policy", self.policy)
        return assess_market_operational_state(**kwargs)


__all__ = [
    "MarketOperationalState",
    "MarketOperationalStateEngine",
    "OperationalStateError",
    "OperationalStatePolicy",
    "assess_market_operational_state",
]
