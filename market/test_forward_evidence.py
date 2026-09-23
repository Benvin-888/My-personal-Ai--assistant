from datetime import datetime, timezone

import pytest

from market.forward_evidence import (
    DECISION_LOCKED,
    EXECUTED,
    FORWARD_EVIDENCE_CLASS,
    OUTCOME_CONFIRMED,
    RECONCILIATION_PENDING,
    ForwardDecision,
    ForwardEvidence,
    ForwardOutcome,
    compare_forward_to_research,
)


def decision(**overrides):
    data = dict(
        forward_evidence_id="fe-1",
        opportunity_id="opp-1",
        opportunity_fingerprint="abc123",
        decision_timestamp=datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc),
        symbol="EURUSD",
        timeframe="15m",
        direction="LONG",
        strategy_id="trend_momentum",
        strategy_version="1.1.2",
        regime="TRENDING",
        session="LONDON",
        opportunity_status="QUALIFIED",
        economic_edge_status="EDGE_CANDIDATE",
        risk_amount=10.0,
        intended_entry=1.1000,
        intended_exit=1.1020,
        intended_stop=1.0990,
        intended_target=1.1020,
        expected_reward_risk=2.0,
    )
    data.update(overrides)
    return ForwardDecision(**data)


def outcome(**overrides):
    data = dict(
        outcome_timestamp=datetime(2026, 9, 23, 10, 30, tzinfo=timezone.utc),
        status="CONFIRMED",
        actual_entry=1.1001,
        actual_exit=1.1018,
        actual_fill_price=1.1001,
        slippage=0.0001,
        transaction_cost=0.25,
        financing_cost=0.0,
        realized_pnl=17.0,
        reconciliation_status="MATCHED",
    )
    data.update(overrides)
    return ForwardOutcome(**data)


def test_decision_is_forward_and_deterministically_fingerprinted():
    first = decision()
    second = decision()
    assert first.evidence_class == FORWARD_EVIDENCE_CLASS
    assert first.decision_fingerprint == second.decision_fingerprint


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        decision(decision_timestamp=datetime(2026, 9, 23, 10, 0))


def test_missing_numeric_values_are_allowed_but_invalid_values_are_rejected():
    assert decision(risk_amount=None).risk_amount is None
    with pytest.raises(ValueError):
        decision(risk_amount=float("nan"))


def test_lifecycle_preserves_immutable_decision():
    base = ForwardEvidence(decision())
    pending = base.mark_execution_pending()
    executed = pending.record_execution(outcome())
    assert base.lifecycle_status == DECISION_LOCKED
    assert pending.lifecycle_status != EXECUTED
    assert executed.decision == base.decision


def test_reconciliation_and_confirmation_require_execution():
    item = ForwardEvidence(decision()).mark_execution_pending().record_execution(outcome())
    item = item.mark_reconciliation_pending()
    confirmed = item.confirm_outcome()
    assert confirmed.lifecycle_status == OUTCOME_CONFIRMED
    assert confirmed.outcome.realized_pnl == 17.0


def test_invalid_lifecycle_transition_is_rejected():
    item = ForwardEvidence(decision())
    with pytest.raises(ValueError):
        item.mark_reconciliation_pending()
    with pytest.raises(ValueError):
        item.confirm_outcome()


def test_outcome_timestamp_must_be_timezone_aware():
    with pytest.raises(ValueError, match="timezone-aware"):
        outcome(outcome_timestamp=datetime(2026, 9, 23, 10, 30))


def test_evidence_fingerprint_changes_with_outcome():
    a = ForwardEvidence(decision()).mark_execution_pending().record_execution(outcome())
    b = ForwardEvidence(decision()).mark_execution_pending().record_execution(outcome(realized_pnl=18.0))
    assert a.evidence_fingerprint != b.evidence_fingerprint


def test_research_comparison_is_descriptive_only():
    result = compare_forward_to_research(
        {"expectancy": 0.2, "win_rate": 0.6, "realized_pnl": 10},
        {"expectancy": 0.4, "win_rate": 0.7, "realized_pnl": 25},
    )
    assert result["comparisons"]["expectancy"]["difference"] == pytest.approx(-0.2)
    assert "profit_factor_comparison_unavailable" in result["limitations"]


def test_terminal_failure_states_do_not_create_success():
    item = ForwardEvidence(decision()).terminal("EXECUTION_FAILED")
    assert item.lifecycle_status == "EXECUTION_FAILED"
    assert item.outcome is None


def test_confirmed_outcome_requires_actual_outcome_data():
    item = ForwardEvidence(decision()).mark_execution_pending().record_execution(outcome())
    confirmed = item.confirm_outcome()
    assert confirmed.outcome.status == "CONFIRMED"


def test_wrong_evidence_class_is_rejected():
    with pytest.raises(ValueError, match="forward"):
        decision(evidence_class="historical")


def test_outcome_unknown_is_terminal():
    item = ForwardEvidence(decision()).terminal("OUTCOME_UNKNOWN")
    assert item.lifecycle_status == "OUTCOME_UNKNOWN"
