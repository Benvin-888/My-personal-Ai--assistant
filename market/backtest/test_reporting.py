"""Tests for Phase 2.5.7 backtest reporting and result aggregation."""

import pytest

from market.backtest.models import BacktestConfig, BacktestFrame, BacktestRunMetadata
from market.backtest.position import PositionSide
from market.backtest.reporting import (
    BacktestReport,
    BacktestReportBuilder,
    BacktestReportingError,
    EquityPoint,
    build_report,
)
from market.backtest.trade import TradeSimulator
from market.models import Candle
from market.strategy.models import SignalDirection


def _frame(index: int, close: float) -> BacktestFrame:
    candles = tuple(
        Candle(
            timestamp=1704067200 + i * 60,
            timestamp_utc=f"2026-01-01T00:{i:02d}:00+00:00",
            open=100.0,
            high=100.0,
            low=100.0,
            close=float(close if i == index else 100.0),
            volume=0.0,
        )
        for i in range(index + 1)
    )
    return BacktestFrame(index=index, candle=candles[-1], available_candles=candles)


def _metadata(initial_capital: float = 10000.0) -> BacktestRunMetadata:
    config = BacktestConfig(pair="EURUSD", interval="5m", initial_capital=initial_capital)
    return BacktestRunMetadata(
        config=config,
        dataset_pair="EURUSD",
        dataset_interval="5m",
        dataset_candle_count=3,
        strategy_ids=("trend_momentum", "mean_reversion"),
    )


def test_build_report_aggregates_simulation_metrics_and_equity_curve():
    result = TradeSimulator(initial_capital=10000, quantity=2).simulate(
        [_frame(0, 100), _frame(1, 110)],
        lambda f: SignalDirection.LONG,
        close_at_end=True,
    )
    report = build_report(_metadata(), result)

    assert isinstance(report, BacktestReport)
    assert report.pair == "EURUSD"
    assert report.interval == "5m"
    assert report.strategy_ids == ("trend_momentum", "mean_reversion")
    assert report.performance.net_pnl == 20.0
    assert len(report.equity_curve) == len(result.events)
    assert report.equity_curve[-1].equity == 10020.0
    assert report.equity_curve[-1].position_side is PositionSide.FLAT


def test_equity_curve_matches_every_simulation_event_in_order():
    result = TradeSimulator().simulate(
        [_frame(0, 100), _frame(1, 105), _frame(2, 103)],
        lambda f: SignalDirection.LONG,
        close_at_end=True,
    )
    report = BacktestReportBuilder().build(_metadata(), result)

    assert [p.index for p in report.equity_curve] == [e.index for e in result.events]
    assert [p.timestamp_utc for p in report.equity_curve] == [e.timestamp_utc for e in result.events]
    assert [p.equity for p in report.equity_curve] == [e.equity for e in result.events]
    assert [p.position_side for p in report.equity_curve] == [e.to_side for e in result.events]


def test_empty_simulation_produces_empty_equity_curve():
    result = TradeSimulator().simulate([], lambda f: SignalDirection.LONG)
    report = build_report(_metadata(), result)

    assert report.performance.trade_count == 0
    assert report.equity_curve == ()


def test_report_serialization_is_deterministic_and_complete():
    result = TradeSimulator().simulate(
        [_frame(0, 100), _frame(1, 105)],
        lambda f: SignalDirection.LONG,
        close_at_end=True,
    )
    report = build_report(_metadata(), result)
    data = report.to_dict()

    assert data == build_report(_metadata(), result).to_dict()
    assert set(data) == {"run_metadata", "simulation", "performance", "equity_curve"}
    assert data["run_metadata"]["strategy_ids"] == ["trend_momentum", "mean_reversion"]
    assert data["performance"]["net_pnl"] == 5.0
    assert len(data["equity_curve"]) == len(result.events)


def test_capital_mismatch_is_rejected():
    result = TradeSimulator(initial_capital=5000).simulate(
        [_frame(0, 100)], lambda f: SignalDirection.LONG
    )
    with pytest.raises(BacktestReportingError):
        build_report(_metadata(initial_capital=10000), result)


def test_invalid_inputs_are_rejected():
    result = TradeSimulator().simulate([], lambda f: SignalDirection.LONG)

    with pytest.raises(BacktestReportingError):
        build_report(object(), result)
    with pytest.raises(BacktestReportingError):
        build_report(_metadata(), object())


def test_equity_point_validation_rejects_invalid_values():
    with pytest.raises(BacktestReportingError):
        EquityPoint(
            index=-1,
            timestamp_utc="2026-01-01T00:00:00+00:00",
            equity=10000,
            cumulative_realized_pnl=0,
            position_side=PositionSide.FLAT,
        )


def test_report_rejects_tampered_performance():
    result = TradeSimulator().simulate(
        [_frame(0, 100), _frame(1, 105)],
        lambda f: SignalDirection.LONG,
        close_at_end=True,
    )
    valid = build_report(_metadata(), result)
    tampered = valid.performance.__class__(
        **{**valid.performance.to_dict(), "net_pnl": 999.0}
    )

    with pytest.raises(BacktestReportingError):
        BacktestReport(
            run_metadata=valid.run_metadata,
            simulation=valid.simulation,
            performance=tampered,
            equity_curve=valid.equity_curve,
        )
