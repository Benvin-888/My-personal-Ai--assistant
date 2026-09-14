"""Tests for Phase 2.15 research cohort coverage integrity."""
from .cohort import CohortStatus, ResearchCohortEngine, ResearchCohortError, ResearchCohortPolicy
from .engine import ResearchPerformance
from .experiment import ExperimentStatus, ResearchDatasetSpec, ResearchExperimentResult, ResearchExperimentSpec


def make_result(i, symbol="EURUSD", interval="5m", dataset_id=None, fp=None, pnl=10):
    ds = ResearchDatasetSpec(dataset_id or f"ds-{i}", symbol, interval, "2026-01-01", "2026-03-01", "test", 100, fp or f"fp-{i}")
    spec = ResearchExperimentSpec(f"exp-{i}", "strategy", ds)
    perf = ResearchPerformance(1000, 1000+pnl, pnl, 1, 40, 55, 1.5, .2, .5, 20, 2, 10, 2, 2, 500, 200)
    return ResearchExperimentResult(spec, ExperimentStatus.PASS, perf)


def test_complete_multi_symbol_cohort_passes():
    result = ResearchCohortEngine().evaluate("cohort-1", [make_result(1), make_result(2, "GBPUSD"), make_result(3, "USDJPY")])
    assert result.status == CohortStatus.PASS
    assert result.eligible_for_promotion is True
    assert result.symbols == ("EURUSD", "GBPUSD", "USDJPY")


def test_too_few_cases_holds():
    result = ResearchCohortEngine().evaluate("c", [make_result(1), make_result(2, "GBPUSD")])
    assert result.status == CohortStatus.INSUFFICIENT_DATA


def test_duplicate_dataset_ids_hold():
    result = ResearchCohortEngine().evaluate("c", [make_result(1, "EURUSD", dataset_id="same"), make_result(2, "GBPUSD", dataset_id="same"), make_result(3, "USDJPY")])
    assert result.status == CohortStatus.HOLD
    assert "duplicate dataset IDs detected" in result.failures


def test_duplicate_dataset_fingerprints_hold():
    result = ResearchCohortEngine().evaluate("c", [make_result(1, "EURUSD", fp="same"), make_result(2, "GBPUSD", fp="same"), make_result(3, "USDJPY")])
    assert result.status == CohortStatus.HOLD
    assert "duplicate dataset fingerprints detected" in result.failures


def test_holdout_lock_is_required():
    result = ResearchCohortEngine().evaluate("c", [make_result(1), make_result(2, "GBPUSD"), make_result(3, "USDJPY")], holdout_locked=False)
    assert result.status == CohortStatus.HOLD


def test_timeframe_coverage_is_recorded():
    result = ResearchCohortEngine().evaluate("c", [make_result(1), make_result(2, "GBPUSD", "15m"), make_result(3, "USDJPY")])
    assert result.status == CohortStatus.PASS
    assert result.intervals == ("15m", "5m")
    assert len(result.symbol_interval_cells) == 3


def test_custom_policy_can_require_more_cells():
    policy = ResearchCohortPolicy(minimum_symbol_interval_cells=4)
    result = ResearchCohortEngine(policy).evaluate("c", [make_result(1), make_result(2, "GBPUSD"), make_result(3, "USDJPY")])
    assert result.status == CohortStatus.HOLD


def test_custom_policy_can_disable_uniqueness_gate():
    policy = ResearchCohortPolicy(require_unique_dataset_ids=False, require_unique_dataset_fingerprints=False)
    result = ResearchCohortEngine(policy).evaluate("c", [make_result(1, dataset_id="same", fp="same"), make_result(2, "GBPUSD", dataset_id="same", fp="same"), make_result(3, "USDJPY")])
    assert result.status == CohortStatus.PASS


def test_deterministic_fingerprint():
    a = ResearchCohortEngine().evaluate("c", [make_result(1), make_result(2, "GBPUSD"), make_result(3, "USDJPY")])
    b = ResearchCohortEngine().evaluate("c", [make_result(1), make_result(2, "GBPUSD"), make_result(3, "USDJPY")])
    assert a.evidence_fingerprint == b.evidence_fingerprint


def test_invalid_cohort_id():
    try:
        ResearchCohortEngine().evaluate("", [make_result(1)])
    except ResearchCohortError:
        pass
    else:
        raise AssertionError("expected ResearchCohortError")


def test_empty_results_rejected():
    try:
        ResearchCohortEngine().evaluate("c", [])
    except ResearchCohortError:
        pass
    else:
        raise AssertionError("expected ResearchCohortError")
