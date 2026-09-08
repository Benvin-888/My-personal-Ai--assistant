from datetime import datetime, timezone

from market.unified import UnifiedMarketDataService
from market.operational_state import OperationalStatePolicy


BASE = datetime(2026, 9, 9, 19, 0, tzinfo=timezone.utc)


def fresh():
    return {"status": "FRESH", "age_seconds": 1.0}


def good_quality():
    return {"quality": "GOOD", "score": 98.0}


def healthy():
    return {"success": True, "status": "HEALTHY"}


def test_unified_service_exposes_operational_state():
    service = UnifiedMarketDataService.with_defaults(include_yahoo=False, include_deriv=True)
    result = service.assess_operational_state(
        provider="deriv", pair="eurusd", assessed_at=BASE,
        freshness=fresh(), data_quality=good_quality(), provider_health=healthy(),
    )
    assert result["provider"] == "Deriv"
    assert result["pair"] == "EURUSD"
    assert result["status"] == "HEALTHY"
    assert result["analysis_usable"] is True


def test_unified_state_uses_accumulated_reliability_snapshot():
    service = UnifiedMarketDataService.with_defaults(include_yahoo=False, include_deriv=True)
    for _ in range(3):
        service.reliability_monitor.record_check("Deriv", success=True, checked_at=BASE, latency_ms=10)
    service.reliability_monitor.record_check("Deriv", success=False, checked_at=BASE, latency_ms=20)
    result = service.assess_operational_state(
        provider="Deriv", assessed_at=BASE,
        freshness=fresh(), data_quality=good_quality(), provider_health=healthy(),
    )
    assert result["reliability_total_checks"] == 4
    assert result["reliability_success_rate"] == 0.75
    assert result["status"] == "DEGRADED"
    assert result["analysis_usable"] is False


def test_unified_state_accepts_explicit_reliability_without_mutating_monitor():
    service = UnifiedMarketDataService.with_defaults(include_yahoo=False, include_deriv=True)
    result = service.assess_operational_state(
        provider="Deriv", assessed_at=BASE,
        freshness=fresh(), data_quality=good_quality(), provider_health=healthy(),
        reliability={"success_rate": 1.0, "consecutive_failures": 0, "total_checks": 20},
    )
    assert result["status"] == "HEALTHY"
    assert service.reliability_monitor.snapshot("Deriv").total_checks == 0


def test_unified_operational_policy_is_forwarded():
    service = UnifiedMarketDataService.with_defaults(include_yahoo=False, include_deriv=True)
    result = service.assess_operational_state(
        provider="Deriv", assessed_at=BASE,
        freshness={"status": "STALE", "age_seconds": 10},
        data_quality=good_quality(), provider_health=healthy(),
        policy=OperationalStatePolicy(allow_stale_for_analysis=True),
    )
    assert result["status"] == "DEGRADED"
    assert result["analysis_usable"] is False
    assert result["warnings"]
