from datetime import datetime, timezone

import pytest

from market.execution import ExecutionMode, ExecutionRequest
from market.live_readiness import (
    LiveReadinessError,
    LiveReadinessGate,
    LiveReadinessProfile,
    LiveReadinessStatus,
    evaluate_live_readiness,
)


def request(mode=ExecutionMode.LIVE):
    obj = object.__new__(ExecutionRequest)
    object.__setattr__(obj, "request_id", "req-34")
    object.__setattr__(obj, "mode", mode)
    return obj


def ready_profile(**overrides):
    data = dict(
        live_enabled=True,
        live_endpoint="wss://real.example/ws",
        demo_endpoint="wss://demo.example/ws",
        credential_provider_configured=True,
        kill_switch_enabled=True,
        risk_limits_configured=True,
        idempotency_enabled=True,
        reconciliation_enabled=True,
        audit_logging_enabled=True,
        monitoring_enabled=True,
        recovery_enabled=True,
        demo_safety_preserved=True,
        maximum_risk_fraction=0.005,
        maximum_total_risk_fraction=0.01,
    )
    data.update(overrides)
    return LiveReadinessProfile(**data)


def test_complete_live_profile_is_ready():
    result = LiveReadinessGate(ready_profile()).evaluate(request())
    assert result.status is LiveReadinessStatus.READY
    assert result.ready is True
    assert result.execution_authorized is False
    assert result.broker_access is False
    assert result.live_execution is False


def test_readiness_never_performs_network_or_execution():
    result = LiveReadinessGate(ready_profile()).evaluate(request())
    assert result.evidence["network_access_performed"] is False
    assert result.evidence["credential_values_read"] is False
    assert result.evidence["execution_performed"] is False


def test_non_live_request_is_not_ready():
    result = LiveReadinessGate(ready_profile()).evaluate(request(ExecutionMode.DEMO))
    assert result.status is LiveReadinessStatus.NOT_READY
    assert "execution_mode" in result.failed_checks


@pytest.mark.parametrize(
    "field",
    [
        "live_enabled",
        "credential_provider_configured",
        "kill_switch_enabled",
        "risk_limits_configured",
        "idempotency_enabled",
        "reconciliation_enabled",
        "audit_logging_enabled",
        "monitoring_enabled",
        "recovery_enabled",
        "demo_safety_preserved",
    ],
)
def test_missing_safety_control_blocks_readiness(field):
    result = LiveReadinessGate(ready_profile(**{field: False})).evaluate(request())
    assert result.status is LiveReadinessStatus.NOT_READY
    assert {
        "live_enabled": "explicit_live_enablement",
        "credential_provider_configured": "credential_provider",
        "kill_switch_enabled": "kill_switch",
        "risk_limits_configured": "risk_limits",
        "idempotency_enabled": "idempotency",
        "reconciliation_enabled": "reconciliation",
        "audit_logging_enabled": "audit_logging",
        "monitoring_enabled": "monitoring",
        "recovery_enabled": "recovery",
        "demo_safety_preserved": "demo_safety",
    }[field] in result.failed_checks


def test_missing_live_endpoint_blocks_readiness():
    result = LiveReadinessGate(ready_profile(live_endpoint=None)).evaluate(request())
    assert result.status is LiveReadinessStatus.NOT_READY
    assert "real_endpoint_separation" in result.failed_checks


def test_missing_demo_endpoint_blocks_endpoint_separation():
    result = LiveReadinessGate(ready_profile(demo_endpoint=None)).evaluate(request())
    assert result.status is LiveReadinessStatus.NOT_READY
    assert "real_endpoint_separation" in result.failed_checks


def test_identical_endpoints_are_rejected():
    result = LiveReadinessGate(
        ready_profile(demo_endpoint="wss://real.example/ws")
    ).evaluate(request())
    assert result.status is LiveReadinessStatus.NOT_READY
    assert "real_endpoint_separation" in result.failed_checks


def test_missing_explicit_risk_fractions_blocks_readiness():
    result = LiveReadinessGate(
        ready_profile(maximum_risk_fraction=None, maximum_total_risk_fraction=None)
    ).evaluate(request())
    assert result.status is LiveReadinessStatus.NOT_READY
    assert "risk_limits" in result.failed_checks


def test_total_risk_cannot_be_below_single_trade_risk():
    result = LiveReadinessGate(
        ready_profile(maximum_risk_fraction=0.02, maximum_total_risk_fraction=0.01)
    ).evaluate(request())
    assert result.status is LiveReadinessStatus.NOT_READY
    assert "risk_limits" in result.failed_checks


def test_profile_rejects_invalid_risk_fraction():
    with pytest.raises(LiveReadinessError):
        LiveReadinessProfile(maximum_risk_fraction=0)
    with pytest.raises(LiveReadinessError):
        LiveReadinessProfile(maximum_total_risk_fraction=1.1)


def test_profile_rejects_boolean_risk_fraction():
    with pytest.raises(LiveReadinessError):
        LiveReadinessProfile(maximum_risk_fraction=True)


def test_result_to_dict_contains_no_authority_or_credentials():
    result = LiveReadinessGate(ready_profile()).evaluate(request())
    payload = result.to_dict()
    assert payload["ready"] is True
    assert payload["execution_authorized"] is False
    assert payload["broker_access"] is False
    assert payload["live_execution"] is False
    assert payload["credentials_exposed"] is False
    assert "credential_values_read" in payload["evidence"]


def test_functional_wrapper_matches_gate():
    profile = ready_profile()
    a = LiveReadinessGate(profile).evaluate(request())
    b = evaluate_live_readiness(request(), profile)
    assert a.status is b.status
    assert a.failed_checks == b.failed_checks


def test_invalid_request_is_invalid_input():
    result = LiveReadinessGate(ready_profile()).evaluate("not-a-request")
    assert result.status is LiveReadinessStatus.INVALID_INPUT
    assert result.execution_authorized is False


def test_ready_profile_is_declarative_and_does_not_expose_endpoint_value():
    payload = ready_profile().to_dict()
    assert "live_endpoint" not in payload
    assert "demo_endpoint" not in payload
    assert payload["live_endpoint_configured"] is True
    assert payload["demo_endpoint_configured"] is True


def test_failed_checks_are_deduplicated():
    result = LiveReadinessGate(
        ready_profile(risk_limits_configured=False, maximum_risk_fraction=None)
    ).evaluate(request())
    assert result.failed_checks.count("risk_limits") == 1
