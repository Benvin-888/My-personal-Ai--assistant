"""Tests for Phase 2.14 research evidence and promotion pipeline."""
from types import SimpleNamespace

import pytest

from .engine import ResearchPerformance
from .experiment import CrossMarketResearchSummary
from .promotion import (
    PromotionEvidence, PromotionStatus, ResearchPromotionEngine,
    ResearchPromotionError, ResearchPromotionPolicy, promote_research,
)
from .robustness import RobustnessScenarioResult, RobustnessScenarioSpec, RobustnessScenarioSummary, RobustnessStatus, TimeWalkForwardResult, TimeWalkForwardWindow
from .statistics import BootstrapResult, StatisticalStatus, StatisticalValidationResult
from .validation import ResearchValidationResult, ValidationStatus


def performance(pnl: float) -> ResearchPerformance:
    return ResearchPerformance(
        initial_capital=1000.0, final_equity=1000.0 + pnl, net_pnl=pnl,
        total_return_pct=pnl / 10.0, trade_count=40, win_rate_pct=55.0,
        profit_factor=1.5, expectancy=pnl / 40.0, average_risk_multiple=0.5,
        max_drawdown=50.0, max_drawdown_pct=5.0, total_transaction_costs=10.0,
        recovery_factor=2.0, calmar_like_ratio=2.0, gross_profit=500.0, gross_loss=200.0,
    )


def evidence(temporal=True, scenarios=True, holdout=True):
    validation = ResearchValidationResult(
        status=ValidationStatus.PASS, eligible_for_paper=True, eligible_for_demo=True,
        checks=(), failures=(), warnings=(), evidence_fingerprint="v", policy={},
    )
    bootstrap = BootstrapResult(40, 500, 0, .95, .1, .1, .01, .19, .9, "b")
    statistical = StatisticalValidationResult(
        status=StatisticalStatus.PASS, sample_size=40, bootstrap=bootstrap,
        selection_audit=None, checks=(), failures=(), warnings=(),
        eligible_for_research_promotion=True, evidence_fingerprint="s",
    )
    experiments = CrossMarketResearchSummary(
        total_cases=3, completed_cases=3, passed_cases=3, failed_cases=0,
        validation_pass_fraction=1.0, profitable_case_fraction=1.0,
        symbols=("EURUSD", "GBPUSD"), intervals=("5m",),
        by_symbol={}, by_interval={}, evidence_fingerprint="e",
    )
    temporal_result = None
    if temporal:
        windows = tuple(TimeWalkForwardWindow(i, "2026-01-01T00:00:00+00:00", "2026-01-30T00:00:00+00:00", "2026-01-31T00:00:00+00:00", "2026-02-10T00:00:00+00:00", 40, 40, performance(50), performance(20)) for i in range(1, 4))
        temporal_result = TimeWalkForwardResult(30, 10, 10, windows, 1.0, 2.0, 2.0, "t")
    scenario_result = None
    if scenarios:
        spec = RobustnessScenarioSpec("base", "base")
        sr = RobustnessScenarioResult(spec, RobustnessStatus.PASS, performance(100))
        scenario_result = RobustnessScenarioSummary(3, 3, 3, 1.0, 100, 100, 100, 0, (sr, sr, sr), "r")
    return PromotionEvidence("candidate-1", validation, experiments, statistical, temporal_result, scenario_result, holdout, False)


def test_promotion_passes_complete_evidence():
    result = promote_research(evidence())
    assert result.status == PromotionStatus.PROMOTE_PAPER
    assert result.eligible_for_paper is True
    assert result.eligible_for_demo is False
    assert result.metadata["execution_authorization"] is False


def test_missing_temporal_evidence_holds():
    result = promote_research(evidence(temporal=False))
    assert result.status == PromotionStatus.HOLD
    assert any("temporal robustness" in x for x in result.failures)


