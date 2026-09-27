import pytest

from market.capital_risk_reservation_admission import (
    ReservationAdmissionResult,
    fingerprint as reservation_admission_fingerprint,
)
from market.decision_admission import (
    AdmissionCriteria,
    DecisionContext,
    evaluate_decision_admission,
)
from market.decision_reservation_integration import (
    bind_reservation_to_decision,
)
from market.capital_risk_reservation import make_reservation
from market.execution_request_bridge import (
    ApprovedExecutionIntent,
    ExecutionContractCriteria,
    ExecutionRequestBridgeStatus,
    execution_request_bridge_is_not_execution_authorization,
    execution_contract_fingerprint,
    materialize_execution_request,
)


def _decision(**changes):
    data = dict(
        decision_id="DEC-1", observed_at="2026-09-26T10:00:00Z",
        symbol="EURUSD", timeframe="5m", strategy_id="trend_momentum",
        strategy_version="1.1.2", candidate_id="CAND-1", direction="LONG",
        quantity=1.0, risk_amount=10.0,
        market_fingerprint="m", opportunity_fingerprint="o",
        evidence_fingerprint="e", economic_edge_fingerprint="ee",
        eligibility_fingerprint="el", portfolio_fingerprint="p", risk_fingerprint="r",
        monitoring_fingerprint="mo", degradation_fingerprint="d", safety_fingerprint="s",
    )
    data.update(changes)
    context = DecisionContext(**data)

    def result(status="APPROVED", **extra):
        value = {"status": status, "passed": True, "reasons": (), "fingerprint": status.lower()}
        value.update(extra)
        return value

    return evaluate_decision_admission(
        context,
        AdmissionCriteria(decision_ttl_seconds=10.0),
        market=result(),
        opportunity=result("QUALIFIED"),
        economic_edge=result("EDGE_CANDIDATE"),
        eligibility=result("ELIGIBLE"),
        portfolio=result(),
        risk=result(),
        monitoring=result("HEALTHY"),
        degradation=result("HEALTHY"),
        safety=result("ARMED", state="ARMED"),
        final_safety_recheck=result("ARMED", state="ARMED"),
    )


def _binding(decision=None, *, reservation_risk=10.0, account_scope="demo"):
    decision = decision or _decision()
    reservation = make_reservation(
        reservation_id="R-1",
        created_at="2026-09-26T10:00:00Z",
        account_scope=account_scope,
        strategy_id=decision.strategy_id,
        strategy_version=decision.strategy_version,
        capital_amount=10.0,
        risk_amount=reservation_risk,
        expires_at="2026-09-26T10:00:20Z",
        source_decision_id=decision.decision_id,
    )
    reasons = ("reservation_admitted",)
    source_snapshot_fingerprint = "snapshot-1"
    admission_data = {
        "status": "AVAILABLE",
        "reservation_id": reservation.reservation_id,
        "reasons": reasons,
        "revision": 0,
        "source_snapshot_fingerprint": source_snapshot_fingerprint,
    }
    admission = ReservationAdmissionResult(
        status=type("Status", (), {"value": "AVAILABLE"})(),
        reservation=reservation,
        reasons=reasons,
        ledger_revision=0,
        source_snapshot_fingerprint=source_snapshot_fingerprint,
        admission_fingerprint=reservation_admission_fingerprint(admission_data),
        execution_authorized=False,
    )
    return bind_reservation_to_decision(
        decision,
        admission,
        account_scope=account_scope,
        now="2026-09-26T10:00:01Z",
    )


def _criteria(**changes):
    values = dict(
        broker="deriv",
        execution_mode="LIVE",
        account_scope="demo",
        currency="USD",
        order_type="CONTRACT",
        contract_type="CALL",
        approved_stake=10.0,
    )
    values.update(changes)
    return ExecutionContractCriteria(**values)


def _intent(**changes):
    values = dict(
        broker="deriv",
        execution_mode="LIVE",
        account_scope="demo",
        symbol="EURUSD",
        direction="BUY",
        quantity=1.0,
        stake=10.0,
        currency="USD",
        order_type="CONTRACT",
        requested_at="2026-09-26T10:00:01Z",
        expires_at="2026-09-26T10:00:05Z",
        contract_type="CALL",
    )
    values.update(changes)
    return ApprovedExecutionIntent(**values)


