from market.capital_risk_reservation import ReservationLedgerSnapshot, ReservationLedgerStatus
from market.capital_risk_reservation_admission import CapitalRiskReservationLedger, ReservationAdmissionRequest
from market.decision_admission import AdmissionCriteria, AdmissionStatus, DecisionContext, evaluate_decision_admission
from market.decision_reservation_integration import (
    DecisionReservationStatus,
    bind_reservation_to_decision,
    decision_reservation_is_not_execution_authorization,
    fingerprint,
)


def _decision():
    context = DecisionContext(
        decision_id="D-1", observed_at="2026-09-26T10:00:00Z",
        symbol="EURUSD", timeframe="5m", strategy_id="trend_momentum",
        strategy_version="1.1.2", candidate_id="C-1", direction="LONG",
        quantity=1.0, risk_amount=40.0,
        market_fingerprint="m", opportunity_fingerprint="o", evidence_fingerprint="e",
        economic_edge_fingerprint="ee", eligibility_fingerprint="el", portfolio_fingerprint="p",
        risk_fingerprint="r", monitoring_fingerprint="mo", degradation_fingerprint="d", safety_fingerprint="s",
    )

    def result(status="APPROVED", **changes):
        data = {"status": status, "passed": True, "reasons": (), "fingerprint": status.lower()}
        data.update(changes)
        return data

    return evaluate_decision_admission(
        context, AdmissionCriteria(),
        market=result(), opportunity=result("QUALIFIED"), economic_edge=result("EDGE_CANDIDATE"),
        eligibility=result("ELIGIBLE"), portfolio=result(), risk=result(), monitoring=result("HEALTHY"),
        degradation=result("HEALTHY"), safety=result("ARMED", state="ARMED"),
        final_safety_recheck=result("ARMED", state="ARMED"),
    )


def _reservation(decision_id="D-1", risk=40.0, rid="R-1"):
    ledger = CapitalRiskReservationLedger()
    snapshot = ReservationLedgerSnapshot(
        observed_at="2026-09-26T10:00:00Z", account_scope="acct",
        capital_budget=5000.0, risk_budget=200.0, committed_capital=1000.0,
        committed_risk=20.0, reservations=(),
    )
    request = ReservationAdmissionRequest(
        reservation_id=rid, created_at="2026-09-26T10:00:00Z", account_scope="acct",
        strategy_id="trend_momentum", strategy_version="1.1.2", capital_amount=1000.0,
        risk_amount=risk, expires_at="2026-09-26T11:00:00Z", source_decision_id=decision_id,
    )
    return ledger.admit(request, snapshot=snapshot)


def test_valid_reservation_binds_to_admitted_decision():
    result = bind_reservation_to_decision(_decision(), _reservation(), account_scope="acct", now="2026-09-26T10:05:00Z")
    assert result.status is DecisionReservationStatus.BOUND
    assert result.execution_admission_allowed is True
    assert result.binding is not None
    assert result.binding.decision_id == "D-1"
    assert result.binding.reservation_id == "R-1"
    assert result.binding.binding_fingerprint == fingerprint(result.binding.__class__(**{**result.binding.__dict__, "binding_fingerprint": ""}))


def test_decision_id_mismatch_fails_closed():
    result = bind_reservation_to_decision(_decision(), _reservation(decision_id="D-OTHER"), account_scope="acct", now="2026-09-26T10:05:00Z")
    assert result.status is DecisionReservationStatus.REJECTED
    assert "reservation_decision_id_mismatch" in result.reasons
    assert result.execution_admission_allowed is False


def test_strategy_version_mismatch_fails_closed():
    admission = _reservation()
    reservation = admission.reservation
    assert reservation is not None
    from dataclasses import replace
    bad = replace(reservation, strategy_version="9.9.9", reservation_fingerprint="")
    from market.capital_risk_reservation import fingerprint as reservation_fingerprint
    bad = replace(bad, reservation_fingerprint=reservation_fingerprint(bad))
    bad_result = type(admission)(
        status=ReservationLedgerStatus.AVAILABLE, reservation=bad, reasons=admission.reasons,
        ledger_revision=admission.ledger_revision, source_snapshot_fingerprint=admission.source_snapshot_fingerprint,
        admission_fingerprint=admission.admission_fingerprint, execution_authorized=False,
    )
    result = bind_reservation_to_decision(_decision(), bad_result, account_scope="acct", now="2026-09-26T10:05:00Z")
    assert result.status is DecisionReservationStatus.REJECTED
    assert "reservation_strategy_version_mismatch" in result.reasons


