from __future__ import annotations

from market.deriv_demo import DerivContractSpec, DerivDemoConfig
from market.deriv_demo_control import DemoControlStatus, DerivDemoControlResult, DerivDemoControlSession
from market.deriv_demo_verification import DemoVerificationStatus, DerivDemoExecutionVerifier


class FakeTransport:
    def __init__(self, response=None):
        self.response = response or {
            "msg_type": "proposal_open_contract",
            "proposal_open_contract": {
                "contract_id": 12345,
                "contract_type": "CALL",
                "currency": "USD",
                "buy_price": "2.50",
                "payout": "4.50",
                "is_sold": 0,
            },
        }
        self.calls = []

    def get_authenticated_websocket_url(self, config):
        return "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"

    def request(self, websocket_url, payload, timeout):
        self.calls.append(dict(payload))
        return self.response

    def close(self):
        pass


def config():
    return DerivDemoConfig("VR123", "secret")


def contract():
    return DerivContractSpec("frxEURUSD", "CALL", 2.5, "stake", "USD", 5, "m")


def purchased():
    return DerivDemoControlResult(
        DemoControlStatus.PURCHASED,
        websocket_url_scoped_demo=True,
        proposal_id="p-1",
        ask_price=2.5,
        contract_id="12345",
    )


def session(transport=None):
    s = DerivDemoControlSession(config(), transport=transport or FakeTransport())
    s.connect()
    return s


def test_verifies_matching_open_contract():
    transport = FakeTransport()
    result = DerivDemoExecutionVerifier(session(transport)).verify(purchased(), contract())
    assert result.status is DemoVerificationStatus.VERIFIED
    assert result.verified
    assert result.contract_id == "12345"
    assert result.buy_price == 2.5
    assert result.live_execution is False
    assert transport.calls == [{"proposal_open_contract": 1, "contract_id": 12345}]


def test_rejects_non_purchased_result_without_network_call():
    transport = FakeTransport()
    result = DerivDemoExecutionVerifier(session(transport)).verify(
        DerivDemoControlResult(DemoControlStatus.PROPOSAL_VALIDATED, proposal_id="p-1", ask_price=2.5),
        contract(),
    )
    assert result.status is DemoVerificationStatus.REJECTED
    assert not transport.calls


def test_rejects_missing_session_connection():
    transport = FakeTransport()
    s = DerivDemoControlSession(config(), transport=transport)
    result = DerivDemoExecutionVerifier(s).verify(purchased(), contract())
    assert result.status is DemoVerificationStatus.REJECTED
    assert "not connected" in result.reasons[0]
    assert not transport.calls


def test_rejects_contract_id_mismatch():
    transport = FakeTransport()
    result = DerivDemoExecutionVerifier(session(transport)).verify(
        purchased(), contract(), expected_contract_id="999"
    )
    assert result.status is DemoVerificationStatus.REJECTED
    assert "contract_id" in result.reasons[0]
    assert not transport.calls


def test_rejects_broker_contract_id_mismatch():
    transport = FakeTransport({"proposal_open_contract": {"contract_id": 999, "contract_type": "CALL", "currency": "USD"}})
    result = DerivDemoExecutionVerifier(session(transport)).verify(purchased(), contract())
    assert result.status is DemoVerificationStatus.REJECTED
    assert "contract_id" in result.reasons[0]


def test_rejects_contract_type_mismatch():
    transport = FakeTransport({"proposal_open_contract": {"contract_id": 12345, "contract_type": "PUT", "currency": "USD"}})
    result = DerivDemoExecutionVerifier(session(transport)).verify(purchased(), contract())
    assert result.status is DemoVerificationStatus.REJECTED
    assert "contract_type" in result.reasons[0]


def test_rejects_currency_mismatch():
    transport = FakeTransport({"proposal_open_contract": {"contract_id": 12345, "contract_type": "CALL", "currency": "EUR"}})
    result = DerivDemoExecutionVerifier(session(transport)).verify(purchased(), contract())
    assert result.status is DemoVerificationStatus.REJECTED
    assert "currency" in result.reasons[0]


def test_handles_api_error():
    transport = FakeTransport({"error": {"message": "not authorized"}})
    result = DerivDemoExecutionVerifier(session(transport)).verify(purchased(), contract())
    assert result.status is DemoVerificationStatus.API_ERROR
    assert "not authorized" in (result.error or "")


def test_accepts_numeric_string_fields():
    transport = FakeTransport({"proposal_open_contract": {
        "contract_id": "12345", "contract_type": "CALL", "currency": "USD",
        "buy_price": "2.50", "payout": "4.50", "is_sold": False,
    }})
    result = DerivDemoExecutionVerifier(session(transport)).verify(purchased(), contract())
    assert result.status is DemoVerificationStatus.VERIFIED
    assert result.payout == 4.5
    assert result.contract_is_sold is False


def test_accepts_optional_broker_fields_absent():
    transport = FakeTransport({"proposal_open_contract": {
        "contract_id": 12345, "contract_type": "CALL", "currency": "USD"
    }})
    result = DerivDemoExecutionVerifier(session(transport)).verify(purchased(), contract())
    assert result.status is DemoVerificationStatus.VERIFIED
    assert result.buy_price is None


def test_rejects_malformed_open_contract():
    transport = FakeTransport({"proposal_open_contract": []})
    result = DerivDemoExecutionVerifier(session(transport)).verify(purchased(), contract())
    assert result.status is DemoVerificationStatus.INVALID_INPUT
    assert "object" in (result.error or "")


def test_rejects_non_numeric_price():
    transport = FakeTransport({"proposal_open_contract": {
        "contract_id": 12345, "contract_type": "CALL", "currency": "USD", "buy_price": "bad"
    }})
    result = DerivDemoExecutionVerifier(session(transport)).verify(purchased(), contract())
    assert result.status is DemoVerificationStatus.INVALID_INPUT
    assert "numeric" in (result.error or "")


def test_result_is_explicitly_demo_only():
    transport = FakeTransport()
    result = DerivDemoExecutionVerifier(session(transport)).verify(purchased(), contract())
    data = result.to_dict()
    assert data["account_mode"] == "demo"
    assert data["broker"] == "deriv"
    assert data["live_execution"] is False
