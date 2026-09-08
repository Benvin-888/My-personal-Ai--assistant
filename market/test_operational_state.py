from datetime import datetime, timedelta, timezone

import pytest

from market.operational_state import (
    MarketOperationalStateEngine,
    OperationalStateError,
    OperationalStatePolicy,
    assess_market_operational_state,
)


BASE = datetime(2026, 9, 9, 19, 0, tzinfo=timezone.utc)


def freshness(status="FRESH", age=1.0):
    return {"status": status, "age_seconds": age}


def quality(status="GOOD", score=98.0):
    return {"quality": status, "score": score}


def health(success=True, status="HEALTHY"):
    return {"success": success, "status": status}


def reliability(rate=1.0, failures=0, total=10):
    return {"success_rate": rate, "consecutive_failures": failures, "total_checks": total}


def test_all_good_is_healthy_and_analysis_usable():
    state = assess_market_operational_state(
        provider="Deriv",
        pair="EURUSD",
        assessed_at=BASE,
        freshness=freshness(),
        data_quality=quality(),
        provider_health=health(),
        reliability=reliability(),
    )
    assert state.status == "HEALTHY"
    assert state.analysis_usable is True
    assert state.reasons == ()


def test_stale_data_is_not_analysis_usable_by_default():
    state = assess_market_operational_state(
        provider="Deriv", assessed_at=BASE, freshness=freshness("STALE", 10),
        data_quality=quality(), provider_health=health(), reliability=reliability(),
    )
    assert state.status == "UNUSABLE"
    assert state.analysis_usable is False
    assert "observation is stale" in state.reasons


def test_policy_can_explicitly_allow_stale_but_state_remains_degraded():
    state = assess_market_operational_state(
        provider="Deriv", assessed_at=BASE, freshness=freshness("STALE", 10),
        data_quality=quality(), provider_health=health(), reliability=reliability(),
        policy=OperationalStatePolicy(allow_stale_for_analysis=True),
    )
    assert state.status == "DEGRADED"
    assert state.analysis_usable is False
    assert state.warnings


def test_very_stale_is_hard_blocker():
    state = assess_market_operational_state(
        provider="Deriv", assessed_at=BASE, freshness=freshness("VERY_STALE", 90),
        data_quality=quality(), provider_health=health(), reliability=reliability(),
    )
    assert state.status == "UNUSABLE"
    assert state.analysis_usable is False


def test_invalid_quality_is_hard_blocker():
    state = assess_market_operational_state(
        provider="Yahoo Finance", assessed_at=BASE, freshness=freshness(),
        data_quality=quality("INVALID", 0), provider_health=None, reliability=reliability(),
    )
    assert state.status == "UNUSABLE"
    assert state.analysis_usable is False


def test_failed_health_is_hard_blocker():
    state = assess_market_operational_state(
        provider="Deriv", assessed_at=BASE, freshness=freshness(),
        data_quality=quality(), provider_health=health(False, "UNHEALTHY"), reliability=reliability(),
    )
    assert state.status == "UNUSABLE"
    assert state.analysis_usable is False


def test_low_reliability_is_degraded_not_silent():
    state = assess_market_operational_state(
        provider="Deriv", assessed_at=BASE, freshness=freshness(),
        data_quality=quality(), provider_health=health(), reliability=reliability(0.8, 1, 10),
    )
    assert state.status == "DEGRADED"
    assert state.analysis_usable is False
    assert "provider reliability success rate is below policy threshold" in state.reasons


def test_excessive_consecutive_failures_are_blocked():
    state = assess_market_operational_state(
        provider="Deriv", assessed_at=BASE, freshness=freshness(),
        data_quality=quality(), provider_health=health(), reliability=reliability(0.99, 3, 100),
    )
    assert state.status == "DEGRADED"
    assert state.analysis_usable is False
    assert "provider consecutive failures exceed policy threshold" in state.reasons


def test_required_components_missing_produce_unknown():
    state = assess_market_operational_state(
        provider="Deriv", assessed_at=BASE, freshness=None, data_quality=None,
        provider_health=None, reliability=None,
        policy=OperationalStatePolicy(require_health_observation=True, require_reliability_history=True),
    )
    assert state.status == "UNKNOWN"
    assert state.analysis_usable is False
    assert state.warnings


def test_optional_missing_components_are_explicitly_unknown():
    state = assess_market_operational_state(
        provider="Deriv", assessed_at=BASE, freshness=None, data_quality=None,
        provider_health=None, reliability=None,
    )
    assert state.status == "UNKNOWN"
    assert state.analysis_usable is False
    assert state.warnings


def test_serialization_is_complete_and_deterministic():
    state = assess_market_operational_state(
        provider="Deriv", pair="eurusd", assessed_at=BASE,
        freshness=freshness(), data_quality=quality(), provider_health=health(), reliability=reliability(),
    )
    data = state.to_dict()
    assert data["provider"] == "Deriv"
    assert data["pair"] == "EURUSD"
    assert data["analysis_usable"] is True
    assert data["reasons"] == []
    assert data["warnings"] == []


def test_engine_reuses_policy():
    engine = MarketOperationalStateEngine(OperationalStatePolicy(minimum_reliability_success_rate=0.9))
    state = engine.assess(
        provider="Deriv", assessed_at=BASE, freshness=freshness(), data_quality=quality(),
        provider_health=health(), reliability=reliability(0.91, 0, 10),
    )
    assert state.status == "HEALTHY"


def test_invalid_inputs_are_rejected():
    with pytest.raises(OperationalStateError):
        OperationalStatePolicy(minimum_reliability_success_rate=1.1)
    with pytest.raises(OperationalStateError):
        OperationalStatePolicy(maximum_consecutive_failures=-1)
    with pytest.raises(OperationalStateError):
        assess_market_operational_state(provider="", assessed_at=BASE)
    with pytest.raises(OperationalStateError):
        assess_market_operational_state(provider="Deriv", assessed_at=BASE, freshness={"freshness": {"status": "BAD"}})


def test_future_assessed_timestamp_is_not_manipulated():
    # This layer does not infer or rewrite timestamps; it preserves the supplied
    # freshness facts, making point-in-time replay possible when facts are bounded.
    state = assess_market_operational_state(
        provider="Deriv", assessed_at=BASE + timedelta(minutes=1),
        freshness=freshness("FRESH", 1), data_quality=quality(), provider_health=health(), reliability=reliability(),
    )
    assert state.assessed_at == "2026-09-09T19:01:00Z"