def test_missing_scenario_evidence_holds():
    result = promote_research(evidence(scenarios=False))
    assert result.status == PromotionStatus.HOLD
    assert any("scenario evidence" in x for x in result.failures)


def test_unlocked_holdout_holds():
    result = promote_research(evidence(holdout=False))
    assert result.status == PromotionStatus.HOLD
    assert "holdout was not locked before selection" in result.failures


def test_policy_can_require_independent_confirmation():
    policy = ResearchPromotionPolicy(require_independent_confirmation=True)
    result = promote_research(evidence(), policy)
    assert result.status == PromotionStatus.HOLD


def test_policy_can_disable_optional_gates():
    policy = ResearchPromotionPolicy(require_temporal_robustness=False, require_scenario_robustness=False)
    result = promote_research(evidence(temporal=False, scenarios=False), policy)
    assert result.status == PromotionStatus.PROMOTE_PAPER


def test_low_cross_market_breadth_holds():
    ev = evidence()
    weak = CrossMarketResearchSummary(1, 1, 1, 1, 1, 1, ("EURUSD",), ("5m",), {}, {}, "x")
    ev = PromotionEvidence(ev.candidate_id, ev.validation, weak, ev.statistical, ev.temporal, ev.scenarios, ev.holdout_locked)
    result = ResearchPromotionEngine().evaluate(ev)
    assert result.status == PromotionStatus.HOLD


def test_low_temporal_profitability_holds():
    ev = evidence()
    bad = TimeWalkForwardResult(30, 10, 10, ev.temporal.windows, 0.5, -1.0, -1.0, "t2")
    ev = PromotionEvidence(ev.candidate_id, ev.validation, ev.experiments, ev.statistical, bad, ev.scenarios, ev.holdout_locked)
    result = ResearchPromotionEngine().evaluate(ev)
    assert result.status == PromotionStatus.HOLD


def test_low_scenario_profitability_holds():
    ev = evidence()
    bad = RobustnessScenarioSummary(3, 3, 1, 1/3, 100, -10, 100, 110, ev.scenarios.scenarios, "r2")
    ev = PromotionEvidence(ev.candidate_id, ev.validation, ev.experiments, ev.statistical, ev.temporal, bad, ev.holdout_locked)
    result = ResearchPromotionEngine().evaluate(ev)
    assert result.status == PromotionStatus.HOLD


def test_phase_210_validation_failure_holds():
    ev = evidence()
    bad = ResearchValidationResult(ValidationStatus.FAIL, False, False, (), ("bad",), (), "v2", {})
    ev = PromotionEvidence(ev.candidate_id, bad, ev.experiments, ev.statistical, ev.temporal, ev.scenarios, ev.holdout_locked)
    assert promote_research(ev).status == PromotionStatus.HOLD


def test_phase_213_statistics_failure_holds():
    ev = evidence()
    bad = StatisticalValidationResult(StatisticalStatus.FAIL, 40, ev.statistical.bootstrap, None, (), ("bad",), (), False, "s2")
    ev = PromotionEvidence(ev.candidate_id, ev.validation, ev.experiments, bad, ev.temporal, ev.scenarios, ev.holdout_locked)
    assert promote_research(ev).status == PromotionStatus.HOLD


def test_result_fingerprint_is_deterministic():
    a = promote_research(evidence())
    b = promote_research(evidence())
    assert a.evidence_fingerprint == b.evidence_fingerprint


def test_policy_rejects_invalid_fraction():
    with pytest.raises(ResearchPromotionError):
        ResearchPromotionPolicy(minimum_profitable_case_fraction=1.1)


def test_policy_rejects_zero_experiment_threshold():
    with pytest.raises(ResearchPromotionError):
        ResearchPromotionPolicy(minimum_completed_experiments=0)


def test_evidence_requires_candidate_id():
    ev = evidence()
    with pytest.raises(ResearchPromotionError):
        PromotionEvidence("", ev.validation, ev.experiments, ev.statistical)
