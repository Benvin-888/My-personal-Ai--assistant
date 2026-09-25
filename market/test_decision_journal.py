from market.decision_journal import (
    DecisionJournalEntry,
    DecisionOutcomeLink,
    InMemoryDecisionJournal,
    JournalError,
    fingerprint,
    validate_entry,
)


def make_entry(**changes):
    data = dict(
        decision_id="D-1", candidate_id="C-1", timestamp="2026-09-25T10:00:00Z",
        symbol="EURUSD", timeframe="5m", strategy_id="trend_momentum", strategy_version="1.1.2",
        market_fingerprint="m", opportunity_fingerprint="o", economic_edge_fingerprint="e",
        eligibility_fingerprint="el", portfolio_fingerprint="p", risk_fingerprint="r",
        monitoring_fingerprint="mo", degradation_fingerprint="d", safety_fingerprint="s",
        decision_fingerprint="decision-fp", decision_status="ADMITTED", admission_status="ADMITTED",
        blocking_reasons=(), decision_context={"observed": "only"}, criteria_versions={"2.67": "2.67.0"},
    )
    data.update(changes)
    return DecisionJournalEntry(**data)


def test_append_and_get_preserves_decision_snapshot():
    repo = InMemoryDecisionJournal()
    entry = make_entry()
    assert repo.append(entry) == "D-1"
    record = repo.get("D-1")
    assert record is not None
    assert record.entry == entry
    assert record.outcome is None


def test_duplicate_identical_append_is_idempotent():
    repo = InMemoryDecisionJournal()
    entry = make_entry()
    repo.append(entry)
    assert repo.append(entry) == "D-1"


def test_decision_snapshot_is_immutable():
    repo = InMemoryDecisionJournal()
    repo.append(make_entry())
    try:
        repo.append(make_entry(decision_status="REJECTED"))
        assert False
    except JournalError as exc:
        assert str(exc) == "immutable_decision_conflict"


def test_outcome_is_separate_from_decision_snapshot():
    repo = InMemoryDecisionJournal()
    repo.append(make_entry())
    outcome = DecisionOutcomeLink(
        decision_id="D-1", linked_at="2026-09-25T10:01:00Z",
        execution_request_id="REQ-1", execution_outcome_id="OUT-1",
        reconciliation_id="REC-1", forward_evidence_id="FWD-1",
        final_outcome="CONFIRMED", realized_pnl=12.5,
    )
    repo.link_outcome(outcome)
    record = repo.get("D-1")
    assert record.entry.decision_status == "ADMITTED"
    assert record.outcome is not None
    assert record.outcome.realized_pnl == 12.5


def test_unknown_outcome_does_not_become_zero():
    repo = InMemoryDecisionJournal()
    repo.append(make_entry())
    repo.link_outcome(DecisionOutcomeLink(decision_id="D-1", linked_at="t"))
    assert repo.get("D-1").outcome.realized_pnl is None


def test_outcome_conflict_is_rejected():
    repo = InMemoryDecisionJournal()
    repo.append(make_entry())
    first = DecisionOutcomeLink(decision_id="D-1", linked_at="t", realized_pnl=1.0)
    repo.link_outcome(first)
    try:
        repo.link_outcome(DecisionOutcomeLink(decision_id="D-1", linked_at="t", realized_pnl=2.0))
        assert False
    except JournalError as exc:
        assert str(exc) == "immutable_outcome_conflict"


def test_missing_decision_blocks_outcome_link():
    repo = InMemoryDecisionJournal()
    try:
        repo.link_outcome(DecisionOutcomeLink(decision_id="missing", linked_at="t"))
        assert False
    except JournalError as exc:
        assert str(exc) == "decision_not_found"


def test_invalid_required_field_rejected():
    try:
        validate_entry(make_entry(symbol=""))
        assert False
    except JournalError as exc:
        assert str(exc) == "missing_symbol"


def test_non_finite_values_rejected():
    try:
        validate_entry(make_entry(decision_context={"x": float("nan")}))
        assert False
    except JournalError as exc:
        assert str(exc) == "non_finite_value"


def test_outcome_fingerprint_is_deterministic():
    outcome = DecisionOutcomeLink(decision_id="D-1", linked_at="t", realized_pnl=4.0)
    repo = InMemoryDecisionJournal()
    repo.append(make_entry())
    repo.link_outcome(outcome)
    saved = repo.get("D-1").outcome
    assert saved.outcome_fingerprint == fingerprint(DecisionOutcomeLink(decision_id="D-1", linked_at="t", realized_pnl=4.0))


def test_no_execution_authority():
    repo = InMemoryDecisionJournal()
    assert not hasattr(repo, "buy")
    assert not hasattr(repo, "sell")
    assert not hasattr(repo, "execute")
    assert not hasattr(repo, "authorize")
