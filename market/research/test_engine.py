from __future__ import annotations

from types import SimpleNamespace

import pytest

from market.backtest.risk_aware import RiskAwareBacktestResult, RiskAwareTrade, RiskAwareTradeStatus
from market.research import StrategyResearchEngine, StrategyResearchError


def make_result(r_values=(1.0, -1.0, 2.0, -0.5, 1.5, -1.0, 0.5, 1.0, -0.75, 1.25), metadata=None):
    trades = []
    equity = 10_000.0
    for i, r in enumerate(r_values, 1):
        risk = 50.0
        pnl = r * risk
        equity += pnl
        trades.append(RiskAwareTrade(
            trade_id=i, opportunity_timestamp_utc=f"2026-01-{i:02d}T00:00:00+00:00",
            signal_index=i - 1, entry_index=i, exit_index=i + 1,
            pair="EURUSD", direction="LONG", entry_market_price=1.1000,
            entry_price=1.1000, stop_loss=1.0950, take_profit=1.1100,
            exit_market_price=1.1000 + r * 0.001, exit_price=1.1000 + r * 0.001,
            quantity=1.0, planned_risk_amount=risk, realized_pnl=pnl,
            gross_pnl=pnl, transaction_costs=0.0,
            status=RiskAwareTradeStatus.TAKE_PROFIT if r > 0 else RiskAwareTradeStatus.STOP_LOSS,
            reward_risk=2.0, risk_multiple=r,
            metadata=metadata[i - 1] if metadata else {},
        ))
    gross_profit = sum(max(0, t.realized_pnl) for t in trades)
    gross_loss = -sum(min(0, t.realized_pnl) for t in trades)
    peak = 10_000.0
    max_dd = 0.0
    for t in trades:
        equity2 = 10_000.0 + sum(x.realized_pnl for x in trades[:t.trade_id])
        peak = max(peak, equity2)
        max_dd = max(max_dd, peak - equity2)
    return RiskAwareBacktestResult(
        pair="EURUSD", interval="5m", initial_capital=10_000.0,
        final_equity=equity, net_pnl=equity - 10_000.0,
        total_return_pct=(equity - 10_000.0) / 100.0,
        peak_equity=peak, max_drawdown=max_dd,
        max_drawdown_pct=max_dd / peak * 100 if peak else 0,
        trades=tuple(trades), events=(), rejected_opportunities=0,
        risk_rejections=0, candidate_opportunities=len(trades), stop_losses=sum(t.realized_pnl < 0 for t in trades),
        take_profits=sum(t.realized_pnl > 0 for t in trades), end_of_test_closures=0,
        winning_trades=sum(t.realized_pnl > 0 for t in trades), losing_trades=sum(t.realized_pnl < 0 for t in trades),
        breakeven_trades=0, gross_profit=gross_profit, gross_loss=gross_loss,
        profit_factor=gross_profit / gross_loss if gross_loss else None,
        average_win=gross_profit / max(1, sum(t.realized_pnl > 0 for t in trades)),
        average_loss=-gross_loss / max(1, sum(t.realized_pnl < 0 for t in trades)),
        average_risk_multiple=sum(t.risk_multiple for t in trades) / len(trades),
        total_transaction_costs=0.0, risk_budget_breaches=0,
        config={}, metadata={},
    )


def test_performance_is_deterministic_and_measured():
    result = make_result()
    performance = StrategyResearchEngine().performance(result)
    assert performance.trade_count == 10
    assert performance.total_return_pct == pytest.approx(2.0)
    assert performance.expectancy == pytest.approx(20.0)
    assert performance.average_risk_multiple == pytest.approx(0.4)


def test_out_of_sample_is_chronological_and_does_not_overlap():
    result = make_result()
    report = StrategyResearchEngine().out_of_sample(result, 0.7)
    assert report.split_trade_index == 7
    assert report.in_sample.trade_count == 7
    assert report.out_of_sample.trade_count == 3
    assert report.out_of_sample.final_equity == pytest.approx(10_200.0)


def test_walk_forward_windows_are_chronological():
    result = make_result()
    windows = StrategyResearchEngine().walk_forward(result, train_trades=4, test_trades=2, step_trades=2)
    assert len(windows) == 3
    assert windows[0].train_start_trade == 0
    assert windows[0].test_start_trade == 4
    assert windows[1].train_start_trade == 2
    assert windows[1].test_start_trade == 6


def test_parameter_stability_does_not_select_a_best_run():
    engine = StrategyResearchEngine()
    runs = {"a": make_result((1, 1, -1)), "b": make_result((0.5, 0.5, -0.25))}
    stability = engine.parameter_stability(runs)
    assert stability.run_count == 2
    assert stability.profitable_run_count == 2
    assert len(stability.runs) == 2


def test_regime_and_session_group_stability():
    metadata = [
        {"regime": "TREND", "session": "London"},
        {"regime": "TREND", "session": "London"},
        {"regime": "RANGE", "session": "New York"},
        {"regime": "RANGE", "session": "New York"},
        {"regime": "TREND", "session": "Tokyo"},
        {"regime": "RANGE", "session": "Tokyo"},
        {"regime": "TREND", "session": "London"},
        {"regime": "RANGE", "session": "New York"},
        {"regime": "TREND", "session": "Tokyo"},
        {"regime": "RANGE", "session": "London"},
    ]
    engine = StrategyResearchEngine()
    result = make_result(metadata=metadata)
    assert {k for k, _ in engine.group_stability(result, "regime").groups} == {"RANGE", "TREND"}
    assert {k for k, _ in engine.group_stability(result, "session").groups} == {"London", "New York", "Tokyo"}


def test_seeded_monte_carlo_is_reproducible():
    result = make_result()
    engine = StrategyResearchEngine()
    a = engine.monte_carlo(result, simulations=100, trades_per_simulation=10, seed=123)
    b = engine.monte_carlo(result, simulations=100, trades_per_simulation=10, seed=123)
    assert a == b
    assert 0.0 <= a.positive_terminal_fraction <= 1.0
    assert 0.0 <= a.ruin_fraction <= 1.0


def test_analyze_collects_warnings_when_optional_evidence_is_missing():
    result = make_result()
    report = StrategyResearchEngine().analyze(
        result, include_regime=True, include_session=True,
        monte_carlo_config=None, walk_forward_config=None,
    )
    assert report.out_of_sample is not None
    assert any("no trade metadata" in warning for warning in report.warnings)


def test_invalid_inputs_are_rejected():
    engine = StrategyResearchEngine()
    result = make_result()
    with pytest.raises(StrategyResearchError):
        engine.out_of_sample(result, 1.0)
    with pytest.raises(StrategyResearchError):
        engine.walk_forward(result, train_trades=20, test_trades=10)
    with pytest.raises(StrategyResearchError):
        engine.parameter_stability({})
