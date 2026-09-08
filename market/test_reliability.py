from datetime import datetime, timezone, timedelta
import pytest

from market.reliability import (
    FreshnessPolicy,
    ProviderReliabilityMonitor,
    ReliabilityError,
    assess_freshness,
    assess_provider_observation,
)

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_fresh_observation_is_fresh():
    result = assess_freshness(BASE, assessed_at=BASE + timedelta(seconds=3))
    assert result.status == "FRESH"
    assert result.age_seconds == 3


def test_boundary_fresh_threshold_is_fresh():
    result = assess_freshness(BASE, assessed_at=BASE + timedelta(seconds=5))
    assert result.status == "FRESH"


def test_observation_after_fresh_threshold_is_stale():
    result = assess_freshness(BASE, assessed_at=BASE + timedelta(seconds=6))
    assert result.status == "STALE"


def test_very_stale_observation_is_explicit():
    result = assess_freshness(BASE, assessed_at=BASE + timedelta(seconds=31))
    assert result.status == "VERY_STALE"


def test_unavailable_observation_is_explicit():
    result = assess_freshness(BASE, assessed_at=BASE + timedelta(seconds=121))
    assert result.status == "UNAVAILABLE"


def test_missing_timestamp_is_unknown_not_fabricated():
    result = assess_freshness(None, assessed_at=BASE)
    assert result.status == "UNKNOWN"
    assert result.age_seconds is None


def test_future_observation_is_invalid():
    result = assess_freshness(BASE + timedelta(seconds=1), assessed_at=BASE)
    assert result.status == "INVALID"
    assert result.age_seconds == -1


def test_custom_policy_is_deterministic():
    policy = FreshnessPolicy(2, 10, 20)
    result = assess_freshness(BASE, assessed_at=BASE + timedelta(seconds=10), policy=policy)
    assert result.status == "STALE"


def test_invalid_policy_order_is_rejected():
    with pytest.raises(ReliabilityError):
        FreshnessPolicy(10, 5, 20)


def test_provider_observation_accepts_iso_timestamp():
    result = assess_provider_observation(
        {"provider": "Deriv", "timestamp_utc": "2026-01-01T00:00:00Z"},
        assessed_at=BASE + timedelta(seconds=2),
    )
    assert result["provider"] == "Deriv"
    assert result["freshness"]["status"] == "FRESH"


def test_provider_observation_requires_provider():
    with pytest.raises(ReliabilityError):
        assess_provider_observation({"timestamp_utc": "2026-01-01T00:00:00Z"}, assessed_at=BASE)


def test_invalid_observation_timestamp_is_rejected():
    with pytest.raises(ReliabilityError):
        assess_provider_observation(
            {"provider": "Deriv", "timestamp_utc": "not-a-time"}, assessed_at=BASE
        )


def test_monitor_records_success_and_failure():
    monitor = ProviderReliabilityMonitor()
    monitor.record_check("Deriv", success=True, checked_at=BASE, latency_ms=100)
    snapshot = monitor.record_check("Deriv", success=False, checked_at=BASE + timedelta(seconds=1), latency_ms=200)
    assert snapshot.total_checks == 2
    assert snapshot.successful_checks == 1
    assert snapshot.failed_checks == 1
    assert snapshot.consecutive_failures == 1
    assert snapshot.average_latency_ms == 150


def test_success_resets_consecutive_failures():
    monitor = ProviderReliabilityMonitor()
    monitor.record_check("Deriv", success=False, checked_at=BASE)
    monitor.record_check("Deriv", success=False, checked_at=BASE + timedelta(seconds=1))
    snapshot = monitor.record_check("Deriv", success=True, checked_at=BASE + timedelta(seconds=2))
    assert snapshot.consecutive_failures == 0


def test_success_rate_is_calculated():
    monitor = ProviderReliabilityMonitor()
    monitor.record_check("Deriv", success=True, checked_at=BASE)
    monitor.record_check("Deriv", success=True, checked_at=BASE + timedelta(seconds=1))
    monitor.record_check("Deriv", success=False, checked_at=BASE + timedelta(seconds=2))
    assert monitor.snapshot("Deriv").success_rate == pytest.approx(2 / 3)


def test_unknown_provider_snapshot_is_empty():
    snapshot = ProviderReliabilityMonitor().snapshot("YahooFinance")
    assert snapshot.total_checks == 0
    assert snapshot.success_rate is None


def test_snapshot_all_is_sorted():
    monitor = ProviderReliabilityMonitor()
    monitor.record_check("YahooFinance", success=True, checked_at=BASE)
    monitor.record_check("Deriv", success=True, checked_at=BASE)
    assert [s.provider for s in monitor.snapshot_all()] == ["Deriv", "YahooFinance"]


def test_negative_latency_is_rejected():
    with pytest.raises(ReliabilityError):
        ProviderReliabilityMonitor().record_check("Deriv", success=True, checked_at=BASE, latency_ms=-1)


def test_non_boolean_success_is_rejected():
    with pytest.raises(ReliabilityError):
        ProviderReliabilityMonitor().record_check("Deriv", success=1, checked_at=BASE)
