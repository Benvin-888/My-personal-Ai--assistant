from market.capital_risk_reservation import ReservationCriteria, ReservationLedgerSnapshot, ReservationLedgerStatus
from market.capital_risk_reservation_admission import (
    CapitalRiskReservationLedger,
    ReservationAdmissionRequest,
    reservation_admission_is_not_execution_authorization,
)


def snap():
    return ReservationLedgerSnapshot(
        observed_at="2026-09-25T10:00:00Z", account_scope="acct",
        capital_budget=5000.0, risk_budget=200.0,
        committed_capital=1000.0, committed_risk=20.0, reservations=(),
    )


def req(rid="r1", capital=1000.0, risk=40.0, decision="d1"):
    return ReservationAdmissionRequest(
        reservation_id=rid, created_at="2026-09-25T10:00:00Z",
        account_scope="acct", strategy_id="trend_momentum", strategy_version="1.1.2",
        capital_amount=capital, risk_amount=risk,
        expires_at="2026-09-25T11:00:00Z", source_decision_id=decision,
    )


def test_first_admission_consumes_capacity():
    ledger = CapitalRiskReservationLedger()
    result = ledger.admit(req(), snapshot=snap())
    assert result.status is ReservationLedgerStatus.AVAILABLE
    assert result.reservation is not None
    assert ledger.revision == 1


def test_second_admission_sees_first_reservation():
    ledger = CapitalRiskReservationLedger()
    assert ledger.admit(req(), snapshot=snap()).status is ReservationLedgerStatus.AVAILABLE
    result = ledger.admit(req("r2", capital=3500.0, risk=140.0), snapshot=snap())
    assert result.status is ReservationLedgerStatus.LIMITED
    assert "capital_capacity_exceeded" in result.reasons


def test_risk_capacity_is_checked_independently():
    ledger = CapitalRiskReservationLedger()
    result = ledger.admit(req(capital=100.0, risk=190.0), snapshot=snap())
    assert result.status is ReservationLedgerStatus.LIMITED
    assert "risk_capacity_exceeded" in result.reasons


def test_missing_budget_fails_closed():
    ledger = CapitalRiskReservationLedger()
    s = snap()
    s = ReservationLedgerSnapshot(**{**s.__dict__, "risk_budget": None})
    result = ledger.admit(req(), snapshot=s)
    assert result.status is ReservationLedgerStatus.INSUFFICIENT_DATA
    assert result.reservation is None


def test_duplicate_id_cannot_be_admitted_twice():
    ledger = CapitalRiskReservationLedger()
    assert ledger.admit(req(), snapshot=snap()).status is ReservationLedgerStatus.AVAILABLE
    result = ledger.admit(req(), snapshot=snap())
    assert result.status is ReservationLedgerStatus.INVALID
    assert "duplicate_reservation_id" in result.reasons


def test_revision_conflict_fails_closed():
    ledger = CapitalRiskReservationLedger()
    assert ledger.admit(req(), snapshot=snap()).ledger_revision == 1
    result = ledger.admit(req("r2"), snapshot=snap(), expected_revision=0)
    assert result.status is ReservationLedgerStatus.INVALID
    assert "ledger_revision_conflict" in result.reasons


def test_account_scope_mismatch_is_rejected():
    ledger = CapitalRiskReservationLedger()
    bad = ReservationAdmissionRequest(**{**req().__dict__, "account_scope": "other"})
    result = ledger.admit(bad, snapshot=snap())
    assert result.status is ReservationLedgerStatus.INVALID
    assert "reservation_account_scope_mismatch" in result.reasons


def test_missing_decision_id_is_rejected():
    ledger = CapitalRiskReservationLedger()
    result = ledger.admit(req(decision=None), snapshot=snap())
    assert result.status is ReservationLedgerStatus.INVALID
    assert "source_decision_id_missing" in result.reasons


def test_missing_expiry_is_rejected():
    ledger = CapitalRiskReservationLedger()
    result = ledger.admit(ReservationAdmissionRequest(**{**req().__dict__, "expires_at": None}), snapshot=snap())
    assert result.status is ReservationLedgerStatus.INVALID
    assert "expiry_missing" in result.reasons


def test_strategy_capital_limit_is_enforced():
    ledger = CapitalRiskReservationLedger(criteria=ReservationCriteria(max_strategy_reserved_capital=1200.0))
    assert ledger.admit(req(capital=1000.0), snapshot=snap()).status is ReservationLedgerStatus.AVAILABLE
    result = ledger.admit(req("r2", capital=300.0), snapshot=snap())
    assert result.status is ReservationLedgerStatus.LIMITED
    assert "strategy_reserved_capital_exceeded" in result.reasons


def test_strategy_risk_limit_is_enforced():
    ledger = CapitalRiskReservationLedger(criteria=ReservationCriteria(max_strategy_reserved_risk=50.0))
    assert ledger.admit(req(risk=40.0), snapshot=snap()).status is ReservationLedgerStatus.AVAILABLE
    result = ledger.admit(req("r2", risk=20.0), snapshot=snap())
    assert result.status is ReservationLedgerStatus.LIMITED
    assert "strategy_reserved_risk_exceeded" in result.reasons


def test_terminal_removal_is_explicit_and_revisioned():
    ledger = CapitalRiskReservationLedger()
    result = ledger.admit(req(), snapshot=snap())
    reservation = result.reservation
    assert reservation is not None
    from market.capital_risk_reservation import apply_reservation_event, ReservationStatus
    terminal = apply_reservation_event(reservation, ReservationStatus.RELEASED, "2026-09-25T10:30:00Z")
    ledger._reservations[reservation.reservation_id] = terminal
    old_revision = ledger.revision
    assert ledger.remove_terminal(reservation.reservation_id) is True
    assert ledger.revision == old_revision + 1
    assert ledger.remove_terminal(reservation.reservation_id) is False


def test_non_execution_authority():
    ledger = CapitalRiskReservationLedger()
    result = ledger.admit(req(), snapshot=snap())
    assert reservation_admission_is_not_execution_authorization(result)
    assert result.execution_authorized is False
