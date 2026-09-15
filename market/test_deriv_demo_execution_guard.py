import pytest

from market.deriv_demo_execution_guard import (
    DemoAdmissionStatus,
    DemoExecutionAdmissionError,
    DemoExecutionAdmissionGuard,
    require_demo_execution_admission,
)
from market.execution import ExecutionMode, ExecutionRequest


class FakeSessionManager:
    def __init__(self, **overrides):
        self._health = {
            "status": "HEALTHY",
            "lifecycle": "AUTHENTICATED",
            "authenticated": True,
            "demo_scope": True,
            "authenticated_read_only": True,
            "credentials_exposed": False,
            "trading_performed": False,
            "live_execution": False,
            "account_id": "demo-account",
            "auth_method": "PAT",
            "reconnect_count": 0,
        }
        self._health.update(overrides)
        self.calls = 0

    def health(self):
        self.calls += 1
        return dict(self._health)


def request(mode=ExecutionMode.DEMO):
    # Bypass constructing a real TradePlan; the guard only needs the request mode/id.
    request_obj = object.__new__(ExecutionRequest)
    object.__setattr__(request_obj, "request_id", "req-33")
    object.__setattr__(request_obj, "mode", mode)
    return request_obj


def test_healthy_demo_session_is_admitted():
    manager = FakeSessionManager()
    result = DemoExecutionAdmissionGuard(manager).check(request())
    assert result.status is DemoAdmissionStatus.ADMITTED
    assert result.admitted is True
    assert result.execution_authorized is False
    assert result.live_execution is False


def test_guard_reads_health_once_and_does_not_execute_network_calls():
    manager = FakeSessionManager()
    DemoExecutionAdmissionGuard(manager).check(request())
    assert manager.calls == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "RECONNECT_REQUIRED"),
        ("lifecycle", "EXPIRED"),
        ("authenticated", False),
        ("demo_scope", False),
        ("authenticated_read_only", False),
        ("credentials_exposed", True),
        ("trading_performed", True),
        ("live_execution", True),
    ],
)
def test_unsafe_session_is_rejected(field, value):
    result = DemoExecutionAdmissionGuard(FakeSessionManager(**{field: value})).check(request())
    assert result.status is DemoAdmissionStatus.REJECTED
    assert result.admitted is False
    assert result.execution_authorized is False
    assert result.reasons


def test_non_demo_request_is_rejected_without_health_check():
    manager = FakeSessionManager()
    result = DemoExecutionAdmissionGuard(manager).check(request(ExecutionMode.LIVE))
    assert result.status is DemoAdmissionStatus.REJECTED
    assert manager.calls == 0
    assert "DEMO" in result.reasons[0]


def test_invalid_request_is_rejected_as_invalid_input():
    manager = FakeSessionManager()
    result = DemoExecutionAdmissionGuard(manager).check("not-a-request")
    assert result.status is DemoAdmissionStatus.INVALID_INPUT
    assert result.execution_authorized is False


def test_missing_health_method_rejected_at_construction():
    with pytest.raises(DemoExecutionAdmissionError):
        DemoExecutionAdmissionGuard(object())


def test_health_failure_is_rejected_without_exposing_details_as_secrets():
    class Broken:
        def health(self):
            raise RuntimeError("health unavailable")

    result = DemoExecutionAdmissionGuard(Broken()).check(request())
    assert result.status is DemoAdmissionStatus.REJECTED
    assert result.execution_authorized is False
    assert "health check failed" in result.reasons[0]


def test_result_to_dict_has_no_execution_authority():
    result = DemoExecutionAdmissionGuard(FakeSessionManager()).check(request())
    payload = result.to_dict()
    assert payload["admitted"] is True
    assert payload["execution_authorized"] is False
    assert payload["live_execution"] is False
    assert payload["credentials_exposed"] is False


def test_functional_wrapper_matches_guard():
    manager = FakeSessionManager()
    result = require_demo_execution_admission(request(), manager)
    assert result.status is DemoAdmissionStatus.ADMITTED


def test_health_snapshot_is_copied():
    manager = FakeSessionManager()
    result = DemoExecutionAdmissionGuard(manager).check(request())
    result.health["status"] = "MUTATED"
    assert manager.health()["status"] == "HEALTHY"
