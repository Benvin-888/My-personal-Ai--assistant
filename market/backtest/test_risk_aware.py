"""Tests for Phase 2.8 risk-aware backtesting."""

from __future__ import annotations

from market.backtest.friction import ExecutionFrictionConfig
from market.backtest.models import BacktestDataset
from market.backtest.risk_aware import (
    IntrabarPolicy,
    RiskAwareBacktestConfig,
    RiskAwareBacktestEngine,
    RiskAwareBacktestError,
    RiskAwareTradeStatus,
)
from market.models import Candle
from market.opportunity import OpportunityStatus, TradeOpportunity
from market.strategy.models import SignalDirection


def _candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp=index * 60,
        timestamp_utc=f"2026-01-01T00:{index:02d}:00Z",
        open=open_, high=high, low=low, close=close, volume=None,
    )


def _dataset(*rows: tuple[float, float, float, float]) -> BacktestDataset:
    candles = tuple(_candle(i, *row) for i, row in enumerate(rows))
    return BacktestDataset(pair="EURUSD", interval="1m", candles=candles)


def _opportunity(index: int, direction: SignalDirection = SignalDirection.LONG) -> TradeOpportunity:
    return TradeOpportunity(
        pair="EURUSD", interval="1m", timestamp_utc=f"2026-01-01T00:{index:02d}:00Z",
        status=OpportunityStatus.CANDIDATE, direction=direction,
        ensemble_score=0.9, agreement=0.9, conflict=0.0, confidence=0.8,
        regime="TRENDING", session_phase="SINGLE_SESSION", active_sessions=("LONDON",),
        operational_state="HEALTHY", analysis_usable=True,
        reasons=("test candidate",), evidence=("test",),
    )


def _config(**kwargs):
    values = dict(pair="EURUSD", interval="1m", initial_capital=10_000.0, quantity_step=1.0)
    values.update(kwargs)
    return RiskAwareBacktestConfig(**values)


def test_next_bar_open_is_used_not_signal_close():
    data = _dataset((100, 100, 99.5, 99.9), (105, 106, 104, 105), (105, 105, 104, 104.5))
    seen = []

    def provider(frame):
        seen.append((frame.index, len(frame.available_candles)))
        if frame.index == 0:
            return _opportunity(0)
        return None

    def levels(opportunity, frame, entry):
        assert entry == 105
        return entry - 1, entry + 2

    result = RiskAwareBacktestEngine(_config()).run(data, provider, levels)
    assert result.trades
    trade = result.trades[0]
    assert trade.signal_index == 0
    assert trade.entry_index == 1
    assert trade.entry_market_price == 105
    assert seen[0] == (0, 1)


def test_provider_never_receives_future_candles():
    data = _dataset((100, 101, 99, 100), (101, 102, 100, 101), (102, 103, 101, 102))
    lengths = []

    def provider(frame):
        lengths.append((frame.index, len(frame.available_candles)))
        return None

    result = RiskAwareBacktestEngine(_config()).run(data, provider, lambda *_: (99, 101))
    assert result.trade_count == 0
    assert lengths == [(0, 1), (1, 2), (2, 3)]


def test_stop_loss_is_triggered_from_bar_range():
    data = _dataset((100, 100.5, 99.5, 100), (100, 100.5, 98, 99.5), (99, 100, 98, 99))

    def provider(frame):
        return _opportunity(0) if frame.index == 0 else None

    result = RiskAwareBacktestEngine(_config()).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    assert result.trades[0].status is RiskAwareTradeStatus.STOP_LOSS
    assert result.stop_losses == 1


def test_take_profit_is_triggered_from_bar_range():
    data = _dataset((100, 100.5, 99.5, 100), (100, 103, 99.8, 102), (102, 102.5, 101, 102))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    result = RiskAwareBacktestEngine(_config()).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    assert result.trades[0].status is RiskAwareTradeStatus.TAKE_PROFIT
    assert result.take_profits == 1


def test_both_stop_and_target_defaults_to_conservative_stop():
    data = _dataset((100, 100.5, 99.5, 100), (100, 103, 98, 101), (101, 101.5, 100, 101))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    result = RiskAwareBacktestEngine(_config()).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    assert result.trades[0].status is RiskAwareTradeStatus.STOP_LOSS


def test_gap_through_stop_uses_bar_open_and_can_breach_planned_risk():
    data = _dataset((100, 100.5, 99.5, 100), (100, 101, 99.5, 100), (93, 94, 92, 93), (93, 93.5, 92.5, 93))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    result = RiskAwareBacktestEngine(_config()).run(
        data, provider, lambda _, __, entry: (entry - 1, entry + 2)
    )
    trade = result.trades[0]
    assert trade.status is RiskAwareTradeStatus.STOP_LOSS
    assert trade.exit_market_price == 93
    assert trade.risk_budget_breached is True
    assert result.risk_budget_breaches == 1


def test_target_first_policy_is_deterministic():
    data = _dataset((100, 100.5, 99.5, 100), (100, 103, 98, 101), (101, 101.5, 100, 101))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    config = _config(intrabar_policy=IntrabarPolicy.TARGET_FIRST)
    result = RiskAwareBacktestEngine(config).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    assert result.trades[0].status is RiskAwareTradeStatus.TAKE_PROFIT


