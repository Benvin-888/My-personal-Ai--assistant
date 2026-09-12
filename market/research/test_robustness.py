from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest

from market.backtest.risk_aware import RiskAwareBacktestResult, RiskAwareTrade, RiskAwareTradeStatus
from market.research.engine import ResearchPerformance
from market.research.experiment import ResearchDatasetSpec, ResearchExperimentSpec
from market.research.robustness import (
    ResearchRobustnessEngine,
    ResearchRobustnessError,
    RobustnessScenarioSpec,
    RobustnessStatus,
)


def result_with_days(days):
    base = __import__("market.research.test_engine", fromlist=["make_result"]).make_result(tuple(1.0 for _ in days))
    trades = tuple(replace(t, opportunity_timestamp_utc=(datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=d)).isoformat()) for t, d in zip(base.trades, days))
    return replace(base, trades=trades, final_equity=base.initial_capital + sum(t.realized_pnl for t in trades), net_pnl=sum(t.realized_pnl for t in trades))

def spec():
    ds = ResearchDatasetSpec("d1", "EURUSD", "1d", "2025-01-01T00:00:00Z", "2025-07-01T00:00:00Z", "test", 20)
    return ResearchExperimentSpec("e1", "trend_momentum", ds)


def test_time_walk_forward_uses_calendar_windows():
    result = result_with_days([1, 2, 10, 20, 31, 40, 50, 61, 70, 80, 91, 100, 110, 121, 130, 140, 151, 160, 170])
    out = ResearchRobustnessEngine().time_walk_forward(result, train_days=30, test_days=20, step_days=20)
    assert len(out.windows) >= 3
    assert all(w.train_trade_count >= 1 and w.test_trade_count >= 1 for w in out.windows)
    assert 0.0 <= out.profitable_test_window_fraction <= 1.0
    assert len(out.evidence_fingerprint) == 64


def test_missing_timestamp_rejected():
    result = result_with_days([1, 10])
    bad = replace(result.trades[0], opportunity_timestamp_utc=None)
    rebuilt = replace(result, trades=(bad,) + result.trades[1:])
    with pytest.raises(ResearchRobustnessError):
        ResearchRobustnessEngine().time_walk_forward(rebuilt, train_days=1, test_days=1)


def test_insufficient_time_coverage_rejected():
    with pytest.raises(ResearchRobustnessError):
        ResearchRobustnessEngine().time_walk_forward(result_with_days([1, 2]), train_days=30, test_days=30)


def test_invalid_days_rejected():
    with pytest.raises(ResearchRobustnessError):
        ResearchRobustnessEngine().time_walk_forward(result_with_days([1, 100]), train_days=0)


def test_scenario_spec_validation():
    with pytest.raises(ResearchRobustnessError):
        RobustnessScenarioSpec("x", "test", transaction_cost_multiplier=-1)
    assert RobustnessScenarioSpec("baseline", "unchanged").to_dict()["scenario_id"] == "baseline"


def test_scenario_runner_and_summary():
    engine = ResearchRobustnessEngine()
    scenarios = [RobustnessScenarioSpec("baseline", "unchanged"), RobustnessScenarioSpec("stress", "higher costs", transaction_cost_multiplier=2.0)]
    p1 = ResearchPerformance(10, 100, 10, 0.1, 10, 50, 2, 5, 0.5, 100, 1, 1, 0, 10, 5)
    p2 = ResearchPerformance(10, 95, -5, -0.05, 10, 40, 1.5, -0.5, 0.2, 80, 2, 2, 0, 5, 5)
    results = engine.run_scenarios(spec(), scenarios, lambda s, sc: p1 if sc.scenario_id == "baseline" else p2)
    summary = engine.summarize_scenarios(results)
    assert summary.total_scenarios == 2
    assert summary.completed_scenarios == 2
    assert summary.profitable_scenarios == 1
    assert summary.baseline_net_pnl == 10.0
    assert summary.worst_net_pnl == -5.0


def test_scenario_errors_are_audited():
    engine = ResearchRobustnessEngine()
    scenarios = [RobustnessScenarioSpec("x", "will fail")]
    results = engine.run_scenarios(spec(), scenarios, lambda s, sc: (_ for _ in ()).throw(RuntimeError("boom")))
    assert results[0].status == RobustnessStatus.ERROR
    assert "boom" in results[0].error


def test_duplicate_scenarios_rejected():
    engine = ResearchRobustnessEngine()
    s = RobustnessScenarioSpec("x", "same")
    with pytest.raises(ResearchRobustnessError):
        engine.run_scenarios(spec(), [s, s], lambda *_: ResearchPerformance(1,1,1,1,1,1,1,1,1,1,1,0,0,1,1))


def test_empty_scenarios_rejected():
    with pytest.raises(ResearchRobustnessError):
        ResearchRobustnessEngine().run_scenarios(spec(), [], lambda *_: None)


def test_non_performance_runner_result_is_error():
    results = ResearchRobustnessEngine().run_scenarios(spec(), [RobustnessScenarioSpec("x", "bad")], lambda *_: "bad")
    assert results[0].status == RobustnessStatus.ERROR


def test_summary_requires_results():
    with pytest.raises(ResearchRobustnessError):
        ResearchRobustnessEngine.summarize_scenarios([])
