from __future__ import annotations

from .engine import (
    GroupStabilityResult,
    MonteCarloResult,
    OutOfSampleReport,
    ParameterStabilityResult,
    ResearchPerformance,
    StrategyResearchReport,
    WalkForwardWindow,
)
from .validation import ResearchValidationEngine, ResearchValidationPolicy, ValidationStatus


def perf(trades: int = 40, pnl: float = 100.0, ret: float = 1.0, dd: float = 5.0, gp: float = 500.0, costs: float = 50.0):
    return ResearchPerformance(10_000, 10_000 + pnl, pnl, ret, trades, 60, 1.8, 10, 0.2, dd * 100, dd, costs, 2, 0.2, gross_profit=gp, gross_loss=max(0.0, gp - pnl))


def good_report():
    base = perf()
    oos = OutOfSampleReport(base, perf(15, 80, 0.8), 28, 80, True)
    wf = tuple(WalkForwardWindow(i, 0, 9, 10, 14, base, perf(5, 20, 0.2)) for i in range(1, 4))
    ps = ParameterStabilityResult(4, 1, .2, .5, 1.4, 1.7, 5, 3, .75, .8, tuple((str(i), base) for i in range(4)))
    group = GroupStabilityResult("regime", (("TREND", base), ("RANGE", base)), .75, .3)
    session = GroupStabilityResult("session", (("London", base), ("New York", base)), .75, .3)
    mc = MonteCarloResult(123, 100, 40, 10_000, 10_200, 10_180, 9_500, 11_000, 800, .7, .01)
    return StrategyResearchReport(base, oos, wf, ps, group, session, mc)


def test_good_report_passes_and_is_paper_eligible():
    result = ResearchValidationEngine().validate(good_report())
    assert result.status == ValidationStatus.PASS
    assert result.eligible_for_paper is True
    assert result.eligible_for_demo is True
    assert len(result.evidence_fingerprint) == 64


def test_validation_is_deterministic():
    engine = ResearchValidationEngine()
    a = engine.validate(good_report())
    b = engine.validate(good_report())
    assert a == b


def test_insufficient_trade_sample_fails_gate():
    report = good_report()
    small = perf(trades=10)
    report = StrategyResearchReport(small, report.out_of_sample, report.walk_forward, report.parameter_stability, report.regime_stability, report.session_stability, report.monte_carlo)
    result = ResearchValidationEngine().validate(report)
    assert result.status == ValidationStatus.FAIL
    assert "minimum_trades" in result.failures


def test_missing_required_evidence_fails():
    r = good_report()
    policy = ResearchValidationPolicy(require_parameter_stability=True, require_monte_carlo=True)
    report = StrategyResearchReport(r.baseline, r.out_of_sample, r.walk_forward, None, r.regime_stability, r.session_stability, None)
    result = ResearchValidationEngine().validate(report, policy)
    assert result.status == ValidationStatus.FAIL
    assert "parameter_stability_present" in result.failures
    assert "monte_carlo_present" in result.failures


def test_optional_regime_and_session_evidence_generate_warnings_not_failure():
    r = good_report()
    report = StrategyResearchReport(r.baseline, r.out_of_sample, r.walk_forward, r.parameter_stability, None, None, r.monte_carlo)
    result = ResearchValidationEngine().validate(report)
    assert result.status == ValidationStatus.PASS
    assert any("no regime stability evidence" in w for w in result.warnings)
    assert result.eligible_for_demo is False
