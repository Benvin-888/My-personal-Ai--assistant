import pytest

from .statistics import (
    BootstrapResult, MultipleTestingResult, ResearchStatisticsError, SelectionBiasAudit,
    SelectionAuditStatus, StatisticalStatus, StatisticalValidationPolicy, bootstrap_mean,
    multiple_testing, validate_statistics,
)


def test_bootstrap_is_deterministic():
    a = bootstrap_mean([1, 2, 3, 4, 5], resamples=500, seed=7)
    b = bootstrap_mean([1, 2, 3, 4, 5], resamples=500, seed=7)
    assert a.to_dict() == b.to_dict()
    assert isinstance(a, BootstrapResult)
    assert a.lower_bound <= a.sample_mean <= a.upper_bound


def test_bootstrap_positive_sample_has_high_positive_fraction():
    result = bootstrap_mean([1.0] * 20, resamples=300, seed=1)
    assert result.positive_fraction == 1.0


def test_bootstrap_rejects_small_resample_count():
    with pytest.raises(ResearchStatisticsError):
        bootstrap_mean([1, 2], resamples=99)


def test_bootstrap_rejects_invalid_confidence():
    with pytest.raises(ResearchStatisticsError):
        bootstrap_mean([1, 2], confidence_level=1.0)


def test_multiple_testing_bonferroni():
    result = multiple_testing([0.001, 0.02, 0.8], alpha=0.05)
    assert isinstance(result, MultipleTestingResult)
    assert result.bonferroni_p_values == (0.003, 0.06, 1.0)
    assert result.bonferroni_rejections == (True, False, False)


def test_multiple_testing_bh_is_monotone_after_adjustment():
    result = multiple_testing([0.01, 0.04, 0.03, 0.9])
    assert all(0.0 <= p <= 1.0 for p in result.bh_p_values)
    assert result.bh_rejections[0] is True


def test_multiple_testing_rejects_invalid_p_values():
    with pytest.raises(ResearchStatisticsError):
        multiple_testing([-0.1, 0.2])


def test_selection_audit_burden_is_deterministic():
    audit = SelectionBiasAudit(
        candidate_count=7, selection_metric="net_pnl", selection_direction="MAXIMIZE",
        holdout_locked_before_selection=True, independent_confirmation=True,
        selected_candidate_id="case-7",
    )
    assert audit.status == SelectionAuditStatus.CONTROLLED
    assert audit.effective_candidate_burden > 0
    assert audit.to_dict()["candidate_count"] == 7


def test_controlled_selection_requires_locked_holdout():
    with pytest.raises(ResearchStatisticsError):
        SelectionBiasAudit(
            candidate_count=2, selection_metric="return", selection_direction="MAXIMIZE",
            holdout_locked_before_selection=False, independent_confirmation=False,
            status=SelectionAuditStatus.CONTROLLED,
        )


def test_selection_direction_is_validated():
    with pytest.raises(ResearchStatisticsError):
        SelectionBiasAudit(
            candidate_count=2, selection_metric="return", selection_direction="BEST",
            holdout_locked_before_selection=True, independent_confirmation=False,
        )


def test_validation_passes_with_sufficient_positive_data_and_locked_holdout():
    audit = SelectionBiasAudit(
        candidate_count=3, selection_metric="net_pnl", selection_direction="MAXIMIZE",
        holdout_locked_before_selection=True, independent_confirmation=True,
    )
    result = validate_statistics([1.0] * 30, selection_audit=audit, resamples=300)
    assert result.status == StatisticalStatus.PASS
    assert result.eligible_for_research_promotion is True
    assert not result.failures


def test_validation_fails_small_sample():
    audit = SelectionBiasAudit(
        candidate_count=1, selection_metric="net_pnl", selection_direction="MAXIMIZE",
        holdout_locked_before_selection=True, independent_confirmation=True,
    )
    result = validate_statistics([1.0] * 10, selection_audit=audit, resamples=300)
    assert result.status == StatisticalStatus.FAIL
    assert result.eligible_for_research_promotion is False


def test_validation_requires_selection_audit_by_default():
    result = validate_statistics([1.0] * 30, resamples=300)
    assert result.status == StatisticalStatus.FAIL
    assert any("selection-bias" in item for item in result.failures)


def test_validation_can_allow_missing_selection_audit():
    policy = StatisticalValidationPolicy(require_holdout_locked_selection=False)
    result = validate_statistics([1.0] * 30, policy=policy, resamples=300)
    assert result.status == StatisticalStatus.PASS
    assert result.warnings


def test_validation_can_require_independent_confirmation():
    audit = SelectionBiasAudit(
        candidate_count=2, selection_metric="net_pnl", selection_direction="MAXIMIZE",
        holdout_locked_before_selection=True, independent_confirmation=False,
    )
    policy = StatisticalValidationPolicy(require_independent_confirmation=True)
    result = validate_statistics([1.0] * 30, policy=policy, selection_audit=audit, resamples=300)
    assert result.status == StatisticalStatus.FAIL


def test_negative_distribution_fails_bootstrap_fraction():
    audit = SelectionBiasAudit(
        candidate_count=2, selection_metric="net_pnl", selection_direction="MAXIMIZE",
        holdout_locked_before_selection=True, independent_confirmation=True,
    )
    result = validate_statistics([-1.0] * 30, selection_audit=audit, resamples=300)
    assert result.status == StatisticalStatus.FAIL
    assert any("bootstrap" in item for item in result.failures)


def test_fingerprint_changes_with_seed():
    a = bootstrap_mean([1, 2, 3, 4], resamples=300, seed=1)
    b = bootstrap_mean([1, 2, 3, 4], resamples=300, seed=2)
    assert a.evidence_fingerprint != b.evidence_fingerprint


def test_policy_validation():
    with pytest.raises(ResearchStatisticsError):
        StatisticalValidationPolicy(minimum_sample_size=0)


def test_multiple_testing_empty_input():
    with pytest.raises(ResearchStatisticsError):
        multiple_testing([])


def test_statistics_result_serializes_nested_evidence():
    audit = SelectionBiasAudit(
        candidate_count=2, selection_metric="return", selection_direction="MAXIMIZE",
        holdout_locked_before_selection=True, independent_confirmation=True,
    )
    result = validate_statistics([1.0] * 30, selection_audit=audit, resamples=300)
    payload = result.to_dict()
    assert payload["bootstrap"]["sample_size"] == 30
    assert payload["selection_audit"]["candidate_count"] == 2
