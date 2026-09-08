"""APEX Phase 2.6.7 - market freshness and provider reliability monitoring.

Provider-neutral, deterministic monitoring primitives. This module does not fetch
market data, trade, generate signals, or decide which provider is correct.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


class ReliabilityError(ValueError):
    """Raised when a monitoring input is invalid."""


def _utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise ReliabilityError("timestamp must be a datetime")
    if dt.tzinfo is None:
        raise ReliabilityError("timestamp must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return _utc(dt).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class FreshnessPolicy:
    """Thresholds for classifying observation age."""

    fresh_after_seconds: float = 5.0
    stale_after_seconds: float = 30.0
    unavailable_after_seconds: float = 120.0

    def __post_init__(self) -> None:
        values = (self.fresh_after_seconds, self.stale_after_seconds, self.unavailable_after_seconds)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
            raise ReliabilityError("freshness thresholds must be numeric")
        if not (0 < self.fresh_after_seconds <= self.stale_after_seconds <= self.unavailable_after_seconds):
            raise ReliabilityError("thresholds must satisfy 0 < fresh <= stale <= unavailable")


@dataclass(frozen=True)
class FreshnessAssessment:
    status: str
    age_seconds: float | None
    observed_at: str | None
    assessed_at: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "age_seconds": self.age_seconds,
            "observed_at": self.observed_at,
            "assessed_at": self.assessed_at,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProviderReliabilitySnapshot:
    provider: str
    total_checks: int
    successful_checks: int
    failed_checks: int
    consecutive_failures: int
    last_success_at: str | None
    last_failure_at: str | None
    average_latency_ms: float | None

    @property
    def success_rate(self) -> float | None:
        if self.total_checks == 0:
            return None
        return self.successful_checks / self.total_checks

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "total_checks": self.total_checks,
            "successful_checks": self.successful_checks,
            "failed_checks": self.failed_checks,
            "consecutive_failures": self.consecutive_failures,
            "success_rate": self.success_rate,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "average_latency_ms": self.average_latency_ms,
        }


@dataclass
class _ProviderState:
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    consecutive_failures: int = 0
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    latency_sum_ms: float = 0.0
    latency_samples: int = 0


class ProviderReliabilityMonitor:
    """In-memory reliability ledger for provider health observations."""

    def __init__(self) -> None:
        self._states: dict[str, _ProviderState] = {}

    @staticmethod
    def _provider(provider: str) -> str:
        if not isinstance(provider, str) or not provider.strip():
            raise ReliabilityError("provider must be a non-empty string")
        return provider.strip()

    def record_check(
        self,
        provider: str,
        *,
        success: bool,
        checked_at: datetime,
        latency_ms: float | None = None,
    ) -> ProviderReliabilitySnapshot:
        name = self._provider(provider)
        when = _utc(checked_at)
        if not isinstance(success, bool):
            raise ReliabilityError("success must be boolean")
        if latency_ms is not None and (
            isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float)) or latency_ms < 0
        ):
            raise ReliabilityError("latency_ms must be a non-negative number")
        state = self._states.setdefault(name, _ProviderState())
        state.total_checks += 1
        if success:
            state.successful_checks += 1
            state.consecutive_failures = 0
            state.last_success_at = when
        else:
            state.failed_checks += 1
            state.consecutive_failures += 1
            state.last_failure_at = when
        if latency_ms is not None:
            state.latency_sum_ms += float(latency_ms)
            state.latency_samples += 1
        return self.snapshot(name)

    def snapshot(self, provider: str) -> ProviderReliabilitySnapshot:
        name = self._provider(provider)
        state = self._states.get(name, _ProviderState())
        return ProviderReliabilitySnapshot(
            provider=name,
            total_checks=state.total_checks,
            successful_checks=state.successful_checks,
            failed_checks=state.failed_checks,
            consecutive_failures=state.consecutive_failures,
            last_success_at=_iso(state.last_success_at) if state.last_success_at else None,
            last_failure_at=_iso(state.last_failure_at) if state.last_failure_at else None,
            average_latency_ms=(state.latency_sum_ms / state.latency_samples) if state.latency_samples else None,
        )

    def snapshot_all(self) -> tuple[ProviderReliabilitySnapshot, ...]:
        return tuple(self.snapshot(name) for name in sorted(self._states))


def assess_freshness(
    observed_at: datetime | None,
    *,
    assessed_at: datetime,
    policy: FreshnessPolicy | None = None,
) -> FreshnessAssessment:
    """Classify observation age without modifying the observation."""
    policy = policy or FreshnessPolicy()
    assessed = _utc(assessed_at)
    if observed_at is None:
        return FreshnessAssessment("UNKNOWN", None, None, _iso(assessed), "observation timestamp is missing")
    observed = _utc(observed_at)
    age = (assessed - observed).total_seconds()
    if age < 0:
        return FreshnessAssessment("INVALID", age, _iso(observed), _iso(assessed), "observation is from the future")
    if age <= policy.fresh_after_seconds:
        status, reason = "FRESH", "observation is within the fresh threshold"
    elif age <= policy.stale_after_seconds:
        status, reason = "STALE", "observation exceeds the fresh threshold"
    elif age <= policy.unavailable_after_seconds:
        status, reason = "VERY_STALE", "observation exceeds the stale threshold"
    else:
        status, reason = "UNAVAILABLE", "observation exceeds the unavailable threshold"
    return FreshnessAssessment(status, age, _iso(observed), _iso(assessed), reason)


def assess_provider_observation(
    observation: Mapping[str, Any],
    *,
    assessed_at: datetime,
    policy: FreshnessPolicy | None = None,
) -> dict[str, Any]:
    """Assess a normalized observation mapping by its timestamp field."""
    if not isinstance(observation, Mapping):
        raise ReliabilityError("observation must be a mapping")
    provider = observation.get("provider")
    if not isinstance(provider, str) or not provider.strip():
        raise ReliabilityError("observation provider is required")
    raw = observation.get("timestamp_utc", observation.get("observed_at"))
    parsed: datetime | None
    if raw is None:
        parsed = None
    elif isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ReliabilityError("observation timestamp is invalid") from exc
    else:
        raise ReliabilityError("observation timestamp must be datetime, ISO string, or None")
    result = assess_freshness(parsed, assessed_at=assessed_at, policy=policy)
    return {"provider": provider.strip(), "freshness": result.to_dict()}
