import pytest

from market.safety_shutdown import (
    SafetyAssessment,
    SafetyCriteria,
    SafetyObservation,
    SafetySeverity,
    SafetyState,
    ShutdownScope,
    assess_safety,
    rearm_after_explicit_validation,
    request_reset,
    safety_assessment_is_not_execution_authorization,
    safety_lock_is_not_execution_authorization,
    trigger_lock,
)


def _obs(**changes):
    data = dict(
        observation_id="OBS-1", observed_at="2026-09-24T20:00:00Z",
        execution_mode="LIVE", account_scope="real", broker="deriv",
        connection_healthy=True, authenticated=True,
        reconciliation_pending=0, unknown_outcomes=0, failed_outcomes=0,
        operational_error_count=0, warning_count=0,
        strategy_degraded=False, safety_state_available=True,
        risk_state_available=True, portfolio_state_available=True,
        eligibility_valid=True,
    )
    data.update(changes)
    return SafetyObservation(**data)


def test_healthy_observation_is_armed_and_admissible():
    result = assess_safety(SafetyCriteria(), _obs())
    assert result.state is SafetyState.ARMED
    assert result.execution_admission_allowed is True
    assert result.scope is None


def test_unknown_execution_outcome_triggers_account_lock():
    result = assess_safety(SafetyCriteria(), _obs(unknown_outcomes=1))
    assert result.state is SafetyState.TRIGGERED
    assert result.severity is SafetySeverity.CRITICAL
    assert result.scope is ShutdownScope.ACCOUNT
    assert "unknown_outcomes_exceeded" in result.reasons
    assert result.execution_admission_allowed is False


def test_reconciliation_backlog_is_fail_closed():
    result = assess_safety(SafetyCriteria(), _obs(reconciliation_pending=None))
    assert result.execution_admission_allowed is False
    assert "reconciliation_state_unknown" in result.reasons


def test_connection_or_authentication_failure_blocks_live_admission():
    result = assess_safety(SafetyCriteria(), _obs(connection_healthy=False, authenticated=False))
    assert result.execution_admission_allowed is False
    assert "connection_not_healthy" in result.reasons
    assert "authentication_not_verified" in result.reasons


def test_strategy_degradation_uses_configured_strategy_scope():
    result = assess_safety(SafetyCriteria(), _obs(strategy_degraded=True))
    assert result.state is SafetyState.TRIGGERED
    assert result.severity is SafetySeverity.DEGRADED
    assert result.scope is ShutdownScope.STRATEGY
    assert result.execution_admission_allowed is False


def test_warning_does_not_shutdown_when_configured_as_warning_only():
    result = assess_safety(SafetyCriteria(max_warning_count=2), _obs(warning_count=1))
    assert result.state is SafetyState.ARMED
    assert result.severity is SafetySeverity.WARNING
    assert result.execution_admission_allowed is True


def test_warning_threshold_can_block_without_being_critical():
    result = assess_safety(SafetyCriteria(max_warning_count=2), _obs(warning_count=3))
    assert result.state is SafetyState.TRIGGERED
    assert result.severity is SafetySeverity.DEGRADED
    assert result.execution_admission_allowed is False


def test_invalid_input_fails_closed():
    result = assess_safety(SafetyCriteria(), _obs(observation_id=""))
    assert result.state is SafetyState.TRIGGERED
    assert result.severity is SafetySeverity.INVALID
    assert result.scope is ShutdownScope.SYSTEM
    assert result.execution_admission_allowed is False


def test_lock_is_latched_and_cannot_authorize_execution():
    assessment = assess_safety(SafetyCriteria(), _obs(unknown_outcomes=1))
    lock = trigger_lock(assessment, "LOCK-1", "2026-09-24T20:00:01Z")
    assert lock.state is SafetyState.LOCKED
    assert lock.execution_admission_allowed is False
    assert safety_lock_is_not_execution_authorization(lock)


def test_reset_requires_locked_state_and_does_not_arm_automatically():
    assessment = assess_safety(SafetyCriteria(), _obs(unknown_outcomes=1))
    lock = trigger_lock(assessment, "LOCK-1", "2026-09-24T20:00:01Z")
    pending = request_reset(lock)
    assert pending.state is SafetyState.RESET_PENDING
    assert pending.execution_admission_allowed is False
    assert rearm_after_explicit_validation(pending, True, False) is False
    assert rearm_after_explicit_validation(pending, False, True) is False
    assert rearm_after_explicit_validation(pending, True, True) is True


def test_reset_is_not_available_from_armed_state():
    assessment = assess_safety(SafetyCriteria(), _obs())
    with pytest.raises(ValueError):
        trigger_lock(assessment, "LOCK-1", "2026-09-24T20:00:01Z")


def test_fingerprint_is_deterministic_and_changes_with_input():
    a = assess_safety(SafetyCriteria(), _obs(unknown_outcomes=1))
    b = assess_safety(SafetyCriteria(), _obs(unknown_outcomes=1))
    c = assess_safety(SafetyCriteria(), _obs(unknown_outcomes=2))
    assert a.assessment_fingerprint == b.assessment_fingerprint
    assert a.assessment_fingerprint != c.assessment_fingerprint


def test_execution_authority_is_always_false():
    result = assess_safety(SafetyCriteria(), _obs())
    assert safety_assessment_is_not_execution_authorization(result)
    assert result.execution_authorized is False