def test_short_direction_stop_and_target_are_respected():
    data = _dataset((100, 100.5, 99.5, 100), (100, 100.5, 97.5, 99), (99, 99.5, 98, 99))
    provider = lambda frame: _opportunity(0, SignalDirection.SHORT) if frame.index == 0 else None
    result = RiskAwareBacktestEngine(_config()).run(data, provider, lambda _, __, entry: (entry + 1, entry - 2))
    assert result.trades[0].status is RiskAwareTradeStatus.TAKE_PROFIT


def test_position_size_is_risk_based_not_confidence_based():
    data = _dataset((100, 100.5, 99.5, 100), (100, 101, 99, 100), (100, 100, 99, 99.5))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    result = RiskAwareBacktestEngine(_config()).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    assert result.trades[0].quantity == 50.0
    assert result.trades[0].planned_risk_amount == 50.0


def test_minimum_reward_risk_rejects_candidate():
    data = _dataset((100, 100.5, 99.5, 100), (100, 101, 99, 100), (100, 100, 99, 99.5))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    result = RiskAwareBacktestEngine(_config()).run(data, provider, lambda _, __, entry: (entry - 1, entry + 1))
    assert result.trade_count == 0
    assert result.risk_rejections == 1


def test_max_drawdown_is_reported():
    data = _dataset((100, 100.5, 99.5, 100), (100, 101, 98, 99), (99, 99.5, 98, 99))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    result = RiskAwareBacktestEngine(_config()).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    assert result.max_drawdown >= 0


def test_mark_to_market_drawdown_includes_open_trade_loss():
    data = _dataset(
        (100, 100.5, 99.5, 100),
        (100, 101, 94, 95),
        (95, 96, 94.5, 95),
    )
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    result = RiskAwareBacktestEngine(_config(close_at_end=False)).run(
        data, provider, lambda _, __, entry: (entry - 10, entry + 20)
    )
    assert result.trade_count == 0
    assert result.max_drawdown >= 25.0


def test_transaction_costs_reduce_realized_pnl():
    data = _dataset((100, 100.5, 99.5, 100), (100, 103, 99.5, 102), (102, 102.5, 101, 102))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    no_cost = RiskAwareBacktestEngine(_config()).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    friction = ExecutionFrictionConfig(transaction_cost_per_unit=0.01)
    with_cost = RiskAwareBacktestEngine(_config(friction=friction, reject_if_friction_exceeds_planned_risk=False)).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    assert with_cost.final_equity < no_cost.final_equity
    assert with_cost.total_transaction_costs > 0


def test_friction_can_reject_when_worst_case_exceeds_budget():
    data = _dataset((100, 100.5, 99.5, 100), (100, 103, 98, 101), (101, 101.5, 100, 101))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    friction = ExecutionFrictionConfig(spread=0.5)
    result = RiskAwareBacktestEngine(_config(friction=friction)).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    assert result.trade_count == 0
    assert result.risk_rejections == 1


def test_end_of_test_close_is_recorded_when_enabled():
    data = _dataset((100, 100.5, 99.5, 100), (100, 101, 99, 100), (100, 101, 99, 100.5))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    result = RiskAwareBacktestEngine(_config()).run(data, provider, lambda _, __, entry: (entry - 5, entry + 10))
    assert result.trades[0].status is RiskAwareTradeStatus.END_OF_TEST
    assert result.end_of_test_closures == 1


def test_end_of_test_can_leave_position_unrealized():
    data = _dataset((100, 100.5, 99.5, 100), (100, 101, 99, 100), (100, 101, 99, 100.5))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    result = RiskAwareBacktestEngine(_config(close_at_end=False)).run(data, provider, lambda _, __, entry: (entry - 5, entry + 10))
    assert result.trade_count == 0


def test_no_signal_on_last_bar_can_execute():
    data = _dataset((100, 101, 99, 100), (101, 102, 100, 101))
    provider = lambda frame: _opportunity(frame.index) if frame.index == 1 else None
    result = RiskAwareBacktestEngine(_config()).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    assert result.trade_count == 0


def test_warmup_prevents_early_candidates():
    data = _dataset((100, 101, 99, 100), (101, 102, 100, 101), (102, 103, 101, 102))
    provider = lambda frame: _opportunity(frame.index) if frame.index == 2 else None
    result = RiskAwareBacktestEngine(_config(warmup_candles=3)).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    assert result.candidate_opportunities == 1


def test_result_is_serializable():
    data = _dataset((100, 101, 99, 100), (101, 103, 100, 102), (102, 103, 101, 102))
    provider = lambda frame: _opportunity(0) if frame.index == 0 else None
    result = RiskAwareBacktestEngine(_config()).run(data, provider, lambda _, __, entry: (entry - 1, entry + 2))
    payload = result.to_dict()
    assert payload["analysis"] == "risk_aware_backtest"
    assert payload["trade_count"] == result.trade_count


def test_dataset_requires_two_candles():
    data = BacktestDataset(pair="EURUSD", interval="1m", candles=(_candle(0, 100, 101, 99, 100),))
    try:
        RiskAwareBacktestEngine(_config()).run(data, lambda _: None, lambda *_: (99, 101))
    except RiskAwareBacktestError as exc:
        assert "two candles" in str(exc)
    else:
        raise AssertionError("expected RiskAwareBacktestError")
