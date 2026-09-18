import pytest

from market.deriv_demo import DerivContractSpec
from market.deriv_live_account import DerivLiveConnectivityResult
from market.deriv_live_execution import (
    DerivLiveExecutionAdapter,
    DerivLiveExecutionConfig,
    DerivLiveExecutionStatus,
)
from market.execution import ExecutionGateway, ExecutionMode, ExecutionPolicy
from market.execution_outcome import ExecutionOutcomeStatus
from market.risk import RiskDecision, RiskStatus, TradePlan


class FakeTransport:
    def __init__(self, *, buy_response=None, proposal_response=None, connectivity=None, ws_url="wss://api.derivws.com/trading/v1/options/ws/real?otp=fake"):
        self.buy_response = buy_response or {"msg_type": "buy", "buy": {"contract_id": 12345, "buy_price": 10.0, "transaction_id": 999}}
        self.proposal_response = proposal_response or {"msg_type": "proposal", "proposal": {"id": "proposal-1", "ask_price": 10.0, "payout": 20.0, "spot": 1.085}}
        self.connectivity = connectivity or DerivLiveConnectivityResult(True, True, True, True, "REAL123", "USD", "ok", True)
        self.ws_url = ws_url
        self.calls = []

    def verify_real_session(self, config):
        self.calls.append(("verify", config.account_id))
        return self.connectivity

    def get_authenticated_websocket_url(self, config):
        self.calls.append(("url",))
        return self.ws_url

    def request_proposal(self, websocket_url, payload, timeout):
        self.calls.append(("proposal", dict(payload)))
        return self.proposal_response

    def buy(self, websocket_url, proposal_id, price, timeout):
        self.calls.append(("buy", proposal_id, price))
        return self.buy_response


def request():
    plan = TradePlan("EURUSD", "5m", "2026-09-18T20:00:00+00:00", "LONG", 1.08, 1.07, 1.10, .01, .02, 2.0, 10.0, .10, .01)
    decision = RiskDecision(RiskStatus.APPROVED, "EURUSD", "5m", plan.timestamp_utc, "LONG", plan=plan)
    gateway = ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.LIVE))
    return gateway.create_request(decision, request_id="req-live-1", created_at_utc="2026-09-18T20:00:01+00:00")


def contract():
    return DerivContractSpec("EURUSD", "CALL", 10.0, "stake", "USD", 5, "m")


def config(enabled=False):
    return DerivLiveExecutionConfig("REAL123", "secret", "12345", live_enabled=enabled)


def test_live_disabled_by_default_and_buy_is_never_called():
    t = FakeTransport()
    result = DerivLiveExecutionAdapter(config(), transport=t).execute(request(), contract(), explicit_live_confirmation=True)
    assert result.status is DerivLiveExecutionStatus.BLOCKED
    assert result.succeeded is False
    assert not any(c[0] == "buy" for c in t.calls)


def test_explicit_confirmation_is_required():
    t = FakeTransport()
    result = DerivLiveExecutionAdapter(config(True), transport=t).execute(request(), contract())
    assert result.status is DerivLiveExecutionStatus.BLOCKED
    assert "confirmation" in result.reasons[0]
    assert not any(c[0] == "buy" for c in t.calls)


def test_wrong_mode_rejected_without_network():
    t = FakeTransport()
    r = request()
    # Build a DEMO request with a gateway that admits DEMO, then send to live adapter.
    plan = r.plan
    decision = RiskDecision(RiskStatus.APPROVED, "EURUSD", "5m", plan.timestamp_utc, "LONG", plan=plan)
    demo_req = ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO)).create_request(decision, request_id="demo-1", created_at_utc="2026-09-18T20:00:01+00:00")
    result = DerivLiveExecutionAdapter(config(True), transport=t).execute(demo_req, contract(), explicit_live_confirmation=True)
    assert result.status is DerivLiveExecutionStatus.UNKNOWN
    assert not t.calls


def test_real_session_must_be_verified():
    t = FakeTransport(connectivity=DerivLiveConnectivityResult(True, True, False, False, "REAL123", "USD", "bad", True))
    result = DerivLiveExecutionAdapter(config(True), transport=t).execute(request(), contract(), explicit_live_confirmation=True)
    assert result.status is DerivLiveExecutionStatus.BLOCKED
    assert not any(c[0] == "proposal" for c in t.calls)
    assert not any(c[0] == "buy" for c in t.calls)


def test_account_currency_must_match_contract():
    t = FakeTransport(connectivity=DerivLiveConnectivityResult(True, True, True, True, "REAL123", "EUR", "ok", True))
    result = DerivLiveExecutionAdapter(config(True), transport=t).execute(request(), contract(), explicit_live_confirmation=True)
    assert result.status is DerivLiveExecutionStatus.BLOCKED
    assert "currency" in result.reasons[0]
    assert not any(c[0] == "buy" for c in t.calls)


