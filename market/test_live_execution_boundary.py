from market.execution import ExecutionMode, ExecutionRequest
from market.risk import TradePlan
from market.live_execution_boundary import (
    LiveBoundaryStatus,
    LiveExecutionBoundary,
    LiveExecutionEvidence,
)
from market.live_readiness import LiveReadinessProfile


def request():
    plan = TradePlan(
        pair="EURUSD",
        interval="5m",
        timestamp_utc="2026-09-17T02:00:00Z",
        direction="LONG",
        entry_price=1.1000,
        stop_loss=1.0990,
        take_profit=1.1020,
        stop_distance=0.0010,
        target_distance=0.0020,
        reward_risk=2.0,
        quantity=1000.0,
        risk_amount=1.0,
        risk_fraction=0.005,
    )
    return ExecutionRequest(
        request_id="req-236",
        plan=plan,
        created_at_utc="2026-09-17T02:00:00Z",
        mode=ExecutionMode.LIVE,
    )


def profile(**overrides):
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


def evidence(**overrides):
    data = dict(
        authenticated_real_session=True,
        real_endpoint_verified=True,
        balance_verified=True,
        demo_scope_false=True,
        credentials_exposed_false=True,
        trading_performed_false=True,
        kill_switch_clear=True,
        reconciliation_current=True,
        audit_logging_ready=True,
        monitoring_ready=True,
        recovery_ready=True,
        explicit_live_confirmation=True,
        live_adapter_present=True,
    )
    data.update(overrides)
    return LiveExecutionEvidence(**data)


def test_complete_boundary_passes_without_authorization():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence()
    )
    assert result.status is LiveBoundaryStatus.PASSED
    assert result.passed is True
    assert result.execution_authorized is False
    assert result.broker_access is False
    assert result.order_placed is False
    assert result.live_execution is False


def test_boundary_never_performs_network_or_execution():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence()
    )
    assert result.evidence["network_access_performed"] is False
    assert result.evidence["credential_values_read"] is False
    assert result.evidence["execution_performed"] is False


def test_missing_real_authentication_blocks():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence(authenticated_real_session=False)
    )
    assert result.status is LiveBoundaryStatus.BLOCKED
    assert "evidence:authenticated_real_session" in result.failed_checks


def test_demo_scope_cannot_pass_live_boundary():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence(demo_scope_false=False)
    )
    assert result.status is LiveBoundaryStatus.BLOCKED
    assert "evidence:demo_scope_false" in result.failed_checks


def test_credential_exposure_blocks():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence(credentials_exposed_false=False)
    )
    assert result.status is LiveBoundaryStatus.BLOCKED
    assert "evidence:credentials_exposed_false" in result.failed_checks


def test_prior_trading_activity_blocks():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence(trading_performed_false=False)
    )
    assert result.status is LiveBoundaryStatus.BLOCKED
    assert "evidence:trading_performed_false" in result.failed_checks


def test_kill_switch_must_be_clear():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence(kill_switch_clear=False)
    )
    assert result.status is LiveBoundaryStatus.BLOCKED
    assert "evidence:kill_switch_clear" in result.failed_checks


def test_reconciliation_must_be_current():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence(reconciliation_current=False)
    )
    assert result.status is LiveBoundaryStatus.BLOCKED
    assert "evidence:reconciliation_current" in result.failed_checks


def test_explicit_live_confirmation_is_required():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence(explicit_live_confirmation=False)
    )
    assert result.status is LiveBoundaryStatus.BLOCKED
    assert "evidence:explicit_live_confirmation" in result.failed_checks


def test_live_adapter_presence_is_required_for_boundary_pass():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence(live_adapter_present=False)
    )
    assert result.status is LiveBoundaryStatus.BLOCKED
    assert "evidence:live_adapter_present" in result.failed_checks


def test_readiness_failure_blocks_boundary():
    result = LiveExecutionBoundary(
        readiness_profile=profile(monitoring_enabled=False)
    ).evaluate(request(), evidence=evidence())
    assert result.status is LiveBoundaryStatus.BLOCKED
    assert "readiness:monitoring" in result.failed_checks


def test_gateway_failure_blocks_boundary():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence(), total_risk_fraction=0.03
    )
    assert result.status is LiveBoundaryStatus.BLOCKED
    assert "execution_gateway" in result.failed_checks


def test_invalid_request_is_invalid_input():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        "not-a-request", evidence=evidence()
    )
    assert result.status is LiveBoundaryStatus.INVALID_INPUT
    assert result.execution_authorized is False


def test_evidence_is_required():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(request())
    assert result.status is LiveBoundaryStatus.INVALID_INPUT
    assert "live execution evidence is required" in result.failed_checks


def test_wrong_policy_mode_is_rejected_at_construction():
    from market.execution import ExecutionPolicy
    import pytest

    with pytest.raises(ValueError):
        LiveExecutionBoundary(
            readiness_profile=profile(),
            execution_policy=ExecutionPolicy(mode=ExecutionMode.DEMO),
        )


def test_result_contains_safety_flags():
    result = LiveExecutionBoundary(readiness_profile=profile()).evaluate(
        request(), evidence=evidence()
    )
    payload = result.to_dict()
    assert payload["passed"] is True
    assert payload["execution_authorized"] is False
    assert payload["broker_access"] is False
    assert payload["order_placed"] is False
    assert payload["live_execution"] is False
    assert payload["credentials_exposed"] is False


def test_failed_checks_are_deduplicated():
    result = LiveExecutionBoundary(
        readiness_profile=profile(
            risk_limits_configured=False,
            maximum_risk_fraction=None,
            maximum_total_risk_fraction=None,
        )
    ).evaluate(request(), evidence=evidence())
    assert result.failed_checks.count("readiness:risk_limits") == 1


def test_functional_wrapper():
    from market.live_execution_boundary import evaluate_live_execution_boundary

    result = evaluate_live_execution_boundary(
        request(), readiness_profile=profile(), evidence=evidence()
    )
    assert result.status is LiveBoundaryStatus.PASSED
