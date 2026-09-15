from __future__ import annotations

from dataclasses import replace

from .demo_forward import ControlledDemoForwardTrader, DemoForwardPolicy, DemoForwardStatus
from .deriv_demo import DerivContractSpec, DerivDemoConfig, DerivDemoExecutionAdapter
from .deriv_demo_verification import DerivDemoExecutionVerifier
from .deriv_demo_control import DerivDemoControlSession
from .deriv_reconciliation import DerivDemoReconciler
from .execution import ExecutionGateway, ExecutionMode, ExecutionPolicy
from .risk import RiskDecision, RiskStatus, TradePlan


class FakeTransport:
    def __init__(self, *, mismatch=False):
        self.mismatch = mismatch
        self.calls = []

    def get_authenticated_websocket_url(self, config):
        self.calls.append(("auth",))
        return "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"

    def request_proposal(self, websocket_url, payload, timeout):
        self.calls.append(("proposal", dict(payload)))
        return {"proposal": {"id": "P-1", "ask_price": 1.0, "payout": 1.8, "spot": 1.1}}

    def buy(self, websocket_url, proposal_id, price, timeout):
        self.calls.append(("buy", proposal_id, price))
        return {"buy": {"contract_id": "9001", "buy_price": 1.0}}

    def request(self, websocket_url, payload, timeout):
        self.calls.append(("request", dict(payload)))
        if "proposal_open_contract" in payload:
            return {"proposal_open_contract": {
                "contract_id": "9001",
                "contract_type": "CALL",
                "underlying_symbol": "frxEURUSD",
                "currency": "USD",
                "buy_price": 1.0,
                "payout": 1.8,
                "is_sold": False,
            }}
        return {"active_symbols": [{"underlying_symbol": "frxEURUSD"}]}

    def close(self):
        pass


def _config():
    return DerivDemoConfig(account_id="demo", authorization_token="token")


def _contract():
    return DerivContractSpec(underlying_symbol="frxEURUSD", contract_type="CALL", amount=1.0,
                             basis="stake", currency="USD", duration=5, duration_unit="m")


def _request():
    plan = TradePlan(pair="frxEURUSD", interval="5m", timestamp_utc="2026-09-15T12:00:00+00:00",
                     direction="LONG", entry_price=1.1, stop_loss=1.0, take_profit=1.3,
                     stop_distance=0.1, target_distance=0.2, reward_risk=2.0,
                     quantity=1.0, risk_amount=1.0, risk_fraction=0.005)
    decision = RiskDecision(status=RiskStatus.APPROVED, pair=plan.pair, interval=plan.interval,
                            timestamp_utc=plan.timestamp_utc, direction=plan.direction, plan=plan)
    gateway = ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO))
    return gateway.create_request(decision, request_id="demo-forward-1",
                                  created_at_utc="2026-09-15T12:00:01+00:00")


def _trader(transport):
    adapter = DerivDemoExecutionAdapter(_config(), transport=transport, gateway=ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO)))
    session = DerivDemoControlSession(_config(), transport=transport)
    session.websocket_url = "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"
    verifier = DerivDemoExecutionVerifier(session)
    return ControlledDemoForwardTrader(_config(), adapter=adapter, verifier=verifier, control_session=session)


def test_requires_explicit_confirmation():
    trader = _trader(FakeTransport())
    result = trader.execute_once(_request(), _contract())
    assert result.status is DemoForwardStatus.REJECTED
    assert trader.executions_used == 0


def test_rejects_non_demo_request():
    trader = _trader(FakeTransport())
    request = replace(_request(), mode=ExecutionMode.PAPER)
    result = trader.execute_once(request, _contract(), confirm_purchase=True)
    assert result.status is DemoForwardStatus.REJECTED
    assert trader.executions_used == 0


def test_requires_one_shot_limit():
    trader = _trader(FakeTransport())
    trader._executions = 1
    result = trader.execute_once(_request(), _contract(), confirm_purchase=True)
    assert result.status is DemoForwardStatus.ALREADY_EXECUTED


