from __future__ import annotations

import pytest

from .final_evidence import FinalEvidenceStatus, FinalResearchEvidenceResult
from .paper_readiness import (
    PaperReadinessEngine,
    PaperReadinessError,
    PaperReadinessInput,
    PaperReadinessPolicy,
    PaperReadinessStatus,
    assess_paper_readiness,
)


def final_evidence(status=FinalEvidenceStatus.PROMOTE_PAPER, eligible=True):
    return FinalResearchEvidenceResult(
        status=status,
        eligible_for_paper=eligible,
        eligible_for_demo=False,
        candidate_id="candidate-1",
        cohort_id="cohort-1",
        checks=(),
        failures=(),
        warnings=(),
        evidence_fingerprint="a" * 64,
        nested_fingerprints={"promotion": "b" * 64},
        policy={},
        metadata={},
    )


def ready_input(**overrides):
    values = dict(
        environment_id="paper-test",
        market_data_ready=True,
        market_data_age_seconds=10.0,
        risk_ready=True,
        configured_risk_fraction_per_trade=0.005,
        configured_total_risk_fraction=0.02,
        configured_reward_risk=1.5,
        point_in_time_execution=True,
        no_lookahead_verified=True,
        friction_model_ready=True,
        paper_isolated=True,
        broker_execution_disabled=True,
        metadata={"data_source": "test", "execution_model": "bar_replay_v1"},
    )
    values.update(overrides)
    return PaperReadinessInput(**values)


def test_default_ready():
    result = assess_paper_readiness(final_evidence(), ready_input())
    assert result.status is PaperReadinessStatus.READY
    assert result.ready_for_paper_research is True
    assert result.eligible_for_demo is False
    assert result.metadata["execution_authorization"] is False


def test_final_evidence_failure_holds():
    result = assess_paper_readiness(final_evidence(FinalEvidenceStatus.HOLD, False), ready_input())
    assert result.status is PaperReadinessStatus.HOLD
    assert result.ready_for_paper_research is False


def test_market_data_not_ready_is_insufficient():
    result = assess_paper_readiness(final_evidence(), ready_input(market_data_ready=False))
    assert result.status is PaperReadinessStatus.INSUFFICIENT_DATA


def test_stale_market_data_holds():
    result = assess_paper_readiness(final_evidence(), ready_input(market_data_age_seconds=61))
    assert result.status is PaperReadinessStatus.HOLD


def test_risk_fraction_ceiling():
    result = assess_paper_readiness(final_evidence(), ready_input(configured_risk_fraction_per_trade=0.011))
    assert result.status is PaperReadinessStatus.HOLD
    assert any("risk configuration" in x for x in result.failures)


def test_total_risk_ceiling():
    result = assess_paper_readiness(final_evidence(), ready_input(configured_total_risk_fraction=0.021))
    assert result.status is PaperReadinessStatus.HOLD


def test_reward_risk_floor():
    result = assess_paper_readiness(final_evidence(), ready_input(configured_reward_risk=1.49))
    assert result.status is PaperReadinessStatus.HOLD


def test_point_in_time_required():
    result = assess_paper_readiness(final_evidence(), ready_input(point_in_time_execution=False))
    assert result.status is PaperReadinessStatus.HOLD


def test_no_lookahead_required():
    result = assess_paper_readiness(final_evidence(), ready_input(no_lookahead_verified=False))
    assert result.status is PaperReadinessStatus.HOLD


def test_friction_required():
    result = assess_paper_readiness(final_evidence(), ready_input(friction_model_ready=False))
    assert result.status is PaperReadinessStatus.HOLD


def test_isolation_required():
    result = assess_paper_readiness(final_evidence(), ready_input(paper_isolated=False))
    assert result.status is PaperReadinessStatus.HOLD


def test_broker_execution_must_be_disabled():
    result = assess_paper_readiness(final_evidence(), ready_input(broker_execution_disabled=False))
    assert result.status is PaperReadinessStatus.HOLD


def test_warning_when_metadata_is_incomplete():
    result = assess_paper_readiness(final_evidence(), ready_input(metadata={}))
    assert result.status is PaperReadinessStatus.READY
    assert len(result.warnings) == 2


def test_policy_can_disable_optional_gates():
    policy = PaperReadinessPolicy(require_friction_model=False)
    result = assess_paper_readiness(final_evidence(), ready_input(friction_model_ready=False), policy)
    assert result.status is PaperReadinessStatus.READY


def test_custom_policy_limits_are_applied():
    policy = PaperReadinessPolicy(maximum_market_data_age_seconds=5)
    result = assess_paper_readiness(final_evidence(), ready_input(market_data_age_seconds=6), policy)
    assert result.status is PaperReadinessStatus.HOLD


def test_deterministic_fingerprint():
    a = assess_paper_readiness(final_evidence(), ready_input())
    b = assess_paper_readiness(final_evidence(), ready_input())
    assert a.evidence_fingerprint == b.evidence_fingerprint


def test_to_dict_is_serializable():
    result = assess_paper_readiness(final_evidence(), ready_input())
    data = result.to_dict()
    assert data["status"] == "READY"
    assert data["eligible_for_demo"] is False
    assert data["metadata"]["broker_access"] is False


def test_invalid_environment_id():
    with pytest.raises(PaperReadinessError):
        ready_input(environment_id="")


def test_invalid_boolean_rejected():
    with pytest.raises(PaperReadinessError):
        ready_input(paper_isolated=1)


def test_negative_age_rejected():
    with pytest.raises(PaperReadinessError):
        ready_input(market_data_age_seconds=-1)


def test_engine_rejects_wrong_types():
    engine = PaperReadinessEngine()
    with pytest.raises(PaperReadinessError):
        engine.evaluate(object(), ready_input())
    with pytest.raises(PaperReadinessError):
        engine.evaluate(final_evidence(), object())
