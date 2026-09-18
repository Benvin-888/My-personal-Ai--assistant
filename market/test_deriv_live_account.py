import pytest

from market.deriv_live_account import (
    DerivLiveAccountConfig,
    DerivLiveAccountConnectivity,
    DerivLiveAccountError,
    REAL_WS_PREFIX,
)


class FakeRest:
    def __init__(self, url=None):
        self.url = url or f"{REAL_WS_PREFIX}?otp=test"
        self.calls = []

    def post_json(self, url, headers, timeout):
        self.calls.append((url, dict(headers), timeout))
        return {"data": {"url": self.url}}


class FakeWS:
    def __init__(self, response=None):
        self.response = response or {"msg_type": "balance", "balance": {"currency": "USD", "balance": 100, "loginid": "REAL123"}}
        self.calls = []

    def request_balance(self, websocket_url, timeout):
        self.calls.append((websocket_url, timeout))
        return self.response


def config():
    return DerivLiveAccountConfig(
        account_id="REAL123",
        app_id="12345",
        authorization_token="secret",
    )


def test_environment_configuration_reads_expected_names_without_summary_secrets():
    c = DerivLiveAccountConfig.from_environment({
        "DERIV_REAL_ACCOUNT_ID": "REAL123",
        "DERIV_APP_ID": "12345",
        "DERIV_PAT": "secret",
    })
    summary = c.safe_summary()
    assert summary["account_id_configured"] is True
    assert summary["app_id_configured"] is True
    assert summary["authorization_token_configured"] is True
    assert "secret" not in str(summary)
    assert summary["credentials_exposed"] is False


def test_missing_required_configuration_rejected():
    with pytest.raises(DerivLiveAccountError):
        DerivLiveAccountConfig("", "app", "token")


def test_rest_base_must_use_https():
    with pytest.raises(DerivLiveAccountError):
        DerivLiveAccountConfig("a", "b", "c", rest_base_url="http://example.com")


def test_get_authenticated_url_requires_real_endpoint():
    rest = FakeRest(url="wss://api.derivws.com/trading/v1/options/ws/demo?otp=test")
    client = DerivLiveAccountConnectivity(rest_transport=rest, websocket_transport=FakeWS())
    with pytest.raises(DerivLiveAccountError, match="real endpoint"):
        client.get_authenticated_websocket_url(config())


def test_get_authenticated_url_uses_pat_headers_without_exposing_token():
    rest = FakeRest()
    client = DerivLiveAccountConnectivity(rest_transport=rest, websocket_transport=FakeWS())
    url = client.get_authenticated_websocket_url(config())
    assert url.startswith(REAL_WS_PREFIX + "?")
    headers = rest.calls[0][1]
    assert headers["Deriv-App-ID"] == "12345"
    assert headers["Authorization"] == "Bearer secret"


def test_successful_real_read_only_verification():
    rest = FakeRest()
    ws = FakeWS()
    result = DerivLiveAccountConnectivity(rest_transport=rest, websocket_transport=ws).verify_read_only(config())
    assert result.ready_for_read_only is True
    assert result.connected is True
    assert result.real_endpoint_verified is True
    assert result.authenticated is True
    assert result.balance_verified is True
    assert result.account_id == "REAL123"
    assert result.currency == "USD"
    assert result.trading_performed is False
    assert result.live_execution is False
    assert result.trading_authorized is False
    assert result.credentials_exposed is False


def test_read_only_verification_rejects_broker_error():
    rest = FakeRest()
    ws = FakeWS({"msg_type": "error", "error": {"message": "unauthorized"}})
    result = DerivLiveAccountConnectivity(rest_transport=rest, websocket_transport=ws).verify_read_only(config())
    assert result.ready_for_read_only is False
    assert result.authenticated is False
    assert result.balance_verified is False
    assert result.trading_performed is False


def test_read_only_verification_requires_balance_object():
    rest = FakeRest()
    ws = FakeWS({"msg_type": "balance"})
    result = DerivLiveAccountConnectivity(rest_transport=rest, websocket_transport=ws).verify_read_only(config())
    assert result.connected is True
    assert result.authenticated is False
    assert result.balance_verified is False


