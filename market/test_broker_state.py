from market.broker_state import *


def state(cid="123", lifecycle=PositionLifecycle.OPEN):
    return BrokerContractState("deriv", "demo", cid, "CALL", "EURUSD", "USD", 5.0, 8.0, False, lifecycle)


def test_state_rejects_empty_id():
    try: BrokerContractState("deriv", "demo", "")
    except BrokerStateError: return
    assert False


def test_live_property():
    assert not state().live
    assert BrokerContractState("deriv", "live", "1").live


def test_to_dict():
    assert state().to_dict()["contract_id"] == "123"


def test_reconciliation_match():
    r = ReconciliationResult(ReconciliationStatus.MATCHED, "123", state=state())
    assert r.matched and r.safe_for_position_state


def test_reconciliation_mismatch_not_safe():
    r = ReconciliationResult(ReconciliationStatus.MISMATCH, "123", reasons=("x",), state=state())
    assert not r.safe_for_position_state


def test_store_applies_only_match():
    s=BrokerPositionStore(); assert s.apply(ReconciliationResult(ReconciliationStatus.MISMATCH,"1",state=state("1"))) is False
    assert s.get("deriv","demo","1") is None


def test_store_applies_match():
    s=BrokerPositionStore(); assert s.apply(ReconciliationResult(ReconciliationStatus.MATCHED,"1",state=state("1")))
    assert s.get("deriv","demo","1").contract_id == "1"


def test_open_positions():
    s=BrokerPositionStore(); s.apply(ReconciliationResult(ReconciliationStatus.MATCHED,"1",state=state("1"))); s.apply(ReconciliationResult(ReconciliationStatus.MATCHED,"2",state=state("2",PositionLifecycle.CLOSED)))
    assert [x.contract_id for x in s.open_positions()] == ["1"]


def test_all():
    s=BrokerPositionStore(); s.apply(ReconciliationResult(ReconciliationStatus.MATCHED,"1",state=state("1"))); assert len(s.all())==1


def test_clear():
    s=BrokerPositionStore(); s.apply(ReconciliationResult(ReconciliationStatus.MATCHED,"1",state=state("1"))); s.clear(); assert not s.all()
