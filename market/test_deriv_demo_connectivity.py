from __future__ import annotations

from market.deriv_demo import DerivDemoConfig, DerivDemoError
from market.deriv_demo_connectivity import (
    DemoConnectivityStatus,
    DerivDemoConnectivityGate,
)


class FakeTransport:
    def __init__(self, url: str = "wss://api.derivws.com/trading/v1/options/ws/demo?otp=secret") -> None:
        self.url = url
        self.probed = False

    def get_authenticated_websocket_url(self, config):
        return self.url

    def probe_websocket(self, websocket_url, timeout):
        self.probed = True


def config() -> DerivDemoConfig:
    return DerivDemoConfig(account_id="DOT90000000", authorization_token="secret", app_id="1234")


def test_configuration_ready_without_network():
    gate = DerivDemoConnectivityGate(transport=FakeTransport())
    result = gate.validate_configuration(config())
    assert result.status is DemoConnectivityStatus.READY
    assert result.credentials_exposed is False
    assert result.to_dict()["credentials_exposed"] is False


def test_connects_only_to_demo_url():
    transport = FakeTransport()
    result = DerivDemoConnectivityGate(transport=transport).connect(config())
    assert result.status is DemoConnectivityStatus.CONNECTED
    assert result.websocket_demo_scoped is True
    assert result.trading_performed is False
    assert result.live_execution is False
    assert transport.probed is True


def test_real_url_rejected():
    transport = FakeTransport("wss://api.derivws.com/trading/v1/options/ws/real?otp=secret")
    result = DerivDemoConnectivityGate(transport=transport).connect(config())
    assert result.status is DemoConnectivityStatus.REJECTED
    assert result.live_endpoint_detected is True
    assert result.live_execution is False
    assert transport.probed is False


def test_non_demo_url_rejected():
    transport = FakeTransport("wss://api.derivws.com/trading/v1/options/ws/public")
    result = DerivDemoConnectivityGate(transport=transport).connect(config())
    assert result.status is DemoConnectivityStatus.REJECTED
    assert transport.probed is False


def test_result_never_contains_token():
    result = DerivDemoConnectivityGate(transport=FakeTransport()).connect(config())
    text = repr(result.to_dict())
    assert "secret" not in text


def test_environment_inspection_reports_presence_only(monkeypatch):
    monkeypatch.setenv("DERIV_DEMO_ACCOUNT_ID", "DOT90000000")
    monkeypatch.setenv("DERIV_AUTH_TOKEN", "super-secret")
    monkeypatch.setenv("DERIV_APP_ID", "1234")
    state = DerivDemoConnectivityGate.inspect_environment()
    assert state.configured is True
    assert state.account_id_present is True
    assert state.token_present is True
    assert state.app_id_present is True
    assert "super-secret" not in repr(state.safe_summary)


def test_missing_environment_is_not_configured(monkeypatch):
    monkeypatch.delenv("DERIV_DEMO_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("DERIV_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("DERIV_APP_ID", raising=False)
    state = DerivDemoConnectivityGate.inspect_environment()
    assert state.configured is False
    assert state.token_present is False


def test_connect_from_environment_without_credentials_is_safe(monkeypatch):
    monkeypatch.delenv("DERIV_DEMO_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("DERIV_AUTH_TOKEN", raising=False)
    result = DerivDemoConnectivityGate(transport=FakeTransport()).connect_from_environment()
    assert result.status is DemoConnectivityStatus.REJECTED
    assert result.live_execution is False


def test_https_required():
    try:
        DerivDemoConfig(
            account_id="DOT90000000",
            authorization_token="secret",
            rest_base_url="http://api.derivws.com",
        )
    except DerivDemoError:
        return
    raise AssertionError("insecure REST base URL was accepted")


def test_timeout_is_forwarded():
    class Recording(FakeTransport):
        def __init__(self):
            super().__init__()
            self.timeout = None
        def probe_websocket(self, websocket_url, timeout):
            self.timeout = timeout
    transport = Recording()
    gate = DerivDemoConnectivityGate(transport=transport)
    gate.connect(DerivDemoConfig(account_id="DOT90000000", authorization_token="secret", timeout_seconds=7.5))
    assert transport.timeout == 7.5


def test_failure_does_not_claim_connection():
    class Failing(FakeTransport):
        def probe_websocket(self, websocket_url, timeout):
            raise RuntimeError("network down")
    result = DerivDemoConnectivityGate(transport=Failing()).connect(config())
    assert result.status is DemoConnectivityStatus.FAILED
    assert result.connected is False
    assert result.websocket_demo_scoped is False


def test_connectivity_is_non_trading():
    result = DerivDemoConnectivityGate(transport=FakeTransport()).connect(config())
    assert result.trading_performed is False
    assert result.live_execution is False


def test_safe_summary_contains_no_secret_values():
    state = type("S", (), {})
    result = DerivDemoConnectivityGate(transport=FakeTransport()).connect(config())
    assert result.to_dict()["credentials_exposed"] is False
