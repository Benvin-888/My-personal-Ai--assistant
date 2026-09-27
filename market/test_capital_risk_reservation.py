from market.capital_risk_reservation import (
    CapitalRiskReservation, ReservationCriteria, ReservationLedgerSnapshot,
    ReservationLedgerStatus, ReservationStatus, assess_reservation_capacity,
    apply_reservation_event, make_reservation, reservation_ledger_is_not_execution_authorization,
    validate_reservation_request,
)


def reservation(**kw):
    return make_reservation(
        reservation_id=kw.get("reservation_id", "r-1"), created_at=kw.get("created_at", "2026-09-25T10:00:00Z"),
        account_scope=kw.get("account_scope", "acct"), strategy_id=kw.get("strategy_id", "trend_momentum"),
        strategy_version=kw.get("strategy_version", "1.1.2"), capital_amount=kw.get("capital_amount", 1000.0),
        risk_amount=kw.get("risk_amount", 40.0), expires_at=kw.get("expires_at", "2026-09-25T11:00:00Z"),
        source_decision_id=kw.get("source_decision_id", "decision-1"),
    )


def snap(reservations=(), **kw):
    base = dict(observed_at="2026-09-25T10:30:00Z", account_scope="acct", capital_budget=7000.0,
                risk_budget=300.0, committed_capital=1000.0, committed_risk=50.0,
                reservations=tuple(reservations))
    base.update(kw)
    return ReservationLedgerSnapshot(**base)


def test_capacity_available_and_reservation_reduces_capacity():
    a = assess_reservation_capacity(snap((reservation(),)), ReservationCriteria(), "trend_momentum", "1.1.2")
    assert a.status is ReservationLedgerStatus.AVAILABLE
    assert a.active_reserved_capital == 1000.0
    assert a.available_capital_after == 5000.0
    assert a.available_risk_after == 210.0


def test_missing_budget_fails_closed():
    a = assess_reservation_capacity(snap(capital_budget=None), ReservationCriteria())
    assert a.status is ReservationLedgerStatus.INSUFFICIENT_DATA
    assert "capital_budget_missing" in a.reasons


def test_expired_reservation_is_not_active():
    r = reservation(expires_at="2026-09-25T10:15:00Z")
    a = assess_reservation_capacity(snap((r,)), ReservationCriteria())
    assert a.active_reserved_capital == 0.0
    assert a.available_capital_after == 6000.0


def test_account_scope_mismatch_is_invalid():
    r = reservation(account_scope="other")
    a = assess_reservation_capacity(snap((r,)), ReservationCriteria())
    assert a.status is ReservationLedgerStatus.INVALID
    assert "reservation_account_scope_mismatch" in a.reasons


def test_reservation_request_requires_expiry_and_decision():
    r = reservation(expires_at=None, source_decision_id=None)
    errors = validate_reservation_request(r, snap(), ReservationCriteria())
    assert "expiry_missing" in errors
    assert "source_decision_id_missing" in errors


def test_reservation_request_validates_fingerprint():
    r = reservation()
    assert validate_reservation_request(r, snap(), ReservationCriteria()) == ()
    broken = CapitalRiskReservation(**{**r.__dict__, "capital_amount": 2000.0})
    assert "reservation_fingerprint_mismatch" in validate_reservation_request(broken, snap(), ReservationCriteria())


def test_capacity_limits_strategy_reservations():
    c = ReservationCriteria(max_strategy_reserved_capital=1200.0, max_strategy_reserved_risk=50.0)
    r = reservation(capital_amount=1500.0)
    a = assess_reservation_capacity(snap((r,)), c, "trend_momentum", "1.1.2")
    assert a.status is ReservationLedgerStatus.LIMITED
    assert "strategy_reserved_capital_exceeded" in a.reasons


def test_release_event_is_append_only_state_transition():
    r = reservation()
    released = apply_reservation_event(r, ReservationStatus.RELEASED, "2026-09-25T10:40:00Z")
    assert released.status is ReservationStatus.RELEASED
    assert released.released_at == "2026-09-25T10:40:00Z"
    assert released.reservation_fingerprint


def test_consumed_event_is_not_reusable():
    r = reservation()
    consumed = apply_reservation_event(r, ReservationStatus.CONSUMED, "2026-09-25T10:40:00Z")
    try:
        apply_reservation_event(consumed, ReservationStatus.RELEASED, "2026-09-25T10:41:00Z")
    except ValueError as exc:
        assert str(exc) == "reservation_not_active"
    else:
        raise AssertionError("expected reservation_not_active")


def test_duplicate_reservation_ids_are_invalid_in_snapshot():
    r1 = reservation(reservation_id="same")
    r2 = reservation(reservation_id="same", strategy_id="mean_reversion")
    # The ledger must not silently merge duplicate identities.
    a = assess_reservation_capacity(snap((r1, r2)), ReservationCriteria())
    assert a.status is ReservationLedgerStatus.INVALID
    assert "duplicate_reservation_id" in a.reasons


def test_non_execution_authority():
    a = assess_reservation_capacity(snap(), ReservationCriteria())
    assert reservation_ledger_is_not_execution_authorization(a)
    assert a.execution_authorized is False


def test_reservation_lifetime_limit_is_enforced():
    r = reservation(expires_at="2026-09-25T13:00:00Z")
    errors = validate_reservation_request(r, snap(), ReservationCriteria(max_reservation_lifetime_seconds=3600))
    assert "reservation_lifetime_exceeded" in errors
