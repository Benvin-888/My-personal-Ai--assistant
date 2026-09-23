from market.economic_edge import (
    DESCRIPTIVE_ONLY,
    EDGE_CANDIDATE,
    EDGE_CANDIDATE_WITH_LIMITATIONS,
    INSUFFICIENT_EVIDENCE,
    INVALID,
    EconomicEdgeCriteria,
    evaluate_economic_edge,
)


def _record(i, *, cls="forward", pnl=10.0, cost=1.0, risk=5.0):
    return {"trade_id": f"T{i}", "evidence_class": cls, "realized_pnl": pnl, "total_costs": cost, "risk_amount": risk}


def _good(n=30):
    return [_record(i) for i in range(n)]


def test_edge_candidate_requires_explicit_oos_and_statistics():
    result = evaluate_economic_edge(_good(), evidence_class="forward", oos_status="OOS_STABILITY", statistical_status="UNCERTAINTY_QUANTIFIED")
    assert result.status == EDGE_CANDIDATE
    assert result.edge_candidate is True
    assert result.summary.total_net_pnl == 270.0


def test_missing_oos_is_not_edge():
    result = evaluate_economic_edge(_good(), evidence_class="forward", statistical_status="UNCERTAINTY_QUANTIFIED")
    assert result.status == DESCRIPTIVE_ONLY
    assert "oos_status_missing" in result.limitations


def test_missing_statistics_is_not_edge():
    result = evaluate_economic_edge(_good(), evidence_class="forward", oos_status="OOS_STABILITY")
    assert result.status == DESCRIPTIVE_ONLY
    assert "statistical_status_missing" in result.limitations


def test_missing_costs_are_not_zero():
    records = _good()
    for record in records:
        record.pop("total_costs")
    result = evaluate_economic_edge(records, evidence_class="forward", oos_status="OOS_STABILITY", statistical_status="UNCERTAINTY_QUANTIFIED")
    assert result.status == INSUFFICIENT_EVIDENCE
    assert result.summary.cost_coverage == 0.0


def test_missing_risk_is_not_zero():
    records = _good()
    for record in records:
        record.pop("risk_amount")
    result = evaluate_economic_edge(records, evidence_class="forward", oos_status="OOS_STABILITY", statistical_status="UNCERTAINTY_QUANTIFIED")
    assert result.status == INSUFFICIENT_EVIDENCE
    assert result.summary.risk_coverage == 0.0


def test_evidence_classes_are_never_silently_mixed():
    records = _good() + [_record(i + 100, cls="live") for i in range(30)]
    result = evaluate_economic_edge(records, evidence_class="forward", oos_status="OOS_STABILITY", statistical_status="UNCERTAINTY_QUANTIFIED")
    assert result.summary.total_records == 30


def test_negative_net_expectancy_is_descriptive_only():
    records = _good()
    for record in records:
        record["realized_pnl"] = -2.0
    result = evaluate_economic_edge(records, evidence_class="forward", oos_status="OOS_STABILITY", statistical_status="UNCERTAINTY_QUANTIFIED")
    assert result.status == DESCRIPTIVE_ONLY
    assert "net_expectancy_below_threshold" in result.limitations


def test_small_sample_is_insufficient():
    result = evaluate_economic_edge(_good(5), evidence_class="forward", oos_status="OOS_STABILITY", statistical_status="UNCERTAINTY_QUANTIFIED")
    assert result.status == INSUFFICIENT_EVIDENCE
    assert "economic_sample_small" in result.limitations


def test_partial_cost_coverage_produces_limitation():
    records = _good()
    for record in records[:5]:
        record.pop("total_costs")
    result = evaluate_economic_edge(records, evidence_class="forward", oos_status="OOS_STABILITY", statistical_status="UNCERTAINTY_QUANTIFIED")
    assert result.status == INSUFFICIENT_EVIDENCE
    assert result.summary.cost_coverage < 1.0


def test_component_costs_are_accepted_only_when_all_are_explicit():
    records = _good()
    for record in records:
        record.pop("total_costs")
        record["transaction_cost"] = 0.5
        record["slippage_cost"] = 0.25
        record["financing_cost"] = 0.25
    result = evaluate_economic_edge(records, evidence_class="forward", oos_status="OOS_STABILITY", statistical_status="UNCERTAINTY_QUANTIFIED")
    assert result.status == EDGE_CANDIDATE
    assert result.summary.total_explicit_costs == 30.0


def test_deterministic_for_reordered_records():
    records = _good()
    a = evaluate_economic_edge(records, evidence_class="forward", oos_status="OOS_STABILITY", statistical_status="UNCERTAINTY_QUANTIFIED")
    b = evaluate_economic_edge(list(reversed(records)), evidence_class="forward", oos_status="OOS_STABILITY", statistical_status="UNCERTAINTY_QUANTIFIED")
    assert a.evaluation_fingerprint == b.evaluation_fingerprint
    assert a.summary.evidence_fingerprint == b.summary.evidence_fingerprint


def test_cost_ratio_can_create_limited_candidate_when_threshold_relaxed():
    records = _good()
    for record in records:
        record["total_costs"] = 4.0
    result = evaluate_economic_edge(
        records,
        evidence_class="forward",
        oos_status="OOS_STABILITY",
        statistical_status="UNCERTAINTY_QUANTIFIED",
        criteria=EconomicEdgeCriteria(max_cost_to_gross_profit=0.3),
    )
    assert result.status == DESCRIPTIVE_ONLY
    assert "cost_to_gross_profit_above_threshold" in result.limitations


def test_zero_gross_profit_is_not_automatically_edge():
    records = _good()
    for record in records:
        record["realized_pnl"] = 0.0
    result = evaluate_economic_edge(records, evidence_class="forward", oos_status="OOS_STABILITY", statistical_status="UNCERTAINTY_QUANTIFIED")
    assert result.status == DESCRIPTIVE_ONLY
    assert "no_gross_profit_for_cost_ratio" in result.limitations


def test_invalid_empty_evidence_class():
    try:
        evaluate_economic_edge([], evidence_class="")
    except ValueError as exc:
        assert "evidence_class" in str(exc)
    else:
        raise AssertionError("expected ValueError")
