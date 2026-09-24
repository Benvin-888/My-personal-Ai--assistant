from market.live_monitoring import *


def p(i="T-1", risk=10):
    return LivePositionObservation(i, "EURUSD", "LONG", 1, 1.1, 1.11, 5, risk)


def o(**kwargs):
    data = dict(observation_id="O-1", observed_at="2026-09-24T02:00:00Z", execution_mode="LIVE", account_scope="acct", broker="Deriv", connection_healthy=True, authenticated=True, positions=(p(),))
    data.update(kwargs)
    return LiveOperationalObservation(**data)


def test_healthy():
    a = assess_live_monitoring(LiveMonitoringCriteria(max_total_risk=20), o())
    assert a.status is MonitoringStatus.HEALTHY
    assert a.total_risk == 10
    assert a.execution_authorized is False


def test_connection_critical():
    a = assess_live_monitoring(LiveMonitoringCriteria(), o(connection_healthy=False))
    assert a.status is MonitoringStatus.CRITICAL
    assert "connection_unhealthy" in a.reasons


def test_authentication_critical():
    a = assess_live_monitoring(LiveMonitoringCriteria(), o(authenticated=False))
    assert a.status is MonitoringStatus.CRITICAL


def test_reconciliation_critical():
    a = assess_live_monitoring(LiveMonitoringCriteria(max_reconciliation_pending=0), o(reconciliation_pending=1))
    assert a.status is MonitoringStatus.CRITICAL


def test_unknown_outcome_critical():
    a = assess_live_monitoring(LiveMonitoringCriteria(max_unknown_outcomes=0), o(unknown_outcomes=1))
    assert a.status is MonitoringStatus.CRITICAL


def test_risk_limit_warning():
    a = assess_live_monitoring(LiveMonitoringCriteria(max_total_risk=5), o())
    assert a.status is MonitoringStatus.WARNING
    assert "total_risk_limit_exceeded" in a.reasons


def test_missing_risk_is_insufficient_when_required_by_limit():
    a = assess_live_monitoring(LiveMonitoringCriteria(max_total_risk=20), o(positions=(LivePositionObservation("T-1", "EURUSD", "LONG", 1, 1.1, 1.11, 5, None),)))
    assert a.status is MonitoringStatus.INSUFFICIENT_DATA
    assert "risk_data_missing" in a.reasons


def test_stale_execution_observation():
    a = assess_live_monitoring(LiveMonitoringCriteria(stale_execution_age_seconds=60), o(last_execution_age_seconds=61))
    assert a.status is MonitoringStatus.WARNING
    assert "execution_observation_stale" in a.reasons


def test_non_live_mode_warning():
    a = assess_live_monitoring(LiveMonitoringCriteria(), o(execution_mode="DEMO"))
    assert a.status is MonitoringStatus.WARNING
    assert "not_live_mode" in a.reasons


def test_position_count_limit():
    a = assess_live_monitoring(LiveMonitoringCriteria(max_position_count=1), o(positions=(p("T-1"), p("T-2"))))
    assert a.status is MonitoringStatus.WARNING


def test_invalid_duplicate_position():
    a = assess_live_monitoring(LiveMonitoringCriteria(), o(positions=(p("T-1"), p("T-1"))))
    assert a.status is MonitoringStatus.INVALID_STATE


def test_invalid_nonfinite_position():
    a = assess_live_monitoring(LiveMonitoringCriteria(), o(positions=(LivePositionObservation("T-1", "EURUSD", "LONG", float("nan"), 1.1, 1.11),)))
    assert a.status is MonitoringStatus.INVALID_STATE


def test_fingerprint_deterministic():
    c = LiveMonitoringCriteria(max_total_risk=20)
    assert assess_live_monitoring(c, o()).assessment_fingerprint == assess_live_monitoring(c, o()).assessment_fingerprint


def test_fingerprint_changes_with_observation():
    c = LiveMonitoringCriteria(max_total_risk=20)
    a = assess_live_monitoring(c, o(error_count=0))
    b = assess_live_monitoring(c, o(error_count=1))
    assert a.observation_fingerprint != b.observation_fingerprint
    assert a.assessment_fingerprint != b.assessment_fingerprint


def test_no_execution_authority():
    a = assess_live_monitoring(LiveMonitoringCriteria(), o())
    assert monitoring_assessment_is_not_execution_authorization(a)
    assert not hasattr(a, "buy")
