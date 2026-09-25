from market.strategy_lifecycle import (
    InMemoryStrategyLifecycle, StrategyLifecycleCriteria, StrategyLifecycleError,
    StrategyLifecycleEvidence, StrategyLifecycleStage, fingerprint, initial_state,
)


def ev(**kwargs):
    base = dict(
        profitability_status="VALID", statistical_status="WITHIN_SAMPLE_STABILITY",
        oos_status="OOS_STABILITY", regime_session_status="STABLE",
        economic_edge_status="EDGE_CANDIDATE", forward_status="OUTCOME_CONFIRMED",
        eligibility_status="ELIGIBLE", monitoring_status="HEALTHY",
        degradation_status="HEALTHY", fingerprints={"x": "fp"},
    )
    base.update(kwargs)
    return StrategyLifecycleEvidence(**base)


def test_initial_state_is_idea():
    state = initial_state("s1", "1.0", changed_at="t")
    assert state.stage is StrategyLifecycleStage.IDEA
    assert state.lifecycle_fingerprint


def test_validated_progression_requires_evidence():
    repo = InMemoryStrategyLifecycle()
    repo.create(initial_state("s1", "1.0", changed_at="t"))
    repo.transition("s1", StrategyLifecycleStage.RESEARCH, changed_at="t1", reason="research")
    repo.transition("s1", StrategyLifecycleStage.VALIDATING, changed_at="t2", reason="validate", evidence=ev())
    assert repo.get("s1").stage is StrategyLifecycleStage.VALIDATING


def test_validation_gate_blocks_missing_oos():
    repo = InMemoryStrategyLifecycle(); repo.create(initial_state("s1", "1.0", changed_at="t"))
    repo.transition("s1", StrategyLifecycleStage.RESEARCH, changed_at="t1", reason="research")
    try:
        repo.transition("s1", StrategyLifecycleStage.VALIDATING, changed_at="t2", reason="validate", evidence=ev(oos_status=None))
        assert False
    except StrategyLifecycleError as exc:
        assert str(exc) == "evidence_gate_failed:oos_evidence"


def test_forward_gate_requires_forward_evidence():
    repo = InMemoryStrategyLifecycle(); repo.create(initial_state("s1", "1.0", changed_at="t"))
    repo.transition("s1", StrategyLifecycleStage.RESEARCH, changed_at="t1", reason="research")
    repo.transition("s1", StrategyLifecycleStage.VALIDATING, changed_at="t2", reason="validate", evidence=ev())
    try:
        repo.transition("s1", StrategyLifecycleStage.FORWARD, changed_at="t3", reason="forward", evidence=ev(forward_status=None))
        assert False
    except StrategyLifecycleError as exc:
        assert str(exc) == "evidence_gate_failed:forward_evidence"


def test_eligibility_gate_requires_eligible_status():
    repo = InMemoryStrategyLifecycle(); repo.create(initial_state("s1", "1.0", changed_at="t"))
    for stage, t in [(StrategyLifecycleStage.RESEARCH, "1"), (StrategyLifecycleStage.VALIDATING, "2"), (StrategyLifecycleStage.FORWARD, "3")]:
        repo.transition("s1", stage, changed_at=t, reason="step", evidence=ev())
    try:
        repo.transition("s1", StrategyLifecycleStage.ELIGIBLE, changed_at="4", reason="eligible", evidence=ev(eligibility_status="INELIGIBLE"))
        assert False
    except StrategyLifecycleError as exc:
        assert str(exc) == "evidence_gate_failed:eligibility"


def test_limited_live_requires_healthy_monitoring_and_degradation():
    repo = InMemoryStrategyLifecycle(); repo.create(initial_state("s1", "1.0", changed_at="t"))
    for stage, t in [(StrategyLifecycleStage.RESEARCH, "1"), (StrategyLifecycleStage.VALIDATING, "2"), (StrategyLifecycleStage.FORWARD, "3"), (StrategyLifecycleStage.ELIGIBLE, "4")]:
        repo.transition("s1", stage, changed_at=t, reason="step", evidence=ev())
    try:
        repo.transition("s1", StrategyLifecycleStage.LIMITED_LIVE, changed_at="5", reason="deploy", evidence=ev(monitoring_status="WARNING"))
        assert False
    except StrategyLifecycleError as exc:
        assert str(exc) == "evidence_gate_failed:monitoring"


