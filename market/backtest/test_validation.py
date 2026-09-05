"""Tests for Phase 2.5.9 backtest validation and integrity."""

from dataclasses import replace

import pytest

from market.backtest.models import BacktestConfig, BacktestDataset, BacktestRunMetadata, BacktestFrame
from market.backtest.orchestration import run_backtest
from market.backtest.reporting import BacktestReport, EquityPoint
from market.backtest.validation import (
    BacktestIntegrityValidator,
    BacktestValidationError,
    BacktestValidationStatus,
    validate_backtest,
)
from market.models import Candle
from market.strategy.models import SignalDirection


def _candle(index: int, close: float) -> Candle:
    timestamp = f"2026-01-01T00:{index:02d}:00+00:00"
    return Candle(
        timestamp=1767225600 + index * 300,
        timestamp_utc=timestamp,
        open=100.0,
        high=max(100.0, close),
        low=min(100.0, close),
        close=float(close),
        volume=0.0,
    )


def _dataset() -> BacktestDataset:
    candles = tuple(_candle(i, price) for i, price in enumerate((100, 110, 105, 120)))
    return BacktestDataset(
        pair="EURUSD",
        interval="5m",
        candles=candles,
        provider="test",
        provider_symbol="EURUSD",
        data_range="1d",
    )


def _report() -> BacktestReport:
    config = BacktestConfig(pair="EURUSD", interval="5m", initial_capital=10_000.0)
    metadata = BacktestRunMetadata(
        config=config,
        dataset_pair="EURUSD",
        dataset_interval="5m",
        dataset_candle_count=4,
        strategy_ids=("test_strategy",),
    )
    return run_backtest(
        _dataset(),
        metadata,
        lambda frame: SignalDirection.LONG,
        close_at_end=True,
    )


def test_valid_report_passes_integrity_validation():
    result = validate_backtest(_report())
    assert result.status is BacktestValidationStatus.PASSED
    assert result.passed is True
    assert result.failed_checks == 0
    assert result.passed_checks == 12


def test_validation_is_deterministic():
    report = _report()
    validator = BacktestIntegrityValidator()
    assert validator.validate(report) == validator.validate(report)
    assert validator.validate(report).to_dict() == validator.validate(report).to_dict()


def test_report_serialization_is_deterministic():
    report = _report()
    assert report.to_dict() == report.to_dict()


def test_dataset_coverage_check_fails_for_inconsistent_metadata():
    report = _report()
    bad_metadata = replace(report.run_metadata, dataset_candle_count=1)
    # Constructing BacktestReport itself remains valid because the reporting contract
    # only requires internal identity; the validator catches insufficient coverage.
    bad_report = replace(report, run_metadata=bad_metadata)
    result = validate_backtest(bad_report)
    assert result.status is BacktestValidationStatus.FAILED
    failed = {check.name for check in result.checks if not check.passed}
    assert "dataset_coverage" in failed


def test_final_equity_check_fails_for_tampered_simulation():
    report = _report()
    bad_report = report
    object.__setattr__(bad_report.simulation.final_account, "equity", bad_report.simulation.final_account.equity + 1.0)
    result = validate_backtest(bad_report)
    assert result.status is BacktestValidationStatus.FAILED
    failed = {check.name for check in result.checks if not check.passed}
    assert "final_equity_consistency" in failed
    assert "performance_consistency" in failed


def test_equity_curve_check_fails_for_tampered_point():
    report = _report()
    first = report.equity_curve[0]
    bad_point = EquityPoint(
        index=first.index,
        timestamp_utc=first.timestamp_utc,
        equity=first.equity + 1.0,
        cumulative_realized_pnl=first.cumulative_realized_pnl,
        position_side=first.position_side,
    )
    bad_curve = (bad_point,) + report.equity_curve[1:]
    bad_report = report
    object.__setattr__(bad_report, "equity_curve", bad_curve)
    result = validate_backtest(bad_report)
    assert result.status is BacktestValidationStatus.FAILED
    failed = {check.name for check in result.checks if not check.passed}
    assert "equity_curve_consistency" in failed


def test_invalid_report_type_is_rejected():
    with pytest.raises(BacktestValidationError):
        validate_backtest(object())



def test_directional_signal_must_be_one_bar_before_execution():
    report = _report()
    first_directional = next(event for event in report.simulation.events if event.signal is SignalDirection.LONG)
    object.__setattr__(first_directional, "signal_index", first_directional.index)
    result = validate_backtest(report)
    assert result.status is BacktestValidationStatus.FAILED
    failed = {check.name for check in result.checks if not check.passed}
    assert "signal_execution_timing" in failed

def test_validation_result_contains_all_audit_checks():
    result = validate_backtest(_report())
    names = [check.name for check in result.checks]
    assert names == [
        "capital_identity",
        "event_chronology",
        "dataset_coverage",
        "final_equity_consistency",
        "performance_consistency",
        "equity_curve_consistency",
        "trade_id_uniqueness",
        "trade_point_in_time_integrity",
        "signal_execution_timing",
        "trade_pnl_consistency",
        "exposure_accounting",
        "serialization_determinism",
    ]
