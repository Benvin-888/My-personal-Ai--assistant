from market.paper import (
    PaperEventType, PaperIntrabarPolicy, PaperTradeStatus, PaperTradingConfig,
    PaperTradingEngine, PaperTradingError,
)
from market.risk import TradePlan


def candles():
    return [
        {"timestamp_utc":"2026-01-01T00:00:00+00:00","open":1.1000,"high":1.1010,"low":1.0990,"close":1.1005},
        {"timestamp_utc":"2026-01-01T00:05:00+00:00","open":1.1005,"high":1.1040,"low":1.1000,"close":1.1035},
        {"timestamp_utc":"2026-01-01T00:10:00+00:00","open":1.1035,"high":1.1050,"low":1.1020,"close":1.1040},
    ]


def plan():
    return TradePlan("EURUSD", "5m", "2026-01-01T00:00:00+00:00", "LONG", 1.1000,
                     1.0980, 1.1040, 0.0020, 0.0040, 2.0, 1000.0, 2.0, 0.0002)


def test_next_bar_entry_and_target_exit():
    result = PaperTradingEngine().run(candles(), lambda frame: plan() if len(frame) == 1 else None)
    assert len(result.trades) == 1
    assert result.trades[0].status is PaperTradeStatus.TAKE_PROFIT
    assert result.trades[0].entry_timestamp_utc == candles()[1]["timestamp_utc"]
    assert result.events[0].event_type is PaperEventType.ENTRY
    assert result.metadata["broker_access"] is False


def test_provider_receives_only_prefix():
    seen = []
    def provider(frame):
        seen.append(len(frame))
        return None
    PaperTradingEngine().run(candles(), provider)
    assert seen == [1, 2]


def test_conservative_collision_prefers_stop():
    bars = [candles()[0], {"timestamp_utc":"2026-01-01T00:05:00+00:00","open":1.1005,"high":1.1045,"low":1.0975,"close":1.101}]
    result = PaperTradingEngine().run(bars, lambda frame: plan() if len(frame) == 1 else None)
    assert result.trades[0].status is PaperTradeStatus.STOP_LOSS


def test_target_first_is_explicit():
    bars = [candles()[0], {"timestamp_utc":"2026-01-01T00:05:00+00:00","open":1.1005,"high":1.1045,"low":1.0975,"close":1.101}]
    result = PaperTradingEngine(PaperTradingConfig(intrabar_policy=PaperIntrabarPolicy.TARGET_FIRST)).run(
        bars, lambda frame: plan() if len(frame) == 1 else None)
    assert result.trades[0].status is PaperTradeStatus.TAKE_PROFIT


def test_end_of_test_closes_open_position():
    bars = [candles()[0], candles()[2]]
    def open_plan(frame):
        return TradePlan("EURUSD", "5m", "2026-01-01T00:00:00+00:00", "LONG", 1.1000,
                         1.0980, 1.2000, 0.0020, 0.1000, 50.0, 1000.0, 2.0, 0.0002)
    result = PaperTradingEngine().run(bars, open_plan)
    assert result.trades[0].status is PaperTradeStatus.END_OF_TEST


def test_friction_costs_are_recorded():
    from market.backtest.friction import ExecutionFrictionConfig, ExecutionFrictionModel
    friction = ExecutionFrictionModel(ExecutionFrictionConfig(spread=0.0002, slippage=0.0001, fixed_transaction_cost=1.0))
    result = PaperTradingEngine(friction=friction).run(candles(), lambda frame: plan() if len(frame) == 1 else None)
    assert result.total_costs > 0
    assert result.trades[0].entry_cost > 0


def test_rejects_invalid_ohlc():
    bad = candles(); bad[0] = dict(bad[0], high=1.0)
    try:
        PaperTradingEngine().run(bad, lambda _: None)
    except PaperTradingError:
        return
    assert False


def test_rejects_nonchronological_timestamps():
    bars = candles(); bars[1] = dict(bars[1], timestamp_utc=bars[0]["timestamp_utc"])
    try:
        PaperTradingEngine().run(bars, lambda _: None)
    except PaperTradingError:
        return
    assert False


def test_rejects_non_trade_plan():
    try:
        PaperTradingEngine().run(candles(), lambda frame: object() if len(frame) == 1 else None)
    except PaperTradingError:
        return
    assert False


def test_fingerprint_is_deterministic():
    provider = lambda frame: plan() if len(frame) == 1 else None
    a = PaperTradingEngine().run(candles(), provider)
    b = PaperTradingEngine().run(candles(), provider)
    assert a.evidence_fingerprint == b.evidence_fingerprint


def test_single_position_prevents_stacking():
    def provider(frame):
        return plan()
    result = PaperTradingEngine().run(candles(), provider)
    entries = [e for e in result.events if e.event_type is PaperEventType.ENTRY]
    exits = [e for e in result.events if e.event_type is PaperEventType.EXIT]
    assert len(entries) == len(exits)
    assert len(entries) == 2
    assert all(entries[i].event_id < exits[i].event_id for i in range(len(entries)))