def _materialize(**intent_changes):
    decision = _decision()
    binding = _binding(decision)
    return materialize_execution_request(
        decision,
        binding,
        _intent(**intent_changes),
        request_id="REQ-1",
        now="2026-09-26T10:00:02Z",
        criteria=_criteria(),
    )


def test_materializes_only_when_every_contract_is_consistent():
    result = _materialize()
    assert result.status is ExecutionRequestBridgeStatus.MATERIALIZED
    assert result.execution_admission_allowed is True
    assert result.request is not None
    assert result.request.symbol == "EURUSD"
    assert result.request.direction == "BUY"
    assert result.request.execution_contract_fingerprint == execution_contract_fingerprint(_criteria())
    assert result.request.execution_authorized is False


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("symbol", "GBPUSD", "intent_symbol_mismatch"),
        ("direction", "SELL", "intent_direction_mismatch"),
        ("quantity", 2.0, "intent_quantity_mismatch"),
        ("broker", "other", "intent_broker_mismatch"),
        ("execution_mode", "DEMO", "intent_execution_mode_mismatch"),
        ("currency", "EUR", "intent_currency_mismatch"),
        ("order_type", "OTHER", "intent_order_type_mismatch"),
        ("contract_type", "PUT", "intent_contract_type_mismatch"),
        ("stake", 20.0, "intent_stake_mismatch"),
    ],
)
def test_rejects_execution_term_tampering(field, value, reason):
    result = _materialize(**{field: value})
    assert result.status is ExecutionRequestBridgeStatus.INVALID
    assert reason in result.reasons
    assert result.request is None


def test_rejects_policy_account_scope_mismatch():
    result = materialize_execution_request(
        _decision(), _binding(), _intent(), request_id="REQ-1", now="2026-09-26T10:00:02Z",
        criteria=_criteria(account_scope="real"),
    )
    assert result.status is ExecutionRequestBridgeStatus.INVALID
    assert "intent_account_scope_policy_mismatch" in result.reasons


def test_rejects_tampered_decision_fingerprint():
    decision = _decision()
    tampered = type(decision)(**{**decision.__dict__, "decision_fingerprint": "0" * 64})
    result = materialize_execution_request(
        tampered, _binding(decision), _intent(), request_id="REQ-1", now="2026-09-26T10:00:02Z", criteria=_criteria()
    )
    assert result.status is ExecutionRequestBridgeStatus.INVALID
    assert "decision_fingerprint_mismatch" in result.reasons


def test_rejects_tampered_reservation_fingerprint():
    decision = _decision()
    binding = _binding(decision)
    tampered = type(binding.binding)(**{**binding.binding.__dict__, "reservation_fingerprint": "0" * 64})
    tampered = type(binding)(**{**binding.__dict__, "binding": tampered})
    result = materialize_execution_request(
        decision, tampered, _intent(), request_id="REQ-1", now="2026-09-26T10:00:02Z", criteria=_criteria()
    )
    assert result.status is ExecutionRequestBridgeStatus.INVALID
    assert "binding_fingerprint_mismatch" in result.reasons


def test_rejects_tampered_binding_fingerprint():
    decision = _decision()
    binding = _binding(decision)
    tampered_binding = type(binding.binding)(**{**binding.binding.__dict__, "binding_fingerprint": "0" * 64})
    tampered = type(binding)(**{**binding.__dict__, "binding": tampered_binding})
    result = materialize_execution_request(
        decision, tampered, _intent(), request_id="REQ-1", now="2026-09-26T10:00:02Z", criteria=_criteria()
    )
    assert result.status is ExecutionRequestBridgeStatus.INVALID
    assert "binding_fingerprint_mismatch" in result.reasons


def test_rejects_expired_request():
    result = _materialize(expires_at="2026-09-26T10:00:02Z")
    assert result.status is ExecutionRequestBridgeStatus.EXPIRED
    assert "request_expired" in result.reasons


