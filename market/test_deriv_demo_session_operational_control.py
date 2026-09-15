import pytest

from market.deriv_demo_session_manager import (
    DemoSessionLifecycle,
    DerivDemoSessionManager,
)
from market.deriv_demo import DerivDemoConfig, DerivDemoError
from market.deriv_demo_session import DemoAuthConfiguration, DemoSessionResult, DemoSessionStatus


class FakeTransport:
    def __init__(self, authenticated=True):
        self.authenticated = authenticated
        self.calls = 0

    def get_authenticated_websocket_url(self, config):
        return "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"

    def request_read_only(self, websocket_url, payload, timeout):
        self.calls += 1
        if not self.authenticated:
            return {"msg_type": "error", "error": {"message": "bad"}}
        return {"msg_type": "balance", "balance": {"currency": "USD", "balance": 100}}


def config():
    return DerivDemoConfig(
        account_id="demo-account",
        authorization_token="secret",
        app_id="12345",
    )


def test_health_is_healthy_after_authenticated_connect():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    manager.connect()
    health = manager.health()
    assert health["status"] == "HEALTHY"
    assert health["authenticated"] is True
    assert health["demo_scope"] is True
    assert health["authenticated_read_only"] is True


def test_health_does_not_perform_network_request():
    transport = FakeTransport()
    manager = DerivDemoSessionManager(config(), transport=transport)
    manager.connect()
    calls = transport.calls
    manager.health()
    assert transport.calls == calls


def test_health_reports_disconnected_state():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    health = manager.health()
    assert health["status"] == "DISCONNECTED"
    assert health["authenticated"] is False


def test_expired_state_requires_reconnect():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    manager.connect()
    manager.mark_expired()
    health = manager.health()
    assert health["status"] == "RECONNECT_REQUIRED"
    assert health["authenticated"] is False
    assert manager.reconnect_allowed is True


def test_failed_state_requires_reconnect():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport(authenticated=False))
    result = manager.connect()
    assert result.status is DemoSessionStatus.FAILED
    assert manager.health()["status"] == "RECONNECT_REQUIRED"


def test_reconnect_budget_is_bounded():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport(), max_reconnects=2)
    manager.connect()
    manager.mark_expired()
    manager.reconnect()
    manager.mark_expired()
    manager.reconnect()
    assert manager.reconnect_allowed is False
    with pytest.raises(DerivDemoError, match="maximum demo session reconnect attempts"):
        manager.reconnect()


def test_negative_reconnect_budget_rejected():
    with pytest.raises(DerivDemoError):
        DerivDemoSessionManager(config(), transport=FakeTransport(), max_reconnects=-1)


def test_boolean_reconnect_budget_rejected():
    with pytest.raises(DerivDemoError):
        DerivDemoSessionManager(config(), transport=FakeTransport(), max_reconnects=True)


def test_safe_summary_contains_operational_health_without_secrets():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    manager.connect()
    summary = manager.safe_summary()
    assert summary["health"]["status"] == "HEALTHY"
    assert summary["credentials_exposed"] is False
    assert summary["trading_performed"] is False
    assert summary["live_execution"] is False
    assert "authorization_token" not in str(summary)


def test_health_clock_age_is_deterministic():
    now = [10.0]
    manager = DerivDemoSessionManager(config(), transport=FakeTransport(), clock=lambda: now[0])
    manager.connect()
    now[0] = 15.25
    health = manager.health()
    assert health["authenticated_age_seconds"] == 5.25


def test_disconnect_clears_authenticated_health():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    manager.connect()
    manager.disconnect()
    health = manager.health()
    assert health["status"] == "DISCONNECTED"
    assert health["authenticated"] is False
    assert health["authenticated_age_seconds"] is None


def test_operational_health_has_no_trading_authority():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    manager.connect()
    health = manager.health()
    assert health["trading_performed"] is False
    assert health["live_execution"] is False
    assert health["credentials_exposed"] is False