def test_read_only_verification_requires_balance_message_type():
    rest = FakeRest()
    ws = FakeWS({"msg_type": "authorize", "balance": {"currency": "USD", "balance": 100, "loginid": "REAL123"}})
    result = DerivLiveAccountConnectivity(rest_transport=rest, websocket_transport=ws).verify_read_only(config())
    assert result.authenticated is False
    assert result.balance_verified is False


def test_read_only_verification_requires_numeric_nonnegative_balance_and_identity():
    rest = FakeRest()
    for payload in (
        {"msg_type": "balance", "balance": {"currency": "USD", "balance": "100", "loginid": "REAL123"}},
        {"msg_type": "balance", "balance": {"currency": "USD", "balance": -1, "loginid": "REAL123"}},
        {"msg_type": "balance", "balance": {"currency": "USD", "balance": 100, "loginid": "OTHER"}},
        {"msg_type": "balance", "balance": {"currency": "", "balance": 100, "loginid": "REAL123"}},
    ):
        result = DerivLiveAccountConnectivity(rest_transport=rest, websocket_transport=FakeWS(payload)).verify_read_only(config())
        assert result.authenticated is False
        assert result.balance_verified is False


def test_otp_failure_is_reported_without_secret_exposure():
    class BrokenRest:
        def post_json(self, url, headers, timeout):
            raise DerivLiveAccountError("OTP failed")

    result = DerivLiveAccountConnectivity(rest_transport=BrokenRest(), websocket_transport=FakeWS()).verify_read_only(config())
    assert result.connected is False
    assert result.network_access_performed is True
    assert "secret" not in result.message


def test_safe_summary_never_reports_credentials():
    result = DerivLiveAccountConnectivity(rest_transport=FakeRest(), websocket_transport=FakeWS()).verify_read_only(config())
    summary = result.safe_summary()
    assert summary["credentials_exposed"] is False
    assert "secret" not in str(summary)


def test_websocket_transport_receives_only_real_url():
    rest = FakeRest()
    ws = FakeWS()
    DerivLiveAccountConnectivity(rest_transport=rest, websocket_transport=ws).verify_read_only(config())
    assert ws.calls[0][0].startswith(REAL_WS_PREFIX + "?")


def test_real_account_connectivity_never_reports_execution_authority():
    result = DerivLiveAccountConnectivity(rest_transport=FakeRest(), websocket_transport=FakeWS()).verify_read_only(config())
    assert result.trading_authorized is False
    assert result.trading_performed is False
    assert result.live_execution is False


def test_environment_connectivity_is_read_only_with_fakes():
    rest = FakeRest()
    ws = FakeWS()
    client = DerivLiveAccountConnectivity(rest_transport=rest, websocket_transport=ws)
    result = client.connect_from_environment({
        "DERIV_REAL_ACCOUNT_ID": "REAL123",
        "DERIV_APP_ID": "12345",
        "DERIV_PAT": "secret",
    })
    assert result.ready_for_read_only is True


def test_invalid_ws_url_is_rejected():
    rest = FakeRest(url="wss://evil.example/trading/v1/options/ws/real?otp=test")
    client = DerivLiveAccountConnectivity(rest_transport=rest, websocket_transport=FakeWS())
    with pytest.raises(DerivLiveAccountError):
        client.get_authenticated_websocket_url(config())


def test_missing_ws_query_is_rejected():
    rest = FakeRest(url=REAL_WS_PREFIX)
    client = DerivLiveAccountConnectivity(rest_transport=rest, websocket_transport=FakeWS())
    with pytest.raises(DerivLiveAccountError):
        client.get_authenticated_websocket_url(config())


def test_timeout_must_be_positive():
    with pytest.raises(DerivLiveAccountError):
        DerivLiveAccountConfig("a", "b", "c", timeout_seconds=0)


def test_boolean_timeout_is_rejected():
    with pytest.raises(DerivLiveAccountError):
        DerivLiveAccountConfig("a", "b", "c", timeout_seconds=True)
