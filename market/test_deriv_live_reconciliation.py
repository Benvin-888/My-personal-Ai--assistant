from dataclasses import replace

from market.deriv_demo import DerivContractSpec
from market.deriv_live_execution import DerivLiveExecutionConfig
from market.deriv_live_reconciliation import DerivLiveReconciler
from market.execution import ExecutionMode, ExecutionRequest
from market.execution_outcome import ExecutionOutcome, ExecutionOutcomeStatus
from market.broker_state import ReconciliationStatus, PositionLifecycle


class T:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_authenticated_websocket_url(self, config):
        self.calls.append(("url",))
        return "wss://api.derivws.com/trading/v1/options/ws/real?otp=x"

    def request(self, url, payload, timeout):
        self.calls.append(("request", dict(payload)))
        return self.payload


def config():
    return DerivLiveExecutionConfig("REAL123", "secret", "APP", live_enabled=True)


def request():
    from market.test_execution import approved
    from market.execution import ExecutionGateway, ExecutionPolicy
    gateway = ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.LIVE))
    return gateway.create_request(approved(), request_id="REQ238", created_at_utc="2026-09-14T20:00:01+00:00")


def contract():
    return DerivContractSpec("EURUSD", "CALL", 5, "stake", "USD", 5, "m")


def outcome():
    return ExecutionOutcome(
        request_id="REQ238", mode=ExecutionMode.LIVE, status=ExecutionOutcomeStatus.CONFIRMED,
        broker="deriv", account_scope="REAL123", broker_order_id="12345",
        execution_price=5.0, executed_quantity=5.0,
    )


def reconciler(payload):
    t = T(payload)
    return DerivLiveReconciler(config(), transport=t), t


def test_match_verifies_real_broker_state_and_stores_it():
    r, t = reconciler({"msg_type":"proposal_open_contract", "proposal_open_contract": {
        "contract_id":12345, "contract_type":"CALL", "currency":"USD",
        "underlying_symbol":"EURUSD", "buy_price":"5", "payout":"8", "is_sold":0,
    }})
    result = r.reconcile(request(), outcome(), contract())
    assert result.status is ReconciliationStatus.MATCHED
    assert result.verified
    assert result.broker_state.lifecycle is PositionLifecycle.OPEN
    assert r.store.get("deriv", "live", "12345") is not None
    assert [c[0] for c in t.calls] == ["url", "request"]


def test_new_deriv_string_numeric_fields_are_accepted_and_optional_symbol_is_safe():
    r, _ = reconciler({"msg_type":"proposal_open_contract", "proposal_open_contract": {
        "contract_id":"12345", "contract_type":"CALL", "currency":"USD",
        "buy_price":"5.00", "payout":"8.00", "is_sold":0,
    }})
    result = r.reconcile(request(), outcome(), contract())
    assert result.status is ReconciliationStatus.MATCHED
    assert result.broker_state.buy_price == 5.0


def test_closed_contract_is_still_successfully_reconciled():
    r, _ = reconciler({"msg_type":"proposal_open_contract", "proposal_open_contract":{"contract_id":12345,"contract_type":"CALL","currency":"USD","underlying_symbol":"EURUSD","buy_price":5,"is_sold":1}})
    result = r.reconcile(request(), outcome(), contract())
    assert result.status is ReconciliationStatus.MATCHED
    assert result.broker_state.lifecycle is PositionLifecycle.CLOSED


def test_contract_id_mismatch_is_fail_closed():
    r, _ = reconciler({"msg_type":"proposal_open_contract", "proposal_open_contract":{"contract_id":999,"contract_type":"CALL","currency":"USD","underlying_symbol":"EURUSD","buy_price":5}})
    result = r.reconcile(request(), outcome(), contract())
    assert result.status is ReconciliationStatus.MISMATCH
    assert not result.verified


def test_type_symbol_currency_and_price_mismatch_are_detected():
    r, _ = reconciler({"msg_type":"proposal_open_contract", "proposal_open_contract":{"contract_id":12345,"contract_type":"PUT","currency":"EUR","underlying_symbol":"frxGBPUSD","buy_price":6}})
    result = r.reconcile(request(), outcome(), contract())
    assert result.status is ReconciliationStatus.MISMATCH
    assert len(result.reasons) == 4


def test_missing_identity_fields_are_not_accepted():
    r, _ = reconciler({"msg_type":"proposal_open_contract", "proposal_open_contract":{"contract_id":12345,"buy_price":5}})
    result = r.reconcile(request(), outcome(), contract())
    assert result.status is ReconciliationStatus.MISMATCH


def test_api_error_is_unknown_not_success():
    r, _ = reconciler({"error":{"message":"temporary broker error"}})
    result = r.reconcile(request(), outcome(), contract())
    assert result.status is ReconciliationStatus.UNKNOWN
    assert not result.verified


def test_wrong_message_type_is_unknown():
    r, _ = reconciler({"msg_type":"buy","buy":{"contract_id":12345}})
    result = r.reconcile(request(), outcome(), contract())
    assert result.status is ReconciliationStatus.UNKNOWN


def test_missing_payload_is_unknown():
    r, _ = reconciler({})
    result = r.reconcile(request(), outcome(), contract())
    assert result.status is ReconciliationStatus.UNKNOWN


def test_non_real_url_is_rejected():
    class DemoURL(T):
        def get_authenticated_websocket_url(self, config):
            return "wss://api.derivws.com/trading/v1/options/ws/demo?otp=x"
    r = DerivLiveReconciler(config(), transport=DemoURL({"proposal_open_contract":{}}))
    result = r.reconcile(request(), outcome(), contract())
    assert result.status is ReconciliationStatus.UNKNOWN


def test_non_confirmed_outcome_cannot_be_reconciled():
    r, t = reconciler({})
    submitted = replace(outcome(), status=ExecutionOutcomeStatus.SUBMITTED)
    result = r.reconcile(request(), submitted, contract())
    assert result.status is ReconciliationStatus.INVALID_INPUT
    assert t.calls == []


def test_account_scope_mismatch_is_rejected_before_network():
    r, t = reconciler({})
    wrong_account = replace(outcome(), account_scope="OTHER")
    result = r.reconcile(request(), wrong_account, contract())
    assert result.status is ReconciliationStatus.INVALID_INPUT
    assert t.calls == []


def test_wrong_mode_request_is_rejected_before_network():
    r, t = reconciler({})
    demo_request = replace(request(), mode=ExecutionMode.DEMO)
    result = r.reconcile(demo_request, outcome(), contract())
    assert result.status is ReconciliationStatus.INVALID_INPUT
    assert t.calls == []


def test_non_numeric_deriv_contract_id_is_rejected():
    r, _ = reconciler({"proposal_open_contract":{"contract_id":"ABC","contract_type":"CALL","currency":"USD","underlying_symbol":"EURUSD","buy_price":5}})
    bad = replace(outcome(), broker_order_id="ABC")
    result = r.reconcile(request(), bad, contract())
    assert result.status is ReconciliationStatus.INVALID_INPUT


def test_reconciliation_is_read_only_transport_boundary():
    r, t = reconciler({"msg_type":"proposal_open_contract", "proposal_open_contract":{"contract_id":12345,"contract_type":"CALL","currency":"USD","underlying_symbol":"EURUSD","buy_price":5}})
    r.reconcile(request(), outcome(), contract())
    assert all(call[0] in {"url", "request"} for call in t.calls)
    assert all("buy" not in call[1] for call in t.calls if call[0] == "request")