def test_strategy_can_move_backward_for_revalidation():
    repo = InMemoryStrategyLifecycle(); repo.create(initial_state("s1", "1.0", changed_at="t"))
    repo.transition("s1", StrategyLifecycleStage.RESEARCH, changed_at="1", reason="research")
    repo.transition("s1", StrategyLifecycleStage.VALIDATING, changed_at="2", reason="validate", evidence=ev())
    repo.transition("s1", StrategyLifecycleStage.RESEARCH, changed_at="3", reason="new_evidence_needed")
    assert repo.get("s1").stage is StrategyLifecycleStage.RESEARCH


def test_degraded_can_return_to_validation_not_live_directly():
    repo = InMemoryStrategyLifecycle(); repo.create(initial_state("s1", "1.0", changed_at="t"))
    for stage, t in [(StrategyLifecycleStage.RESEARCH, "1"), (StrategyLifecycleStage.VALIDATING, "2"), (StrategyLifecycleStage.FORWARD, "3"), (StrategyLifecycleStage.ELIGIBLE, "4"), (StrategyLifecycleStage.LIMITED_LIVE, "5")]:
        repo.transition("s1", stage, changed_at=t, reason="step", evidence=ev())
    repo.transition("s1", StrategyLifecycleStage.DEGRADED, changed_at="6", reason="degradation")
    repo.transition("s1", StrategyLifecycleStage.VALIDATING, changed_at="7", reason="revalidate", evidence=ev())
    assert repo.get("s1").stage is StrategyLifecycleStage.VALIDATING


def test_retired_is_terminal():
    repo = InMemoryStrategyLifecycle(); repo.create(initial_state("s1", "1.0", changed_at="t"))
    repo.transition("s1", StrategyLifecycleStage.RETIRED, changed_at="1", reason="retire")
    try:
        repo.transition("s1", StrategyLifecycleStage.RESEARCH, changed_at="2", reason="restart")
        assert False
    except StrategyLifecycleError as exc:
        assert str(exc) == "invalid_transition:RETIRED->RESEARCH"


def test_history_is_append_only():
    repo = InMemoryStrategyLifecycle(); repo.create(initial_state("s1", "1.0", changed_at="t"))
    repo.transition("s1", StrategyLifecycleStage.RESEARCH, changed_at="1", reason="research")
    history = repo.history("s1")
    assert len(history) == 2
    assert history[0].stage is StrategyLifecycleStage.IDEA


def test_fingerprint_is_deterministic():
    state = initial_state("s1", "1.0", changed_at="t")
    assert fingerprint(state) == state.lifecycle_fingerprint


def test_fingerprint_mismatch_rejected():
    state = initial_state("s1", "1.0", changed_at="t")
    bad = state.__class__(**{**state.__dict__, "lifecycle_fingerprint": "bad"})
    try:
        from market.strategy_lifecycle import validate_state
        validate_state(bad)
        assert False
    except StrategyLifecycleError as exc:
        assert str(exc) == "lifecycle_fingerprint_mismatch"


def test_custom_criteria_can_disable_specific_requirement():
    repo = InMemoryStrategyLifecycle(); repo.create(initial_state("s1", "1.0", changed_at="t"))
    repo.transition("s1", StrategyLifecycleStage.RESEARCH, changed_at="1", reason="research")
    criteria = StrategyLifecycleCriteria(require_regime_session_stability=False)
    repo.transition("s1", StrategyLifecycleStage.VALIDATING, changed_at="2", reason="validate", evidence=ev(regime_session_status=None), criteria=criteria)
    assert repo.get("s1").stage is StrategyLifecycleStage.VALIDATING


def test_no_execution_authority():
    repo = InMemoryStrategyLifecycle()
    assert not hasattr(repo, "buy")
    assert not hasattr(repo, "sell")
    assert not hasattr(repo, "execute")
    assert not hasattr(repo, "authorize")


def test_unknown_strategy_rejected():
    repo = InMemoryStrategyLifecycle()
    try:
        repo.transition("missing", StrategyLifecycleStage.RESEARCH, changed_at="t", reason="x")
        assert False
    except StrategyLifecycleError as exc:
        assert str(exc) == "strategy_not_found"