def test_symbol_must_match_trade_plan():
    t = FakeTransport()
    bad = DerivContractSpec("GBPUSD", "CALL", 10.0, "stake", "USD", 5, "m")
    result = DerivLiveExecutionAdapter(config(True), transport=t).execute(request(), bad, explicit_live_confirmation=True)
    assert result.status is DerivLiveExecutionStatus.BLOCKED
    assert not t.calls


def test_real_ws_url_is_enforced():
    t = FakeTransport(ws_url="wss://api.derivws.com/trading/v1/options/ws/demo?otp=fake")
    result = DerivLiveExecutionAdapter(config(True), transport=t).execute(request(), contract(), explicit_live_confirmation=True)
    assert result.status is DerivLiveExecutionStatus.UNKNOWN
    assert not any(c[0] == "buy" for c in t.calls)


def test_success_requires_valid_buy_response_and_produces_confirmed_outcome():
    t = FakeTransport()
    result = DerivLiveExecutionAdapter(config(True), transport=t).execute(request(), contract(), explicit_live_confirmation=True)
    assert result.status is DerivLiveExecutionStatus.CONFIRMED
    assert result.succeeded is True
    assert result.live_execution is True
    assert result.outcome is not None
    assert result.outcome.status is ExecutionOutcomeStatus.CONFIRMED
    assert result.outcome.broker_order_id == "12345"
    assert result.outcome.execution_price == 10.0
    assert result.outcome.executed_quantity == 10.0
    assert any(c[0] == "buy" for c in t.calls)


def test_buy_api_error_is_failed_not_success():
    t = FakeTransport(buy_response={"msg_type": "error", "error": {"message": "insufficient balance"}})
    result = DerivLiveExecutionAdapter(config(True), transport=t).execute(request(), contract(), explicit_live_confirmation=True)
    assert result.status is DerivLiveExecutionStatus.FAILED
    assert result.succeeded is False
    assert result.outcome is not None
    assert result.outcome.status is ExecutionOutcomeStatus.FAILED


def test_missing_contract_id_never_becomes_success():
    t = FakeTransport(buy_response={"msg_type": "buy", "buy": {"buy_price": 10.0}})
    result = DerivLiveExecutionAdapter(config(True), transport=t).execute(request(), contract(), explicit_live_confirmation=True)
    assert result.status is DerivLiveExecutionStatus.UNKNOWN
    assert result.succeeded is False


def test_missing_proposal_id_blocks_buy():
    t = FakeTransport(proposal_response={"msg_type": "proposal", "proposal": {"ask_price": 10.0}})
    result = DerivLiveExecutionAdapter(config(True), transport=t).execute(request(), contract(), explicit_live_confirmation=True)
    assert result.status is DerivLiveExecutionStatus.UNKNOWN
    assert not any(c[0] == "buy" for c in t.calls)


def test_credentials_are_not_in_result():
    result = DerivLiveExecutionAdapter(config(True), transport=FakeTransport()).execute(request(), contract(), explicit_live_confirmation=True)
    text = str(result.to_dict())
    assert "secret" not in text
    assert "secret" not in text
    assert "app-secret" not in text


def test_environment_flag_defaults_off():
    c = DerivLiveExecutionConfig.from_environment({"DERIV_REAL_ACCOUNT_ID": "R", "DERIV_PAT": "secret", "DERIV_APP_ID": "A"})
    assert c.live_enabled is False


def test_environment_flag_requires_exact_true():
    c = DerivLiveExecutionConfig.from_environment({"DERIV_REAL_ACCOUNT_ID": "R", "DERIV_PAT": "secret", "DERIV_APP_ID": "A", "APEX_LIVE_EXECUTION_ENABLED": "yes"})
    assert c.live_enabled is False
    c2 = DerivLiveExecutionConfig.from_environment({"DERIV_REAL_ACCOUNT_ID": "R", "DERIV_PAT": "secret", "DERIV_APP_ID": "A", "APEX_LIVE_EXECUTION_ENABLED": "TRUE"})
    assert c2.live_enabled is True


def test_safe_summary_contains_no_secret():
    c = config(True)
    summary = c.safe_summary()
    assert summary["credentials_exposed"] is False
    assert "secret" not in str(summary)


def test_failed_proposal_does_not_call_buy():
    t = FakeTransport(proposal_response={"msg_type": "error", "error": {"message": "proposal rejected"}})
    result = DerivLiveExecutionAdapter(config(True), transport=t).execute(request(), contract(), explicit_live_confirmation=True)
    assert result.status is DerivLiveExecutionStatus.FAILED
    assert not any(c[0] == "buy" for c in t.calls)