def test_risk_amount_mismatch_fails_closed():
    result = bind_reservation_to_decision(_decision(), _reservation(risk=39.0), account_scope="acct", now="2026-09-26T10:05:00Z")
    assert result.status is DecisionReservationStatus.REJECTED
    assert "reservation_risk_amount_mismatch" in result.reasons


def test_missing_reservation_is_insufficient_data():
    admission = _reservation()
    empty = type(admission)(
        status=ReservationLedgerStatus.INSUFFICIENT_DATA, reservation=None, reasons=("capacity_unavailable",),
        ledger_revision=admission.ledger_revision, source_snapshot_fingerprint=admission.source_snapshot_fingerprint,
        admission_fingerprint=admission.admission_fingerprint, execution_authorized=False,
    )
    result = bind_reservation_to_decision(_decision(), empty, account_scope="acct", now="2026-09-26T10:05:00Z")
    assert result.status is DecisionReservationStatus.INSUFFICIENT_DATA
    assert result.execution_admission_allowed is False


def test_expired_reservation_is_not_bound():
    result = bind_reservation_to_decision(_decision(), _reservation(), account_scope="acct", now="2026-09-26T11:00:00Z")
    assert result.status is DecisionReservationStatus.EXPIRED
    assert "reservation_expired" in result.reasons


def test_non_admitted_decision_cannot_bind():
    decision = _decision()
    from dataclasses import replace
    decision = replace(decision, status=AdmissionStatus.BLOCKED, execution_admission_allowed=False)
    result = bind_reservation_to_decision(decision, _reservation(), account_scope="acct", now="2026-09-26T10:05:00Z")
    assert result.status is DecisionReservationStatus.BLOCKED
    assert result.execution_admission_allowed is False


def test_account_scope_mismatch_fails_closed():
    result = bind_reservation_to_decision(_decision(), _reservation(), account_scope="other", now="2026-09-26T10:05:00Z")
    assert result.status is DecisionReservationStatus.REJECTED
    assert "reservation_account_scope_mismatch" in result.reasons


def test_missing_expiry_check_time_fails_closed():
    result = bind_reservation_to_decision(_decision(), _reservation(), account_scope="acct")
    assert result.status is DecisionReservationStatus.INVALID
    assert "reservation_expiry_check_time_missing" in result.reasons


def test_non_active_reservation_is_rejected():
    admission = _reservation()
    from dataclasses import replace
    from market.capital_risk_reservation import ReservationStatus, fingerprint as reservation_fingerprint
    reservation = replace(admission.reservation, status=ReservationStatus.RELEASED, reservation_fingerprint="")
    reservation = replace(reservation, reservation_fingerprint=reservation_fingerprint(reservation))
    changed = type(admission)(
        status=ReservationLedgerStatus.AVAILABLE, reservation=reservation, reasons=admission.reasons,
        ledger_revision=admission.ledger_revision, source_snapshot_fingerprint=admission.source_snapshot_fingerprint,
        admission_fingerprint=admission.admission_fingerprint, execution_authorized=False,
    )
    result = bind_reservation_to_decision(_decision(), changed, account_scope="acct", now="2026-09-26T10:05:00Z")
    assert result.status is DecisionReservationStatus.REJECTED
    assert "reservation_not_active" in result.reasons


def test_execution_authority_remains_false():
    result = bind_reservation_to_decision(_decision(), _reservation(), account_scope="acct", now="2026-09-26T10:05:00Z")
    assert decision_reservation_is_not_execution_authorization(result)
    assert result.execution_authorized is False
    assert not hasattr(result, "buy")


def test_binding_fingerprint_is_deterministic():
    a = bind_reservation_to_decision(_decision(), _reservation(), account_scope="acct", now="2026-09-26T10:05:00Z")
    b = bind_reservation_to_decision(_decision(), _reservation(), account_scope="acct", now="2026-09-26T10:05:00Z")
    assert a.binding is not None and b.binding is not None
    assert a.binding.binding_fingerprint == b.binding.binding_fingerprint


def test_source_provenance_is_preserved():
    admission = _reservation()
    result = bind_reservation_to_decision(_decision(), admission, account_scope="acct", now="2026-09-26T10:05:00Z")
    assert result.binding is not None
    assert result.binding.source_snapshot_fingerprint == admission.source_snapshot_fingerprint
    assert result.binding.reservation_admission_fingerprint == admission.admission_fingerprint
    assert result.binding.decision_fingerprint == _decision().decision_fingerprint
