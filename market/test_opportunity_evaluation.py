from datetime import datetime, timedelta, timezone
import pytest

from market.opportunity_evaluation import (
    INSUFFICIENT_EVIDENCE,
    INVALID,
    QUALIFIED,
    QUALIFIED_WITH_LIMITATIONS,
    OpportunityEvaluationCriteria,
    evaluate_opportunity,
    summarize_opportunity_evidence,
)


def _record(i, *, ts="2026-01-01T00:00:00Z", cls="forward", regime="trend", session="London", strategy="trend", version="1.1.2", symbol="EURUSD", timeframe="15m", pnl=5.0, cost=0.5, risk=2.0):
    return {"trade_id": f"T{i}", "timestamp": ts, "evidence_class": cls, "strategy_id": strategy, "strategy_version": version, "symbol": symbol, "timeframe": timeframe, "regime": regime, "session": session, "realized_pnl": pnl, "total_costs": cost, "risk_amount": risk}


def _opportunity(**overrides):
    base = {"opportunity_id": "O1", "timestamp": "2026-02-01T00:00:00Z", "signal_timestamp": "2026-01-01T00:00:00Z", "context_timestamp": "2026-01-01T00:00:00Z", "symbol": "EURUSD", "timeframe": "15m", "direction": "LONG", "strategy_id": "trend", "strategy_version": "1.1.2", "regime": "trend", "session": "London", "evidence_class": "forward"}
    base.update(overrides)
    return base


def _evidence(n=10):
    return [_record(i) for i in range(n)]


def test_qualified_requires_declared_exact_context_and_coverage():
    result = evaluate_opportunity(_opportunity(), _evidence())
    assert result.status == QUALIFIED
    assert result.opportunity is not None
    assert result.opportunity.evidence.relevant_evidence_records == 10
    assert result.opportunity.qualification.complete is True


def test_future_evidence_is_never_used():
    records = _evidence(10)
    records[0]["timestamp"] = "2026-03-01T00:00:00Z"
    result = evaluate_opportunity(_opportunity(), records)
    assert result.opportunity.evidence.temporal_evidence_records == 9
    assert result.opportunity.evidence.relevant_evidence_records == 9
    assert result.status == QUALIFIED_WITH_LIMITATIONS


def test_future_signal_or_context_invalidates_point_in_time_integrity():
    result = evaluate_opportunity(_opportunity(signal_timestamp="2026-03-02T00:00:00Z"), _evidence())
    assert result.status == INVALID
    assert "signal_timestamp_after_opportunity" in result.limitations


def test_small_relevant_sample_is_limitation_not_success_claim():
    result = evaluate_opportunity(_opportunity(), _evidence(3))
    assert result.status == QUALIFIED_WITH_LIMITATIONS
    assert "relevant_evidence_sample_small" in result.limitations


def test_no_exact_context_is_insufficient():
    records = _evidence(10)
    for record in records:
        record["session"] = "Asia"
    result = evaluate_opportunity(_opportunity(), records)
    assert result.status == INSUFFICIENT_EVIDENCE
    assert "no_exact_context_evidence" in result.limitations


def test_missing_costs_are_not_zero():
    records = _evidence(10)
    for record in records:
        record.pop("total_costs")
    result = evaluate_opportunity(_opportunity(), records)
    assert result.status == QUALIFIED_WITH_LIMITATIONS
    assert result.opportunity.evidence.cost_covered_records == 0


def test_missing_risk_is_not_zero():
    records = _evidence(10)
    for record in records:
        record.pop("risk_amount")
    result = evaluate_opportunity(_opportunity(), records)
    assert result.status == QUALIFIED_WITH_LIMITATIONS
    assert result.opportunity.evidence.risk_covered_records == 0


def test_evidence_classes_are_separated():
    records = _evidence(10)
    records += [_record(i + 100, cls="live") for i in range(10)]
    result = evaluate_opportunity(_opportunity(), records)
    assert result.status == QUALIFIED
    assert result.opportunity.evidence.total_evidence_records == 20
    assert result.opportunity.evidence.relevant_evidence_records == 10


def test_strategy_and_market_identity_must_match():
    records = _evidence(10)
    records[0]["strategy_version"] = "9.9"
    records[1]["symbol"] = "GBPUSD"
    result = evaluate_opportunity(_opportunity(), records)
    assert result.opportunity.evidence.relevant_evidence_records == 8


def test_regime_and_session_are_part_of_relevance():
    records = _evidence(10)
    records[0]["regime"] = "range"
    records[1]["session"] = "New York"
    result = evaluate_opportunity(_opportunity(), records)
    assert result.opportunity.evidence.relevant_evidence_records == 8


def test_invalid_missing_identity_is_rejected():
    opportunity = _opportunity()
    opportunity.pop("strategy_version")
    result = evaluate_opportunity(opportunity, _evidence())
    assert result.status == INVALID
    assert "strategy_version" in result.limitations


def test_timezone_naive_timestamp_is_rejected():
    result = evaluate_opportunity(_opportunity(timestamp="2026-02-01T00:00:00"), _evidence())
    assert result.status == INVALID
    assert "valid_timezone_aware_timestamp" in result.limitations


def test_fingerprint_is_deterministic_for_reordered_evidence():
    records = _evidence()
    a = evaluate_opportunity(_opportunity(), records)
    b = evaluate_opportunity(_opportunity(), list(reversed(records)))
    assert a.evaluation_fingerprint == b.evaluation_fingerprint
    assert a.opportunity.evidence.evidence_fingerprint == b.opportunity.evidence.evidence_fingerprint


def test_query_adapter_is_read_only():
    class Query:
        def find(self, filters):
            assert filters == {"symbol": "EURUSD"}
            return _evidence()
    result = summarize_opportunity_evidence(Query(), _opportunity(), {"symbol": "EURUSD"})
    assert result.status == QUALIFIED
    assert not hasattr(result, "execute")
    assert not hasattr(result, "buy")


def test_query_adapter_requires_find():
    with pytest.raises(TypeError, match=r"find\(filters\)"):
        summarize_opportunity_evidence(object(), _opportunity())


def test_criteria_validation():
    with pytest.raises(ValueError):
        OpportunityEvaluationCriteria(min_relevant_evidence_records=0)
    with pytest.raises(ValueError):
        OpportunityEvaluationCriteria(min_relevant_evidence_records=True)


def test_custom_threshold_is_explicit_not_optimized():
    result = evaluate_opportunity(_opportunity(), _evidence(5), criteria=OpportunityEvaluationCriteria(min_relevant_evidence_records=5))
    assert result.status == QUALIFIED
