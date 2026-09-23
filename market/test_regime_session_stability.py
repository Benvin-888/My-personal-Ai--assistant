import pytest

from market.regime_session_stability import (
    CONCENTRATED,
    DESCRIPTIVE_ONLY,
    INVALID_EVIDENCE,
    INSUFFICIENT_DATA,
    STABLE,
    UNSTABLE,
    RegimeSessionStabilityCriteria,
    evaluate_regime_session_stability,
    summarize_trade_evidence_regime_session,
)


def _records(count=10, *, evidence_class="forward"):
    regimes = ("trend", "range")
    sessions = ("London", "New York")
    records = []
    for i in range(count * 2):
        records.append({
            "trade_id": f"T-{i}",
            "regime": regimes[i // count],
            "session": sessions[i // count],
            "evidence_class": evidence_class,
            "realized_pnl": 4.0 if i % 4 else -1.0,
            "total_costs": 0.5,
            "risk_amount": 2.0,
        })
    return records


def test_empty_is_insufficient():
    result = evaluate_regime_session_stability([])
    assert result.status == INSUFFICIENT_DATA
    assert result.total_records == 0


def test_stability_requires_multiple_complete_cohorts():
    result = evaluate_regime_session_stability(_records())
    assert result.status == STABLE
    assert result.regime.status == STABLE
    assert result.session.status == STABLE
    assert len(result.matrix) == 2
    assert result.evidence_class == "forward"


def test_missing_cost_or_risk_is_not_zero():
    records = _records()
    for record in records:
        record.pop("total_costs")
        record.pop("risk_amount")
    result = evaluate_regime_session_stability(records)
    assert result.status == DESCRIPTIVE_ONLY
    assert result.regime.complete_costs is False
    assert result.session.complete_risk is False


def test_small_cohorts_are_descriptive_only():
    result = evaluate_regime_session_stability(
        _records(3),
        criteria=RegimeSessionStabilityCriteria(min_records_per_cohort=10),
    )
    assert result.status == DESCRIPTIVE_ONLY
    assert result.regime.sufficient_sample is False


def test_unstable_cohort_distribution_is_reported_without_selection():
    records = _records()
    for record in records[:10]:
        record["realized_pnl"] = -5.0
    result = evaluate_regime_session_stability(records)
    assert result.status in {UNSTABLE, CONCENTRATED}
    assert result.regime.profitable_cohort_fraction == pytest.approx(0.5)


def test_missing_labels_are_explicit_and_not_dropped():
    records = _records()
    for record in records[:10]:
        record.pop("session")
    result = evaluate_regime_session_stability(records)
    assert result.status == DESCRIPTIVE_ONLY
    assert result.session.missing_label_cohorts == 1
    assert "session_label_missing" in result.limitations


def test_mixed_evidence_classes_are_never_combined():
    records = _records()
    records[-1]["evidence_class"] = "live"
    result = evaluate_regime_session_stability(records)
    assert result.status == INVALID_EVIDENCE
    assert "mixed_evidence_classes_not_combined" in result.limitations


def test_requested_evidence_class_filters_before_analysis():
    records = _records() + _records(evidence_class="live")
    result = evaluate_regime_session_stability(records, evidence_class="forward")
    assert result.status == STABLE
    assert result.evidence_class == "forward"
    assert result.total_records == 20


def test_fingerprint_is_deterministic():
    records = _records()
    a = evaluate_regime_session_stability(records)
    b = evaluate_regime_session_stability(list(reversed(records)))
    assert a.evidence_fingerprint == b.evidence_fingerprint


def test_query_adapter_is_read_only():
    class Query:
        def find(self, filters):
            assert filters == {"symbol": "EURUSD"}
            return _records()

    result = summarize_trade_evidence_regime_session(Query(), {"symbol": "EURUSD"})
    assert result.total_records == 20
    assert not hasattr(result, "execute")
    assert not hasattr(result, "buy")


def test_query_adapter_requires_find():
    with pytest.raises(TypeError, match=r"find\(filters\)"):
        summarize_trade_evidence_regime_session(object())


def test_invalid_criteria_are_rejected():
    with pytest.raises(ValueError):
        RegimeSessionStabilityCriteria(min_records_per_cohort=0)
    with pytest.raises(ValueError):
        RegimeSessionStabilityCriteria(min_profitable_cohort_fraction=1.5)


def test_missing_evidence_class_is_not_treated_as_a_valid_stability_class():
    records = _records(evidence_class="forward")
    for record in records:
        record.pop("evidence_class")
    result = evaluate_regime_session_stability(records)
    assert result.status == INVALID_EVIDENCE
    assert "evidence_class_missing" in result.limitations
