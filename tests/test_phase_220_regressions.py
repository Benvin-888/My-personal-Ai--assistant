from datetime import datetime, timezone

import pytest

from brain import _resolve_contextual_path
from context import create_default_context
from market import __version__
from market.backtest.version import __version__ as backtest_version
from market.paper import PaperTradingEngine, PaperTradingError
from market.research.version import __version__ as research_version
from market.risk import TradePlan
from market.backtest.friction import ExecutionFrictionConfig, ExecutionFrictionModel


def _candles():
    return [
        {"timestamp_utc": "2026-01-01T00:00:00+00:00", "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1005},
        {"timestamp_utc": "2026-01-01T00:05:00+00:00", "open": 1.1005, "high": 1.1040, "low": 1.1000, "close": 1.1035},
        {"timestamp_utc": "2026-01-01T00:10:00+00:00", "open": 1.1035, "high": 1.1050, "low": 1.1020, "close": 1.1040},
    ]


def _plan():
    return TradePlan("EURUSD", "5m", "2026-01-01T00:00:00+00:00", "LONG", 1.1000,
                     1.0980, 1.1040, 0.0020, 0.0040, 2.0, 1000.0, 2.0, 0.0002)


def test_paper_costs_count_each_fill_once():
    friction = ExecutionFrictionModel(ExecutionFrictionConfig(fixed_transaction_cost=1.0))
    result = PaperTradingEngine(friction=friction).run(_candles(), lambda frame: _plan() if len(frame) == 1 else None)
    trade = result.trades[0]
    assert result.total_costs == pytest.approx(trade.entry_cost + trade.exit_cost)
    assert result.realized_pnl == pytest.approx(trade.net_pnl)


def test_completed_trade_preserves_planned_and_actual_entry_prices():
    result = PaperTradingEngine().run(_candles(), lambda frame: _plan() if len(frame) == 1 else None)
    trade = result.trades[0]
    assert trade.plan_entry_price == pytest.approx(1.1000)
    assert trade.actual_entry_price == pytest.approx(1.1005)


def test_timestamp_ordering_uses_instants_not_strings():
    bars = _candles()
    bars[1] = dict(bars[1], timestamp_utc="2026-01-01T00:30:00+01:00")
    with pytest.raises(PaperTradingError):
        PaperTradingEngine().run(bars, lambda _: None)


def test_naive_timestamps_are_rejected():
    bars = _candles()
    bars[0] = dict(bars[0], timestamp_utc="2026-01-01T00:00:00")
    with pytest.raises(PaperTradingError):
        PaperTradingEngine().run(bars, lambda _: None)


def test_context_resolver_reads_wrapped_tool_result(monkeypatch):
    import brain
    monkeypatch.setattr(brain, "_get_context_snapshot", lambda: {
        "last_action": None,
        "last_tool_result": {"result": {"search_root": "C:/Benvin"}, "timestamp": "2026-01-01T00:00:00Z"},
        "variables": {},
    })
    assert _resolve_contextual_path() == "C:/Benvin"


def test_versions_are_consistent():
    assert __version__ == "2.49.0"
    assert research_version == __version__
    assert backtest_version == __version__
