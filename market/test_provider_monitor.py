"""Phase 2.6.9 tests for continuous provider health monitoring."""
from datetime import datetime, timezone
import time

from market.provider_monitor import (
    ProviderHealthMonitor,
    ProviderMonitorError,
    ProviderMonitorPolicy,
)
from market.provider_registry import ProviderAdapter, ProviderCapabilities, ProviderRegistry
from market.reliability import ProviderReliabilityMonitor


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class HealthyProvider:
    def health_check(self):
        return {"success": True, "provider": "Healthy", "status": "HEALTHY"}


class FailingProvider:
    def health_check(self):
        raise RuntimeError("offline")


def registry(*items):
    return ProviderRegistry(items)


def test_policy_rejects_non_positive_interval():
    try:
        ProviderMonitorPolicy(0)
        assert False
    except ProviderMonitorError:
        pass


def test_run_once_records_success():
    monitor = ProviderReliabilityMonitor()
    svc = ProviderHealthMonitor(
        registry(ProviderAdapter("Healthy", HealthyProvider(), ProviderCapabilities(health=True))),
        monitor,
        clock=lambda: BASE,
    )
    observations = svc.run_once()
    assert len(observations) == 1
    assert observations[0].success is True
    assert observations[0].status == "HEALTHY"
    assert monitor.snapshot("Healthy").successful_checks == 1


def test_run_once_records_failure():
    monitor = ProviderReliabilityMonitor()
    svc = ProviderHealthMonitor(
        registry(ProviderAdapter("Failing", FailingProvider(), ProviderCapabilities(health=True))),
        monitor,
        clock=lambda: BASE,
    )
    observations = svc.run_once()
    assert observations[0].success is False
    assert observations[0].status == "UNHEALTHY"
    assert observations[0].error == "offline"
    assert monitor.snapshot("Failing").consecutive_failures == 1


def test_non_health_provider_is_not_polled():
    called = []

    class NeverCalled:
        def health_check(self):
            called.append(True)
            return {"success": True}

    svc = ProviderHealthMonitor(
        registry(ProviderAdapter("NoHealth", NeverCalled(), ProviderCapabilities(quote=True)))
    )
    assert svc.run_once() == ()
    assert called == []


def test_last_observation_is_normalized():
    svc = ProviderHealthMonitor(
        registry(ProviderAdapter("Healthy", HealthyProvider(), ProviderCapabilities(health=True))),
        clock=lambda: BASE,
    )
    svc.run_once()
    result = svc.last_observation("healthy")
    assert result["provider"] == "Healthy"
    assert result["checked_at"] == "2026-01-01T00:00:00Z"


def test_last_observations_are_sorted():
    class B(HealthyProvider):
        pass

    class A(HealthyProvider):
        pass

    svc = ProviderHealthMonitor(
        registry(
            ProviderAdapter("B", B(), ProviderCapabilities(health=True)),
            ProviderAdapter("A", A(), ProviderCapabilities(health=True)),
        ),
        clock=lambda: BASE,
    )
    svc.run_once()
    assert [x["provider"] for x in svc.last_observations()] == ["A", "B"]


def test_callback_cannot_break_monitoring():
    seen = []

    def callback(observation):
        seen.append(observation.provider)
        raise RuntimeError("observer bug")

    monitor = ProviderReliabilityMonitor()
    svc = ProviderHealthMonitor(
        registry(ProviderAdapter("Healthy", HealthyProvider(), ProviderCapabilities(health=True))),
        monitor,
        clock=lambda: BASE,
        on_observation=callback,
    )
    svc.run_once()
    assert seen == ["Healthy"]
    assert monitor.snapshot("Healthy").successful_checks == 1


def test_status_reports_runtime_state():
    svc = ProviderHealthMonitor(
        registry(ProviderAdapter("Healthy", HealthyProvider(), ProviderCapabilities(health=True))),
        policy=ProviderMonitorPolicy(10),
    )
    status = svc.status()
    assert status["running"] is False
    assert status["interval_seconds"] == 10.0
    assert status["health_capable_providers"] == ("Healthy",)


def test_start_runs_and_stop_is_graceful():
    monitor = ProviderReliabilityMonitor()
    svc = ProviderHealthMonitor(
        registry(ProviderAdapter("Healthy", HealthyProvider(), ProviderCapabilities(health=True))),
        monitor,
        policy=ProviderMonitorPolicy(0.02),
    )
    svc.start()
    time.sleep(0.06)
    svc.stop(timeout=1)
    assert svc.is_running() is False
    assert monitor.snapshot("Healthy").total_checks >= 1


def test_start_twice_is_rejected():
    svc = ProviderHealthMonitor(ProviderRegistry())
    svc.start()
    try:
        svc.start()
        assert False
    except ProviderMonitorError:
        pass
    finally:
        svc.stop(timeout=1)


def test_stop_timeout_validation():
    svc = ProviderHealthMonitor(ProviderRegistry())
    try:
        svc.stop(-1)
        assert False
    except ProviderMonitorError:
        pass


def test_stop_before_start_is_safe():
    svc = ProviderHealthMonitor(ProviderRegistry())
    svc.stop(timeout=0)
    assert svc.is_running() is False
