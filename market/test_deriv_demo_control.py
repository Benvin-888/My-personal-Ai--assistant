from __future__ import annotations

from dataclasses import dataclass

from market.deriv_demo import DerivContractSpec, DerivDemoConfig
from market.deriv_demo_control import (
    DemoControlPolicy,
    DemoControlStatus,
    DerivDemoControlSession,
)


class FakeTransport:
    def __init__(self, url: str = "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"):
        self.url = url
        self.calls: list[dict] = []
        self.closed = False

    def get_authenticated_websocket_url(self, config):
        self.calls.append({"kind": "otp"})
        return self.url

    def request(self, websocket_url, payload, timeout):
        self.calls.append(dict(payload))
        if "active_symbols" in payload:
            return {"msg_type": "active_symbols", "active_symbols": [
                {"underlying_symbol": "frxEURUSD", "underlying_symbol_name": "EUR/USD",
                 "underlying_symbol_type": "forex", "market": "forex", "pip_size": 0.0001,
                 "exchange_is_open": 1, "is_trading_suspended": 0}
            ]}
        if "contracts_for" in payload:
            return {"msg_type": "contracts_for", "contracts_for": {
                "available": [{"contracts": [{"contract_type": "CALL"}, {"contract_type": "PUT"}]}]
            }}
        if "proposal" in payload:
            return {"msg_type": "proposal", "proposal": {"id": "p-1", "ask_price": "2.50", "payout": "4.50", "spot": 1.1}}
        if "buy" in payload:
            return {"msg_type": "buy", "buy": {"contract_id": 12345, "buy_price": "2.50"}}
        return {"error": {"message": "unexpected request"}}

    def close(self):
        self.closed = True


def config():
    return DerivDemoConfig("VR123", "secret")


def contract():
    return DerivContractSpec(
        underlying_symbol="frxEURUSD", contract_type="CALL", amount=2.5,
        basis="stake", currency="USD", duration=5, duration_unit="m"
    )


def test_connect_rejects_real_url():
    session = DerivDemoControlSession(config(), transport=FakeTransport("wss://api.derivws.com/trading/v1/options/ws/real?otp=x"))
    result = session.connect()
    assert result.status is DemoControlStatus.REJECTED
    assert not result.websocket_url_scoped_demo


def test_connect_demo():
    session = DerivDemoControlSession(config(), transport=FakeTransport())
    result = session.connect()
    assert result.status is DemoControlStatus.CONNECTED
    assert result.connected


def test_active_symbols_uses_new_field():
    session = DerivDemoControlSession(config(), transport=FakeTransport())
    session.connect()
    result = session.active_symbols()
    assert result.status is DemoControlStatus.SYMBOLS_VALIDATED
    assert result.symbols[0].underlying_symbol == "frxEURUSD"


def test_symbol_validation_rejects_unknown():
    session = DerivDemoControlSession(config(), transport=FakeTransport())
    session.connect()
    result = session.validate_symbol("frxGBPUSD")
    assert result.status is DemoControlStatus.REJECTED


def test_contracts_for_validates_available_types():
    session = DerivDemoControlSession(config(), transport=FakeTransport())
    session.connect()
    result = session.contracts_for("frxEURUSD")
    assert result.status is DemoControlStatus.CONTRACTS_VALIDATED
    assert result.contracts is not None
    assert result.contracts.contract_types == ("CALL", "PUT")


def test_proposal_is_demo_scoped():
    session = DerivDemoControlSession(config(), transport=FakeTransport())
    session.connect()
    result = session.proposal(contract())
    assert result.status is DemoControlStatus.PROPOSAL_VALIDATED
    assert result.proposal_id == "p-1"
    assert result.ask_price == 2.5


def test_purchase_requires_explicit_confirmation():
    session = DerivDemoControlSession(config(), transport=FakeTransport())
    session.connect()
    proposal = session.proposal(contract())
    result = session.purchase_demo(proposal, confirm_purchase=False)
    assert result.status is DemoControlStatus.REJECTED
    assert result.contract_id is None
    assert not any("buy" in call for call in session.transport.calls)


def test_confirmed_demo_purchase_returns_contract():
    session = DerivDemoControlSession(config(), transport=FakeTransport())
    session.connect()
    proposal = session.proposal(contract())
    result = session.purchase_demo(proposal, confirm_purchase=True)
    assert result.status is DemoControlStatus.PURCHASED
    assert result.contract_id == "12345"
    assert result.live_execution is False


def test_purchase_ceiling_rejects_expensive_proposal():
    session = DerivDemoControlSession(config(), policy=DemoControlPolicy(maximum_purchase_price=2.0), transport=FakeTransport())
    session.connect()
    proposal = session.proposal(contract())
    result = session.purchase_demo(proposal, confirm_purchase=True)
    assert result.status is DemoControlStatus.REJECTED


def test_close_clears_session():
    transport = FakeTransport()
    session = DerivDemoControlSession(config(), transport=transport)
    session.connect()
    session.close()
    assert session.websocket_url is None
    assert transport.closed


def test_missing_connection_rejected():
    session = DerivDemoControlSession(config(), transport=FakeTransport())
    result = session.active_symbols()
    assert result.status is DemoControlStatus.REJECTED


def test_invalid_symbol_response_is_api_error():
    class BadTransport(FakeTransport):
        def request(self, websocket_url, payload, timeout):
            if "active_symbols" in payload:
                return {"active_symbols": [{"market": "forex"}]}
            return super().request(websocket_url, payload, timeout)

    session = DerivDemoControlSession(config(), transport=BadTransport())
    session.connect()
    result = session.active_symbols()
    assert result.status is DemoControlStatus.API_ERROR
