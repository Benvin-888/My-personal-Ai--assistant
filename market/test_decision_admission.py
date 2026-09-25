import pytest

from market.decision_admission import (
    AdmissionCriteria,
    AdmissionStatus,
    DecisionContext,
    DecisionStage,
    final_safety_recheck_passes,
    evaluate_decision_admission,
    decision_admission_is_not_execution_request,
)


def _context(**changes):
    data = dict(
        decision_id="DEC-1", observed_at="2026-09-25T10:00:00Z",
        symbol="EURUSD", timeframe="5m", strategy_id="trend_momentum",
        strategy_version="1.1.2", candidate_id="CAND-1", direction="LONG",
        quantity=1.0, risk_amount=10.0,
        market_fingerprint="m", opportunity_fingerprint="o",
        evidence_fingerprint="e", economic_edge_fingerprint="ee",
        eligibility_fingerprint="el", portfolio_fingerprint="p",
        risk_fingerprint="r", monitoring_fingerprint="mo",
        degradation_fingerprint="d", safety_fingerprint="s",
    )
    data.update(changes)
    return DecisionContext(**data)


def _result(status="APPROVED", **changes):
    data = {"status": status, "passed": True, "reasons": (), "fingerprint": status.lower()}
    data.update(changes)
    return data


def _run(**changes):
    return evaluate_decision_admission(
        _context(), AdmissionCriteria(),
        market=_result(), opportunity=_result("QUALIFIED"), economic_edge=_result("EDGE_CANDIDATE"),
        eligibility=_result("ELIGIBLE"), portfolio=_result("APPROVED"), risk=_result("APPROVED"),
        monitoring=_result("HEALTHY"), degradation=_result("HEALTHY"),
        safety=_result("ARMED", state="ARMED"), final_safety_recheck=_result("ARMED", state="ARMED"),
        **changes,
    )


def test_all_gates_admit_without_execution_authority():
    result = _run()
    assert result.status is AdmissionStatus.ADMITTED
    assert result.execution_admission_allowed is True
    assert result.execution_authorized is False
    assert decision_admission_is_not_execution_request(result)


def test_market_failure_rejects():
    result = _run()
    result = evaluate_decision_admission(_context(), AdmissionCriteria(), market=_result("REJECTED", passed=False, reasons=("market_invalid",)), opportunity=_result("QUALIFIED"), economic_edge=_result("EDGE_CANDIDATE"), eligibility=_result("ELIGIBLE"), portfolio=_result(), risk=_result(), monitoring=_result("HEALTHY"), degradation=_result("HEALTHY"), safety=_result("ARMED", state="ARMED"), final_safety_recheck=_result("ARMED", state="ARMED"))
    assert result.status is AdmissionStatus.REJECTED
    assert "market_invalid" in result.blocking_reasons


def test_eligibility_failure_rejects():
    result = evaluate_decision_admission(_context(), AdmissionCriteria(), market=_result(), opportunity=_result("QUALIFIED"), economic_edge=_result("EDGE_CANDIDATE"), eligibility=_result("INELIGIBLE", passed=False, reasons=("not_eligible",)), portfolio=_result(), risk=_result(), monitoring=_result("HEALTHY"), degradation=_result("HEALTHY"), safety=_result("ARMED", state="ARMED"), final_safety_recheck=_result("ARMED", state="ARMED"))
    assert result.status is AdmissionStatus.REJECTED


def test_safety_failure_blocks():
    result = evaluate_decision_admission(_context(), AdmissionCriteria(), market=_result(), opportunity=_result("QUALIFIED"), economic_edge=_result("EDGE_CANDIDATE"), eligibility=_result("ELIGIBLE"), portfolio=_result(), risk=_result(), monitoring=_result("HEALTHY"), degradation=_result("HEALTHY"), safety=_result("LOCKED", passed=False, state="LOCKED", reasons=("unknown_outcomes",)), final_safety_recheck=_result("LOCKED", passed=False, state="LOCKED"))
    assert result.status is AdmissionStatus.BLOCKED
    assert result.execution_admission_allowed is False


def test_missing_final_safety_recheck_blocks():
    result = evaluate_decision_admission(_context(), AdmissionCriteria(), market=_result(), opportunity=_result("QUALIFIED"), economic_edge=_result("EDGE_CANDIDATE"), eligibility=_result("ELIGIBLE"), portfolio=_result(), risk=_result(), monitoring=_result("HEALTHY"), degradation=_result("HEALTHY"), safety=_result("ARMED", state="ARMED"))
    assert result.status is AdmissionStatus.BLOCKED
    assert "fresh_safety_recheck_required" in result.blocking_reasons


