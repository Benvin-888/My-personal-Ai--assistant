"""Tests for Phase 2.11 research experiment contracts."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from market.research.engine import (
    MonteCarloResult,
    OutOfSampleReport,
    ParameterStabilityResult,
    ResearchPerformance,
    StrategyResearchReport,
    WalkForwardWindow,
)
from market.research.experiment import (
    CrossMarketResearchSummary,
    ExperimentStatus,
    ResearchDatasetSpec,
    ResearchExperimentEngine,
    ResearchExperimentError,
    ResearchExperimentResult,
    ResearchExperimentSpec,
    run_experiments,
    summarize_experiments,
)
from market.research.validation import ValidationStatus


def dataset(symbol="EURUSD", interval="5m", dataset_id="eurusd-5m"):
    return ResearchDatasetSpec(
        dataset_id=dataset_id,
        symbol=symbol,
        interval=interval,
        start_utc="2025-01-01T00:00:00Z",
        end_utc="2026-01-01T00:00:00Z",
        source="test",
        row_count=1000,
        content_fingerprint="abc123",
    )


def spec(symbol="EURUSD", interval="5m", experiment_id="exp-1"):
    return ResearchExperimentSpec(
        experiment_id=experiment_id,
        strategy_id="trend_momentum",
        dataset=dataset(symbol, interval, f"{symbol}-{interval}"),
        strategy_parameters={"fast": 10},
        risk_parameters={"risk_fraction": 0.005},
        execution_parameters={"spread": 0.0001},
        seed=42,
        tags=("fx",),
    )


def report(net_pnl=100.0):
    perf = ResearchPerformance(
        initial_capital=10000.0,
        final_equity=10000.0 + net_pnl,
        net_pnl=net_pnl,
        total_return_pct=net_pnl / 100.0,
        trade_count=40,
        win_rate_pct=55.0,
        profit_factor=1.5,
        expectancy=2.5,
        average_risk_multiple=0.25,
        max_drawdown=300.0,
        max_drawdown_pct=3.0,
        total_transaction_costs=20.0,
        recovery_factor=1.0,
        calmar_like_ratio=1.0,
        gross_profit=200.0,
        gross_loss=100.0,
    )
    wf = tuple(
        WalkForwardWindow(i, i + 1, i + 1, i + 1, i + 2, perf, perf)
        for i in range(3)
    )
    return StrategyResearchReport(
        baseline=perf,
        out_of_sample=OutOfSampleReport(perf, perf, 20, 80.0, True),
        walk_forward=wf,
        parameter_stability=ParameterStabilityResult(2, 5.0, 1.0, 4.0, 6.0, 1.5, 3.0, 2, 1.0, 0.9, ()),
        regime_stability=None,
        session_stability=None,
        monte_carlo=MonteCarloResult(42, 100, 10, 10000.0, 12000.0, 12000.0, 9000.0, 15000.0, 500.0, 0.8, 0.01),
        warnings=(),
        metadata={},
    )


def test_dataset_spec_is_deterministic():
    assert dataset().to_dict()["symbol"] == "EURUSD"
    assert dataset().to_dict() == dataset().to_dict()


def test_experiment_fingerprint_is_deterministic():
    assert spec().fingerprint == spec().fingerprint
    assert spec().fingerprint != spec(experiment_id="exp-2").fingerprint


def test_invalid_dataset_rejected():
    with pytest.raises(ResearchExperimentError):
        ResearchDatasetSpec("x", "EURUSD", "5m", "a", "b", "test", 0)


def test_duplicate_experiment_ids_rejected():
    with pytest.raises(ResearchExperimentError):
        ResearchExperimentEngine().validate_specs((spec(), spec()))


def test_run_case_passes_validation():
    result = ResearchExperimentEngine().run_case(spec(), lambda _: report())
    assert result.status == ExperimentStatus.PASS
    assert result.validation is not None
    assert result.validation.status == ValidationStatus.PASS
    assert result.performance is not None


def test_run_case_failure_is_recorded_without_crashing():
    result = ResearchExperimentEngine().run_case(spec(), lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    assert result.status == ExperimentStatus.ERROR
    assert "RuntimeError" in result.error


def test_run_case_rejects_wrong_runner_result():
    result = ResearchExperimentEngine().run_case(spec(), lambda _: SimpleNamespace())
    assert result.status == ExperimentStatus.ERROR
    assert "StrategyResearchReport" in result.error


def test_run_multiple_cases_is_order_preserving():
    results = run_experiments((spec(), spec("GBPUSD", "5m", "exp-2")), lambda s: report())
    assert [r.spec.experiment_id for r in results] == ["exp-1", "exp-2"]


def test_summary_aggregates_symbols_and_intervals():
    results = (
        ResearchExperimentEngine().run_case(spec(), lambda _: report()),
        ResearchExperimentEngine().run_case(spec("GBPUSD", "15m", "exp-2"), lambda _: report(-50.0)),
    )
    summary = summarize_experiments(results)
    assert isinstance(summary, CrossMarketResearchSummary)
    assert summary.total_cases == 2
    assert summary.completed_cases == 2
    assert summary.symbols == ("EURUSD", "GBPUSD")
    assert summary.intervals == ("15m", "5m")
    assert summary.by_symbol["EURUSD"]["profitable_fraction"] == 1.0
    assert summary.by_symbol["GBPUSD"]["profitable_fraction"] == 0.0


def test_summary_fingerprint_is_deterministic():
    results = run_experiments((spec(),), lambda _: report())
    assert summarize_experiments(results).evidence_fingerprint == summarize_experiments(results).evidence_fingerprint


def test_summary_requires_results():
    with pytest.raises(ResearchExperimentError):
        summarize_experiments(())


def test_result_requires_performance_for_pass():
    with pytest.raises(ResearchExperimentError):
        ResearchExperimentResult(spec(), ExperimentStatus.PASS)