def test_rejects_request_after_decision_expiry():
    result = materialize_execution_request(
        _decision(), _binding(), _intent(expires_at="2026-09-26T10:00:20Z", requested_at="2026-09-26T10:00:11Z"),
        request_id="REQ-1", now="2026-09-26T10:00:11Z", criteria=_criteria(),
    )
    assert result.status is ExecutionRequestBridgeStatus.EXPIRED
    assert "request_after_decision_expiry" in result.reasons


def test_rejects_reservation_expiry_after_request():
    decision = _decision()
    binding = _binding(decision)
    result = materialize_execution_request(
        decision, binding, _intent(expires_at="2026-09-26T10:00:25Z"),
        request_id="REQ-1", now="2026-09-26T10:00:02Z", criteria=_criteria(),
    )
    assert result.status is ExecutionRequestBridgeStatus.EXPIRED
    assert "request_expiry_after_reservation_expiry" in result.reasons


def test_rejects_stake_that_does_not_match_reserved_risk():
    result = materialize_execution_request(
        _decision(), _binding(reservation_risk=20.0), _intent(stake=10.0),
        request_id="REQ-1", now="2026-09-26T10:00:02Z", criteria=_criteria(),
    )
    assert result.status is ExecutionRequestBridgeStatus.REJECTED
    assert "approved_stake_reservation_risk_mismatch" in result.reasons


def test_rejects_blocked_decision():
    data = {
        "decision_id": "DEC-1", "observed_at": "2026-09-26T10:00:00Z",
        "symbol": "EURUSD", "timeframe": "5m", "strategy_id": "trend_momentum",
        "strategy_version": "1.1.2", "candidate_id": "CAND-1", "direction": "LONG",
        "quantity": 1.0, "risk_amount": 10.0,
        "market_fingerprint": "m", "opportunity_fingerprint": "o",
        "evidence_fingerprint": "e", "economic_edge_fingerprint": "ee",
        "eligibility_fingerprint": "el", "portfolio_fingerprint": "p", "risk_fingerprint": "r",
        "monitoring_fingerprint": "mo", "degradation_fingerprint": "d", "safety_fingerprint": "s",
    }
    context = DecisionContext(**data)
    def result(status="APPROVED", **extra):
        value = {"status": status, "passed": True, "reasons": (), "fingerprint": status.lower()}
        value.update(extra)
        return value
    blocked = evaluate_decision_admission(
        context, AdmissionCriteria(),
        market=result(), opportunity=result("QUALIFIED"), economic_edge=result("EDGE_CANDIDATE"),
        eligibility=result("ELIGIBLE"), portfolio=result(), risk=result(), monitoring=result("HEALTHY"),
        degradation=result("HEALTHY"), safety=result("LOCKED", passed=False, state="LOCKED"),
        final_safety_recheck=result("LOCKED", passed=False, state="LOCKED"),
    )
    result = materialize_execution_request(
        blocked, _binding(_decision()), _intent(), request_id="REQ-1", now="2026-09-26T10:00:02Z", criteria=_criteria()
    )
    assert result.status is ExecutionRequestBridgeStatus.BLOCKED
    assert result.request is None


def test_rejects_invalid_terms_without_resizing():
    result = _materialize(direction="HOLD", quantity=0)
    assert result.status is ExecutionRequestBridgeStatus.INVALID
    assert "direction_invalid" in result.reasons
    assert "quantity_invalid" in result.reasons
    assert result.request is None


def test_request_fingerprint_changes_with_trade_terms():
    a = _materialize().request
    # A changed approved policy must create a different contract fingerprint;
    # the original request cannot be silently reinterpreted under it.
    b = materialize_execution_request(
        _decision(), _binding(), _intent(), request_id="REQ-2", now="2026-09-26T10:00:02Z",
        criteria=_criteria(approved_stake=11.0),
    )
    assert a is not None
    assert b.request is None


def test_execution_authority_is_always_false():
    result = _materialize()
    assert result.execution_authorized is False
    assert execution_request_bridge_is_not_execution_authorization(result)