def test_degradation_blocks_by_default():
    result = evaluate_decision_admission(_context(), AdmissionCriteria(), market=_result(), opportunity=_result("QUALIFIED"), economic_edge=_result("EDGE_CANDIDATE"), eligibility=_result("ELIGIBLE"), portfolio=_result(), risk=_result(), monitoring=_result("HEALTHY"), degradation=_result("DEGRADED", passed=False, reasons=("expectancy_deteriorated",)), safety=_result("ARMED", state="ARMED"), final_safety_recheck=_result("ARMED", state="ARMED"))
    assert result.status is AdmissionStatus.REJECTED
    assert "expectancy_deteriorated" in result.blocking_reasons


def test_insufficient_evidence_is_distinguished():
    result = evaluate_decision_admission(_context(), AdmissionCriteria(), market=_result(), opportunity=_result("QUALIFIED"), economic_edge=_result("INSUFFICIENT_EVIDENCE", passed=False, reasons=("not_enough_forward_records",)), eligibility=_result("ELIGIBLE"), portfolio=_result(), risk=_result(), monitoring=_result("HEALTHY"), degradation=_result("HEALTHY"), safety=_result("ARMED", state="ARMED"), final_safety_recheck=_result("ARMED", state="ARMED"))
    assert result.status is AdmissionStatus.INSUFFICIENT_EVIDENCE


def test_expired_decision_is_not_admitted():
    result = _run(elapsed_seconds=10.1)
    assert result.status is AdmissionStatus.EXPIRED
    assert result.execution_admission_allowed is False


def test_expiration_boundary_is_valid():
    result = _run(elapsed_seconds=10.0)
    assert result.status is AdmissionStatus.ADMITTED


def test_invalid_context_fails_closed():
    result = evaluate_decision_admission(_context(decision_id=""), AdmissionCriteria(), market=_result(), opportunity=_result("QUALIFIED"), economic_edge=_result("EDGE_CANDIDATE"), eligibility=_result("ELIGIBLE"), portfolio=_result(), risk=_result(), monitoring=_result("HEALTHY"), degradation=_result("HEALTHY"), safety=_result("ARMED", state="ARMED"), final_safety_recheck=_result("ARMED", state="ARMED"))
    assert result.status is AdmissionStatus.INVALID
    assert result.execution_admission_allowed is False


def test_final_safety_recheck_requires_armed_state():
    result = _run()
    assert final_safety_recheck_passes(result, _result("ARMED", state="ARMED")) is True
    assert final_safety_recheck_passes(result, _result("LOCKED", passed=False, state="LOCKED")) is False


def test_non_admitted_decision_cannot_pass_final_recheck():
    result = _run(elapsed_seconds=11.0)
    assert final_safety_recheck_passes(result, _result("ARMED", state="ARMED")) is False


def test_deterministic_fingerprint():
    a = _run()
    b = _run()
    assert a.decision_fingerprint == b.decision_fingerprint


def test_fingerprint_changes_when_evidence_changes():
    a = _run()
    b = evaluate_decision_admission(_context(evidence_fingerprint="changed"), AdmissionCriteria(), market=_result(), opportunity=_result("QUALIFIED"), economic_edge=_result("EDGE_CANDIDATE"), eligibility=_result("ELIGIBLE"), portfolio=_result(), risk=_result(), monitoring=_result("HEALTHY"), degradation=_result("HEALTHY"), safety=_result("ARMED", state="ARMED"), final_safety_recheck=_result("ARMED", state="ARMED"))
    assert a.decision_fingerprint != b.decision_fingerprint


def test_stage_order_is_deterministic():
    result = _run()
    assert [stage.stage for stage in result.stages] == list(DecisionStage)


def test_brain_like_inputs_are_data_only():
    result = _run()
    assert result.execution_authorized is False
    assert not hasattr(result, "buy")


def test_negative_quantity_fails_closed():
    result = evaluate_decision_admission(_context(quantity=-1), AdmissionCriteria(), market=_result(), opportunity=_result("QUALIFIED"), economic_edge=_result("EDGE_CANDIDATE"), eligibility=_result("ELIGIBLE"), portfolio=_result(), risk=_result(), monitoring=_result("HEALTHY"), degradation=_result("HEALTHY"), safety=_result("ARMED", state="ARMED"), final_safety_recheck=_result("ARMED", state="ARMED"))
    assert result.status is AdmissionStatus.INVALID


def test_invalid_ttl_fails_closed():
    result = _run()
    result = evaluate_decision_admission(_context(), AdmissionCriteria(decision_ttl_seconds=0), market=_result(), opportunity=_result("QUALIFIED"), economic_edge=_result("EDGE_CANDIDATE"), eligibility=_result("ELIGIBLE"), portfolio=_result(), risk=_result(), monitoring=_result("HEALTHY"), degradation=_result("HEALTHY"), safety=_result("ARMED", state="ARMED"), final_safety_recheck=_result("ARMED", state="ARMED"))
    assert result.status is AdmissionStatus.INVALID


def test_final_recheck_is_independent_of_initial_safety_fingerprint():
    result = _run()
    assert final_safety_recheck_passes(result, _result("ARMED", state="ARMED", fingerprint="fresh")) is True
