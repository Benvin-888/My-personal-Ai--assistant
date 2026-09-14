from __future__ import annotations
from datetime import datetime, timezone

from .deriv_demo import (
    DerivContractSpec,
    DerivDemoConfig,
    DerivDemoExecutionAdapter,
    DerivDemoStatus,
)
from .execution import ExecutionGateway, ExecutionMode, ExecutionPolicy
from .risk import AccountSnapshot, ExposureSnapshot, RiskDecision, RiskStatus, TradePlan


def _plan() -> TradePlan:
    return TradePlan(
        pair="EURUSD", interval="5m", timestamp_utc="2026-09-14T20:00:00+00:00",
        direction="LONG", entry_price=1.1, stop_loss=1.09, take_profit=1.12,
        stop_distance=0.01, target_distance=0.02, reward_risk=2.0,
        quantity=1000, risk_amount=10, risk_fraction=0.005,
    )


def _request():
    decision = RiskDecision(RiskStatus.APPROVED, "EURUSD", "5m", _plan().timestamp_utc, "LONG", plan=_plan())
    return ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO)).create_request(
        decision, request_id="req-223", created_at_utc="2026-09-14T20:00:01+00:00"
    )


class FakeTransport:
    def __init__(self, *, real_url=False, proposal_error=False, buy_error=False):
        self.real_url = real_url
        self.proposal_error = proposal_error
        self.buy_error = buy_error
        self.calls = []

    def get_authenticated_websocket_url(self, config):
        self.calls.append(("otp", config.account_id))
        return "wss://api.derivws.com/trading/v1/options/ws/real?otp=x" if self.real_url else "wss://api.derivws.com/trading/v1/options/ws/demo?otp=x"

    def request_proposal(self, websocket_url, payload, timeout):
        self.calls.append(("proposal", payload))
        if self.proposal_error:
            return {"error": {"message": "proposal rejected"}}
        return {"proposal": {"id": "p-1", "ask_price": 10.0, "payout": 19.0, "spot": 1.1}}

    def buy(self, websocket_url, proposal_id, price, timeout):
        self.calls.append(("buy", proposal_id, price))
        if self.buy_error:
            return {"error": {"message": "buy rejected"}}
        return {"buy": {"contract_id": "c-1", "buy_price": price}}


def _config():
    return DerivDemoConfig("demo-1", "secret-token")


def _contract(symbol="EURUSD"):
    return DerivContractSpec(symbol, "CALL", 10, "stake", "USD", 5, "m")


def test_config_requires_credentials():
    try:
        DerivDemoConfig("", "x")
        assert False
    except ValueError:
        pass


def test_demo_execution_purchases_contract_with_mock_transport():
    transport = FakeTransport()
    adapter = DerivDemoExecutionAdapter(_config(), transport=transport, gateway=ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO)))
    result = adapter.execute(_request(), _contract())
    assert result.status is DerivDemoStatus.CONTRACT_PURCHASED
    assert result.contract_id == "c-1"
    assert [c[0] for c in transport.calls] == ["otp", "proposal", "buy"]
    assert result.live_execution is False


def test_rejects_non_demo_mode():
    req = _request()
    from dataclasses import replace
    req = replace(req, mode=ExecutionMode.LIVE)
    result = DerivDemoExecutionAdapter(_config(), transport=FakeTransport()).execute(req, _contract())
    assert result.status is DerivDemoStatus.INVALID_INPUT
    assert "DEMO" in (result.error or "")


def test_rejects_real_websocket_url():
    result = DerivDemoExecutionAdapter(_config(), transport=FakeTransport(real_url=True), gateway=ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO))).execute(_request(), _contract())
    assert result.status is DerivDemoStatus.INVALID_INPUT
    assert "demo-scoped" in (result.error or "")


def test_rejects_symbol_mismatch_before_network_proposal():
    transport = FakeTransport()
    result = DerivDemoExecutionAdapter(_config(), transport=transport, gateway=ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO))).execute(_request(), _contract("GBPUSD"))
    assert result.status is DerivDemoStatus.REJECTED
    assert "symbol" in result.reasons[0]
    assert [c[0] for c in transport.calls] == []


def test_proposal_api_error_does_not_buy():
    transport = FakeTransport(proposal_error=True)
    result = DerivDemoExecutionAdapter(_config(), transport=transport, gateway=ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO))).execute(_request(), _contract())
    assert result.status is DerivDemoStatus.API_ERROR
    assert result.contract_id is None
    assert [c[0] for c in transport.calls] == ["otp", "proposal"]


def test_buy_api_error_is_reported():
    transport = FakeTransport(buy_error=True)
    result = DerivDemoExecutionAdapter(_config(), transport=transport, gateway=ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO))).execute(_request(), _contract())
    assert result.status is DerivDemoStatus.API_ERROR
    assert result.proposal is not None
    assert result.contract_id is None


def test_config_rejects_non_https_rest_url():
    try:
        DerivDemoConfig("demo", "token", rest_base_url="http://localhost")
        assert False
    except ValueError:
        pass


def test_contract_requires_positive_amount_and_duration():
    for kwargs in ({"amount": 0}, {"duration": 0}):
        values = dict(underlying_symbol="EURUSD", contract_type="CALL", amount=10, basis="stake", currency="USD", duration=5, duration_unit="m")
        values.update(kwargs)
        try:
            DerivContractSpec(**values)
            assert False
        except ValueError:
            pass


def test_environment_config_requires_values(monkeypatch):
    monkeypatch.delenv("DERIV_DEMO_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("DERIV_AUTH_TOKEN", raising=False)
    try:
        DerivDemoConfig.from_environment()
        assert False
    except ValueError:
        pass


def test_contract_extra_parameters_are_preserved():
    spec = _contract()
    spec2 = DerivContractSpec(**{**spec.__dict__, "extra_parameters": {"multiplier": 10}})
    assert spec2.to_dict()["multiplier"] == 10


def test_buy_uses_proposal_ask_price():
    transport = FakeTransport()
    adapter = DerivDemoExecutionAdapter(_config(), transport=transport, gateway=ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO)))
    adapter.execute(_request(), _contract())
    assert transport.calls[-1] == ("buy", "p-1", 10.0)