def test_success_requires_verification_and_reconciliation():
    transport = FakeTransport()
    adapter = DerivDemoExecutionAdapter(_config(), transport=transport, gateway=ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO)))
    # Use the adapter transport for the read-only verifier/reconciler as well.
    session = DerivDemoControlSession(_config(), transport=transport)
    session.websocket_url = "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"
    verifier = DerivDemoExecutionVerifier(session)
    trader = ControlledDemoForwardTrader(_config(), adapter=adapter, verifier=verifier, control_session=session)
    result = trader.execute_once(_request(), _contract(), confirm_purchase=True)
    assert result.status is DemoForwardStatus.RECONCILED
    assert result.forward_evidence_ready
    assert result.broker_confirmed
    assert result.contract_id == "9001"
    assert trader.store.get("deriv", "demo", "9001") is not None


def test_failed_broker_verification_blocks_forward_evidence():
    transport = FakeTransport()
    adapter = DerivDemoExecutionAdapter(_config(), transport=transport, gateway=ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO)))
    session = DerivDemoControlSession(_config(), transport=transport)
    session.websocket_url = "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"
    verifier = DerivDemoExecutionVerifier(session)
    trader = ControlledDemoForwardTrader(_config(), adapter=adapter, verifier=verifier, control_session=session)
    bad_contract = replace(_contract(), currency="EUR")
    result = trader.execute_once(_request(), bad_contract, confirm_purchase=True)
    assert result.status is DemoForwardStatus.REJECTED
    assert not result.forward_evidence_ready


def test_execution_receipt_is_demo_only():
    trader = _trader(FakeTransport())
    result = trader.execute_once(_request(), _contract(), confirm_purchase=True)
    assert result.live_execution is False
    assert result.execution is not None
    assert result.execution.live_execution is False


def test_reconciled_state_is_open_when_contract_not_sold():
    transport = FakeTransport()
    adapter = DerivDemoExecutionAdapter(_config(), transport=transport, gateway=ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO)))
    session = DerivDemoControlSession(_config(), transport=transport)
    session.websocket_url = "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"
    verifier = DerivDemoExecutionVerifier(session)
    trader = ControlledDemoForwardTrader(_config(), adapter=adapter, verifier=verifier, control_session=session)
    result = trader.execute_once(_request(), _contract(), confirm_purchase=True)
    assert result.reconciliation is not None
    assert result.reconciliation.state is not None
    assert result.reconciliation.state.lifecycle.value == "OPEN"


def test_result_serializes_safely():
    result = _trader(FakeTransport()).execute_once(_request(), _contract(), confirm_purchase=True)
    payload = result.to_dict()
    assert payload["live_execution"] is False
    assert payload["account_mode"] if "account_mode" in payload else True
    assert payload["status"] == "RECONCILED"


def test_duplicate_request_is_blocked_by_gateway_on_reuse():
    transport = FakeTransport()
    gateway = ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO))
    adapter = DerivDemoExecutionAdapter(_config(), transport=transport, gateway=gateway)
    session = DerivDemoControlSession(_config(), transport=transport)
    session.websocket_url = "wss://api.derivws.com/trading/v1/options/ws/demo?otp=test"
    verifier = DerivDemoExecutionVerifier(session)
    trader = ControlledDemoForwardTrader(_config(), adapter=adapter, verifier=verifier, control_session=session)
    first = trader.execute_once(_request(), _contract(), confirm_purchase=True)
    assert first.status is DemoForwardStatus.RECONCILED
    second = trader.execute_once(_request(), _contract(), confirm_purchase=True)
    assert second.status is DemoForwardStatus.ALREADY_EXECUTED


def test_policy_rejects_multiple_execution_configuration():
    try:
        DemoForwardPolicy(max_executions_per_controller=2)
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("expected one-shot policy rejection")
