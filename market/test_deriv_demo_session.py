from __future__ import annotations

from market.deriv_demo import DerivDemoConfig
from market.deriv_demo_session import (
    DemoAuthConfiguration,
    DemoAuthMethod,
    DemoSessionStatus,
    DerivDemoAuthenticatedSession,
)


class FakeTransport:
    def __init__(self, url="wss://api.derivws.com/trading/v1/options/ws/demo?otp=one-time"):
        self.url = url
        self.payload = None
        self.timeout = None

    def get_authenticated_websocket_url(self, config):
        return self.url

    def request_read_only(self, websocket_url, payload, timeout):
        self.payload = payload
        self.timeout = timeout
        return {"msg_type": "balance", "balance": {"balance": 10000.0, "currency": "USD"}}


def config(app_id="1234"):
    return DerivDemoConfig(account_id="DOT90000000", authorization_token="secret", app_id=app_id)


def test_pat_requires_app_id():
    result = DerivDemoAuthenticatedSession(
        auth=DemoAuthConfiguration.pat(), transport=FakeTransport()
    ).validate(DerivDemoConfig(account_id="DOT90000000", authorization_token="secret"))
    assert result.status is DemoSessionStatus.REJECTED
    assert "App-ID" in result.message


def test_oauth_does_not_require_app_id():
    result = DerivDemoAuthenticatedSession(
        auth=DemoAuthConfiguration.oauth(), transport=FakeTransport()
    ).validate(DerivDemoConfig(account_id="DOT90000000", authorization_token="jwt"))
    assert result.status is DemoSessionStatus.AUTHENTICATED
    assert result.auth_method is DemoAuthMethod.OAUTH


def test_authenticated_demo_session_uses_read_only_balance():
    transport = FakeTransport()
    result = DerivDemoAuthenticatedSession(transport=transport).validate(config())
    assert result.status is DemoSessionStatus.AUTHENTICATED
    assert result.authenticated_request_verified is True
    assert result.balance_verified is True
    assert result.currency == "USD"
    assert transport.payload == {"balance": 1}


def test_no_trading_claims():
    result = DerivDemoAuthenticatedSession(transport=FakeTransport()).validate(config())
    assert result.trading_performed is False
    assert result.live_execution is False
    assert result.credentials_exposed is False


def test_real_endpoint_is_rejected():
    result = DerivDemoAuthenticatedSession(
        transport=FakeTransport("wss://api.derivws.com/trading/v1/options/ws/real?otp=x")
    ).validate(config())
    assert result.status is DemoSessionStatus.REJECTED
    assert result.live_execution is False


def test_public_endpoint_is_rejected_for_authenticated_session():
    result = DerivDemoAuthenticatedSession(
        transport=FakeTransport("wss://api.derivws.com/trading/v1/options/ws/public")
    ).validate(config())
    assert result.status is DemoSessionStatus.REJECTED


def test_wrong_response_is_not_authenticated():
    class Wrong(FakeTransport):
        def request_read_only(self, websocket_url, payload, timeout):
            return {"msg_type": "tick", "tick": {"quote": 1.0}}

    result = DerivDemoAuthenticatedSession(transport=Wrong()).validate(config())
    assert result.status is DemoSessionStatus.FAILED
    assert result.authenticated_request_verified is False


def test_api_error_is_not_authenticated():
    class Error(FakeTransport):
        def request_read_only(self, websocket_url, payload, timeout):
            return {"error": {"message": "unauthorized"}}

    result = DerivDemoAuthenticatedSession(transport=Error()).validate(config())
    assert result.status is DemoSessionStatus.FAILED
    assert result.authenticated is False


def test_result_does_not_expose_token_or_balance_amount():
    result = DerivDemoAuthenticatedSession(transport=FakeTransport()).validate(config())
    text = repr(result.to_dict())
    assert "secret" not in text
    assert "10000" not in text


def test_timeout_is_forwarded():
    transport = FakeTransport()
    session = DerivDemoAuthenticatedSession(transport=transport)
    session.validate(DerivDemoConfig(account_id="DOT90000000", authorization_token="secret", app_id="1234", timeout_seconds=7.5))
    assert transport.timeout == 7.5


def test_environment_without_credentials_is_rejected(monkeypatch):
    monkeypatch.delenv("DERIV_DEMO_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("DERIV_AUTH_TOKEN", raising=False)
    result = DerivDemoAuthenticatedSession(transport=FakeTransport()).validate_from_environment()
    assert result.status is DemoSessionStatus.REJECTED


def test_environment_pat_requires_app_id(monkeypatch):
    monkeypatch.setenv("DERIV_DEMO_ACCOUNT_ID", "DOT90000000")
    monkeypatch.setenv("DERIV_AUTH_TOKEN", "secret")
    monkeypatch.delenv("DERIV_APP_ID", raising=False)
    result = DerivDemoAuthenticatedSession(transport=FakeTransport()).validate_from_environment()
    assert result.status is DemoSessionStatus.REJECTED
    assert "App-ID" in result.message


def test_safe_dict_flags_are_constant():
    result = DerivDemoAuthenticatedSession(transport=FakeTransport()).validate(config())
    data = result.to_dict()
    assert data["credentials_exposed"] is False
    assert data["trading_performed"] is False
    assert data["live_execution"] is False
