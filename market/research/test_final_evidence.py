"""Tests for Phase 2.17 final research evidence integration."""
from dataclasses import replace

import pytest

from .cohort import CohortStatus, ResearchCohortResult
from .final_evidence import (
    FinalEvidenceError,
    FinalEvidencePolicy,
    FinalEvidenceStatus,
    FinalResearchEvidence,
    FinalResearchEvidenceEngine,
    finalize_research_evidence,
)
from .portfolio import PortfolioRobustnessResult, PortfolioRobustnessStatus
from .promotion import PromotionStatus, ResearchPromotionResult


def promotion(status=PromotionStatus.PROMOTE_PAPER):
    return ResearchPromotionResult(
        status=status,
        eligible_for_paper=status == PromotionStatus.PROMOTE_PAPER,
        eligible_for_demo=False,
        checks=(),
        failures=() if status == PromotionStatus.PROMOTE_PAPER else ("promotion failed",),
        warnings=(),
        evidence_fingerprint="p" * 64,
        policy={},
        metadata={},
    )


def cohort(status=CohortStatus.PASS, symbols=("EURUSD", "GBPUSD")):
    return ResearchCohortResult(
        cohort_id="candidate-1",
        status=status,
        total_cases=3,
        completed_cases=3,
        symbols=symbols,
        intervals=("5m",),
        symbol_case_counts={s: 1 for s in symbols},
        interval_case_counts={"5m": 3},
        symbol_interval_cells=tuple(f"{s}|5m" for s in symbols),
        duplicate_dataset_ids=(),
        duplicate_dataset_fingerprints=(),
        checks=(),
        failures=() if status == CohortStatus.PASS else ("cohort failed",),
        warnings=(),
        evidence_fingerprint="c" * 64,
        eligible_for_promotion=status == CohortStatus.PASS,
        policy={},
        metadata={},
    )


def portfolio(status=PortfolioRobustnessStatus.PASS, symbols=("EURUSD", "GBPUSD")):
    return PortfolioRobustnessResult(
        cohort_id="candidate-1",
        status=status,
        symbols=symbols,
        observed_pairs=("EURUSD|GBPUSD",),
        missing_pairs=(),
        max_abs_pair_correlation=0.20,
        weighted_average_abs_correlation=0.20,
        risk_concentration_fraction=0.50,
        effective_symbol_count=1.80,
        checks=(),
        failures=() if status == PortfolioRobustnessStatus.PASS else ("portfolio failed",),
        warnings=(),
        evidence_fingerprint="r" * 64,
        eligible_for_promotion=status == PortfolioRobustnessStatus.PASS,
        policy={},
        metadata={},
    )


def evidence(**kwargs):
    return FinalResearchEvidence(
        candidate_id=kwargs.get("candidate_id", "candidate-1"),
        promotion=kwargs.get("promotion", promotion()),
        cohort=kwargs.get("cohort", cohort()),
        portfolio=kwargs.get("portfolio", portfolio()),
    )


def test_complete_evidence_promotes_to_paper():
    result = finalize_research_evidence(evidence())
    assert result.status == FinalEvidenceStatus.PROMOTE_PAPER
    assert result.eligible_for_paper is True
    assert result.eligible_for_demo is False
    assert result.metadata["execution_authorization"] is False
    assert set(result.nested_fingerprints) == {"promotion", "cohort", "portfolio"}


def test_promotion_failure_holds():
    result = finalize_research_evidence(evidence(promotion=promotion(PromotionStatus.HOLD)))
    assert result.status == FinalEvidenceStatus.HOLD


def test_cohort_failure_holds():
    result = finalize_research_evidence(evidence(cohort=cohort(CohortStatus.HOLD)))
    assert result.status == FinalEvidenceStatus.HOLD


def test_portfolio_failure_holds():
    result = finalize_research_evidence(evidence(portfolio=portfolio(PortfolioRobustnessStatus.HOLD)))
    assert result.status == FinalEvidenceStatus.HOLD


def test_insufficient_cohort_data_is_insufficient():
    result = finalize_research_evidence(evidence(cohort=cohort(CohortStatus.INSUFFICIENT_DATA)))
    assert result.status == FinalEvidenceStatus.INSUFFICIENT_DATA


def test_candidate_cohort_identity_is_required():
    result = finalize_research_evidence(evidence(candidate_id="different"))
    assert result.status == FinalEvidenceStatus.HOLD
    assert any("identities do not match" in x for x in result.failures)


def test_symbol_set_mismatch_holds():
    result = finalize_research_evidence(
        evidence(portfolio=portfolio(symbols=("EURUSD", "USDJPY")))
    )
    assert result.status == FinalEvidenceStatus.HOLD


def test_portfolio_cohort_id_mismatch_rejected_at_bundle_creation():
    bad = replace(portfolio(), cohort_id="other")
    with pytest.raises(FinalEvidenceError):
        FinalResearchEvidence("candidate-1", promotion(), cohort(), bad)


def test_malformed_fingerprint_holds():
    bad = replace(cohort(), evidence_fingerprint="short")
    result = finalize_research_evidence(evidence(cohort=bad))
    assert result.status == FinalEvidenceStatus.HOLD


def test_optional_gates_can_be_disabled():
    policy = FinalEvidencePolicy(
        require_promotion_pass=False,
        require_cohort_pass=False,
        require_portfolio_pass=False,
        require_candidate_cohort_match=False,
        require_symbol_set_match=False,
        require_non_empty_evidence_fingerprints=False,
    )
    result = FinalResearchEvidenceEngine(policy).evaluate(
        evidence(promotion=promotion(PromotionStatus.HOLD))
    )
    assert result.status == FinalEvidenceStatus.PROMOTE_PAPER


def test_policy_rejects_non_boolean():
    with pytest.raises(FinalEvidenceError):
        FinalEvidencePolicy(require_cohort_pass=1)


def test_bundle_requires_valid_candidate_id():
    with pytest.raises(FinalEvidenceError):
        FinalResearchEvidence("", promotion(), cohort(), portfolio())


def test_result_fingerprint_is_deterministic():
    a = finalize_research_evidence(evidence())
    b = finalize_research_evidence(evidence())
    assert a.evidence_fingerprint == b.evidence_fingerprint


def test_warnings_are_propagated():
    warned = replace(cohort(), warnings=("cohort warning",))
    result = finalize_research_evidence(evidence(cohort=warned))
    assert "cohort warning" in result.warnings


def test_demo_is_never_authorized():
    result = finalize_research_evidence(evidence())
    assert result.eligible_for_demo is False
    assert result.metadata["demo_eligibility"] is False


def test_phase_metadata_prevents_execution_interpretation():
    result = finalize_research_evidence(evidence())
    assert result.metadata["broker_access"] is False
    assert result.metadata["order_placement"] is False
    assert result.metadata["paper_trading_authorization"] is False
