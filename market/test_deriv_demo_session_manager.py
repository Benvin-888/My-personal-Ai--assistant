from __future__ import annotations

import pytest

from market.deriv_demo import DerivDemoConfig, DerivDemoError
from market.deriv_demo_session import DemoAuthConfiguration, DemoAuthMethod, DemoSessionStatus
from market.deriv_demo_session_manager import DemoSessionLifecycle, DerivDemoSessionManager


class FakeTransport:
    def __init__(self, response=None, url="wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"):
        self.response = response or {"msg_type": "balance", "balance": {"currency": "USD"}}
        self.url = url
        self.calls = 0

    def get_authenticated_websocket_url(self, config):
        self.calls += 1
        return self.url

    def request_read_only(self, websocket_url, payload, timeout):
        self.calls += 1
        return self.response


def config(app_id="123"):
    return DerivDemoConfig("DOT123", "secret-token", app_id=app_id)


def test_connect_authenticates_and_records_safe_state():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    result = manager.connect()
    assert result.status is DemoSessionStatus.AUTHENTICATED
    assert manager.state.lifecycle is DemoSessionLifecycle.AUTHENTICATED
    assert manager.authenticated is True
    assert manager.safe_summary()["credentials_exposed"] is False
    assert manager.safe_summary()["trading_performed"] is False


def test_connect_is_idempotent_when_already_authenticated():
    transport = FakeTransport()
    manager = DerivDemoSessionManager(config(), transport=transport)
    first = manager.connect()
    second = manager.connect()
    assert first is second
    assert transport.calls == 2


def test_disconnect_clears_authenticated_state():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    manager.connect()
    state = manager.disconnect()
    assert state.lifecycle is DemoSessionLifecycle.DISCONNECTED
    assert manager.authenticated is False
    assert state.demo_scope is False


def test_mark_expired_requires_reconnect():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    manager.connect()
    state = manager.mark_expired()
    assert state.lifecycle is DemoSessionLifecycle.EXPIRED
    assert manager.authenticated is False
    with pytest.raises(DerivDemoError):
        manager.require_authenticated()


def test_reconnect_increments_counter_and_authenticates():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    manager.connect()
    result = manager.reconnect()
    assert result.authenticated
    assert manager.state.lifecycle is DemoSessionLifecycle.AUTHENTICATED
    assert manager.state.reconnect_count == 1


def test_reconnect_after_expiry_increments_counter():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    manager.connect()
    manager.mark_expired()
    manager.reconnect()
    assert manager.state.reconnect_count == 1


def test_failed_authentication_does_not_become_connected():
    manager = DerivDemoSessionManager(
        config(), transport=FakeTransport(response={"msg_type": "error", "error": {"message": "bad"}})
    )
    result = manager.connect()
    assert result.status is DemoSessionStatus.FAILED
    assert manager.state.lifecycle is DemoSessionLifecycle.FAILED
    assert manager.authenticated is False


def test_real_endpoint_is_rejected():
    manager = DerivDemoSessionManager(
        config(), transport=FakeTransport(url="wss://api.derivws.com/trading/v1/options/ws/real?otp=test")
    )
    result = manager.connect()
    assert result.status is DemoSessionStatus.REJECTED
    assert manager.state.lifecycle is DemoSessionLifecycle.FAILED


def test_non_demo_endpoint_is_rejected():
    manager = DerivDemoSessionManager(
        config(), transport=FakeTransport(url="wss://api.derivws.com/trading/v1/options/ws/public")
    )
    result = manager.connect()
    assert result.status is DemoSessionStatus.REJECTED


def test_pat_requires_app_id():
    with pytest.raises(DerivDemoError):
        DemoAuthConfiguration(DemoAuthMethod.PAT, None)


def test_oauth_configuration_does_not_require_app_id():
    auth = DemoAuthConfiguration(DemoAuthMethod.OAUTH)
    manager = DerivDemoSessionManager(config(app_id=None), auth=auth, transport=FakeTransport())
    result = manager.connect()
    assert result.authenticated
    assert result.auth_method is DemoAuthMethod.OAUTH


def test_read_only_session_has_no_trading_authority():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    result = manager.connect()
    assert result.trading_performed is False
    assert result.live_execution is False
    assert result.credentials_exposed is False


def test_require_authenticated_passes_after_connect():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    manager.connect()
    manager.require_authenticated()


def test_last_result_is_retained():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    result = manager.connect()
    assert manager.last_result == result


def test_safe_summary_contains_no_secret_fields():
    manager = DerivDemoSessionManager(config(), transport=FakeTransport())
    manager.connect()
    summary = manager.safe_summary()
    assert "authorization_token" not in summary
    assert "websocket_url" not in summary
    assert summary["credentials_exposed"] is False
