from market.oos_walk_forward import *

def w(i,pnl=100,locked=True,cost=True,risk=True):
    from datetime import datetime, timedelta, timezone
    base=datetime(2025,1,1,tzinfo=timezone.utc) + timedelta(days=(i-1)*40)
    train_start=base; train_end=base+timedelta(days=20); test_start=train_end; test_end=test_start+timedelta(days=20)
    f=lambda d:d.isoformat().replace("+00:00","Z")
    return OOSWindowEvidence(f"w{i}",f(train_start),f(train_end),f(test_start),f(test_end),10,pnl,f"p{i}",locked,cost,risk,{})

def test_window_contract():
    assert w(1).profitable

def test_requires_timezone_and_order():
    try: OOSWindowEvidence('x','2025-01-01','2025-02-01T00:00:00Z','2025-02-01T00:00:00Z','2025-03-01T00:00:00Z',10,1,'p')
    except ValueError: pass
    else: assert False

def test_insufficient_windows():
    r=evaluate_oos_walk_forward([w(1),w(2)])
    assert r.status==OOS_EVIDENCE and 'too_few_test_windows' in r.limitations

def test_stable_oos():
    r=evaluate_oos_walk_forward([w(1),w(2),w(3)])
    assert r.status==OOS_STABILITY and r.profitable_window_fraction==1.0

def test_unprofitable_breadth_is_not_stability():
    r=evaluate_oos_walk_forward([w(1,100),w(2,-50),w(3,-10)])
    assert r.status==OOS_EVIDENCE and r.profitable_windows==1

def test_cost_coverage_required():
    r=evaluate_oos_walk_forward([w(1),w(2),w(3,cost=False)])
    assert r.status==OOS_EVIDENCE and 'cost_coverage_incomplete' in r.limitations

def test_risk_coverage_required():
    r=evaluate_oos_walk_forward([w(1),w(2),w(3,risk=False)])
    assert r.status==OOS_EVIDENCE and 'risk_coverage_incomplete' in r.limitations

def test_selection_lock_leakage():
    r=evaluate_oos_walk_forward([w(1),w(2),w(3,locked=False)])
    assert r.status==INVALID_EVIDENCE and r.leakage_detected

def test_overlapping_test_windows_detected():
    a=w(1)
    b=OOSWindowEvidence('w2','2025-01-10T00:00:00Z','2025-01-31T00:00:00Z','2025-02-05T00:00:00Z','2025-03-05T00:00:00Z',10,1,'p2')
    r=evaluate_oos_walk_forward([a,b])
    assert r.status==INVALID_EVIDENCE

def test_trade_evidence_adapter():
    rows=[x.to_dict() for x in (w(1),w(2),w(3))]
    r=evaluate_trade_evidence_windows(rows)
    assert r.valid_windows==3 and len(r.evidence_fingerprint)==64

def test_fingerprint_reproducible():
    a=evaluate_oos_walk_forward([w(1),w(2),w(3)]); b=evaluate_oos_walk_forward([w(1),w(2),w(3)])
    assert a.evidence_fingerprint==b.evidence_fingerprint

def test_criteria_validation():
    try: OOSWalkForwardCriteria(min_test_windows=0)
    except ValueError: pass
    else: assert False
