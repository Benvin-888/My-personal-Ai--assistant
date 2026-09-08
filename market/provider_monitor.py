"""APEX Phase 2.6.9 - continuous provider health monitoring.

This module provides a small, deterministic lifecycle wrapper around the
provider health capabilities already exposed by the unified market service.
It observes providers; it does not select providers, fetch trading data,
generate signals, manage accounts, or execute trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time
from typing import Any, Callable, Mapping

from .provider_registry import ProviderRegistry, ProviderRegistryError
from .reliability import ProviderReliabilityMonitor


class ProviderMonitorError(ValueError):
    """Raised when provider monitor configuration or lifecycle is invalid."""


@dataclass(frozen=True)
class ProviderMonitorPolicy:
    """Configuration for periodic provider health observation."""

    interval_seconds: float = 30.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.interval_seconds, bool)
            or not isinstance(self.interval_seconds, (int, float))
            or self.interval_seconds <= 0
        ):
            raise ProviderMonitorError("interval_seconds must be a positive number")


@dataclass(frozen=True)
class ProviderHealthObservation:
    """One point-in-time provider health observation."""

    provider: str
    success: bool
    status: str
    checked_at: str
    latency_ms: float | None
    result: Mapping[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "success": self.success,
            "status": self.status,
            "checked_at": self.checked_at,
            "latency_ms": self.latency_ms,
            "result": dict(self.result) if isinstance(self.result, Mapping) else self.result,
            "error": self.error,
        }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ProviderMonitorError("timestamp must be timezone-aware")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ProviderHealthMonitor:
    """Continuously observes health-capable providers.

    ``run_once`` is the deterministic/testing-friendly primitive. ``start``
    adds a daemon background loop for runtime monitoring; callers retain
    explicit lifecycle control through ``stop``.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        reliability_monitor: ProviderReliabilityMonitor | None = None,
        *,
        policy: ProviderMonitorPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        on_observation: Callable[[ProviderHealthObservation], None] | None = None,
    ) -> None:
        if not isinstance(registry, ProviderRegistry):
            raise ProviderMonitorError("registry must be a ProviderRegistry")
        self.registry = registry
        self.reliability_monitor = reliability_monitor or ProviderReliabilityMonitor()
        self.policy = policy or ProviderMonitorPolicy()
        self._clock = clock or _utc_now
        self._sleep = sleeper or time.sleep
        self._on_observation = on_observation
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_observations: dict[str, ProviderHealthObservation] = {}

    def _health_capable(self) -> tuple[Any, ...]:
        return self.registry.find_capable("health")

    def run_once(self) -> tuple[ProviderHealthObservation, ...]:
        """Perform one health check for every currently health-capable provider."""
        observations: list[ProviderHealthObservation] = []
        for adapter in self._health_capable():
            checked_at = self._clock()
            started = time.monotonic()
            checker = getattr(adapter.provider, "health_check", None)
            if not callable(checker):
                observation = ProviderHealthObservation(
                    provider=adapter.name,
                    success=False,
                    status="UNAVAILABLE",
                    checked_at=_iso(checked_at),
                    latency_ms=None,
                    error=f"Provider '{adapter.name}' does not expose health_check().",
                )
            else:
                try:
                    result = checker()
                    success = isinstance(result, Mapping) and result.get("success") is True
                    status = str(result.get("status", "HEALTHY" if success else "UNHEALTHY")) if isinstance(result, Mapping) else ("HEALTHY" if success else "UNHEALTHY")
                    observation = ProviderHealthObservation(
                        provider=adapter.name,
                        success=success,
                        status=status,
                        checked_at=_iso(checked_at),
                        latency_ms=(time.monotonic() - started) * 1000,
                        result=result if isinstance(result, Mapping) else None,
                        error=None if success else (str(result.get("error")) if isinstance(result, Mapping) and result.get("error") else "health check failed"),
                    )
                except Exception as exc:
                    observation = ProviderHealthObservation(
                        provider=adapter.name,
                        success=False,
                        status="UNHEALTHY",
                        checked_at=_iso(checked_at),
                        latency_ms=(time.monotonic() - started) * 1000,
                        error=str(exc),
                    )

            self.reliability_monitor.record_check(
                adapter.name,
                success=observation.success,
                checked_at=checked_at,
                latency_ms=observation.latency_ms,
            )
            with self._lock:
                self._last_observations[adapter.name] = observation
            observations.append(observation)
            if self._on_observation is not None:
                try:
                    self._on_observation(observation)
                except Exception:
                    # Monitoring callbacks are observers only; they must never
                    # stop provider monitoring or alter the recorded observation.
                    pass
        return tuple(observations)

    def last_observation(self, provider: str) -> dict[str, Any] | None:
        try:
            adapter = self.registry.get(provider)
        except ProviderRegistryError:
            return None
        with self._lock:
            observation = self._last_observations.get(adapter.name)
        return observation.to_dict() if observation else None

    def last_observations(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            observations = tuple(self._last_observations.values())
        return tuple(item.to_dict() for item in sorted(observations, key=lambda x: x.provider.casefold()))

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def _loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                self.run_once()
                self._stop_event.wait(self.policy.interval_seconds)
        finally:
            with self._lock:
                self._running = False
                self._thread = None

    def start(self) -> None:
        with self._lock:
            if self._running:
                raise ProviderMonitorError("provider health monitor is already running")
            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._loop,
                name="apex-provider-health-monitor",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0
        ):
            raise ProviderMonitorError("timeout must be a non-negative number or None")
        with self._lock:
            thread = self._thread
            self._stop_event.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
        with self._lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._running = False
                self._thread = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "interval_seconds": float(self.policy.interval_seconds),
                "health_capable_providers": tuple(adapter.name for adapter in self._health_capable()),
                "last_observations": self.last_observations(),
            }


__all__ = [
    "ProviderHealthMonitor",
    "ProviderHealthObservation",
    "ProviderMonitorError",
    "ProviderMonitorPolicy",
]
