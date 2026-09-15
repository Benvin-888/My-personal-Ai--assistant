from market.deriv_demo import DerivContractSpec, DerivDemoConfig
from market.deriv_demo_control import DerivDemoControlSession
from market.deriv_reconciliation import DerivDemoReconciler
from market.broker_state import ReconciliationStatus, PositionLifecycle


class T:
    def __init__(self, payload): self.payload=payload
    def get_authenticated_websocket_url(self, config): return "wss://api.derivws.com/trading/v1/options/ws/demo?otp=x"
    def request(self, url, payload, timeout): return self.payload
    def close(self): pass


def session(payload):
    s=DerivDemoControlSession(DerivDemoConfig("VRTC","token"), transport=T(payload)); s.connect(); return s


def contract(): return DerivContractSpec("frxEURUSD","CALL",5,"stake","USD",5,"m")


def test_reconcile_match():
    s=session({"proposal_open_contract":{"contract_id":123,"contract_type":"CALL","currency":"USD","underlying_symbol":"frxEURUSD","buy_price":5,"payout":8,"is_sold":0}})
    r=DerivDemoReconciler(s).reconcile("123",contract()); assert r.status is ReconciliationStatus.MATCHED; assert r.state.lifecycle is PositionLifecycle.OPEN


def test_reconcile_closed():
    s=session({"proposal_open_contract":{"contract_id":123,"contract_type":"CALL","currency":"USD","is_sold":1}})
    r=DerivDemoReconciler(s).reconcile("123",contract()); assert r.state.lifecycle is PositionLifecycle.CLOSED


def test_id_mismatch():
    s=session({"proposal_open_contract":{"contract_id":999,"contract_type":"CALL","currency":"USD"}})
    assert DerivDemoReconciler(s).reconcile("123",contract()).status is ReconciliationStatus.MISMATCH


def test_type_mismatch():
    s=session({"proposal_open_contract":{"contract_id":123,"contract_type":"PUT","currency":"USD"}})
    assert DerivDemoReconciler(s).reconcile("123",contract()).status is ReconciliationStatus.MISMATCH


def test_currency_mismatch():
    s=session({"proposal_open_contract":{"contract_id":123,"contract_type":"CALL","currency":"EUR"}})
    assert DerivDemoReconciler(s).reconcile("123",contract()).status is ReconciliationStatus.MISMATCH


def test_api_error():
    s=session({"error":{"message":"not found"}}); assert DerivDemoReconciler(s).reconcile("123").status is ReconciliationStatus.UNKNOWN


def test_missing_payload():
    s=session({}); assert DerivDemoReconciler(s).reconcile("123").status is ReconciliationStatus.UNKNOWN


def test_not_connected():
    s=DerivDemoControlSession(DerivDemoConfig("VRTC","token"), transport=T({})); r=DerivDemoReconciler(s).reconcile("123"); assert r.status is ReconciliationStatus.UNKNOWN


def test_empty_id():
    s=session({}); assert DerivDemoReconciler(s).reconcile("").status is ReconciliationStatus.INVALID_INPUT


def test_store_receives_match():
    s=session({"proposal_open_contract":{"contract_id":123,"contract_type":"CALL","currency":"USD"}}); r=DerivDemoReconciler(s); x=r.reconcile("123",contract()); assert r.store.get("deriv","demo","123") is not None
