from market.mongodb_evidence_cohorts import (
    DEFAULT_COHORT_DIMENSIONS,
    MISSING_VALUE,
    summarize_trade_evidence_by_cohort,
    summarize_trade_evidence_by_dimension,
)


class FakeQuery:
    def __init__(self, documents):
        self.documents = [dict(document) for document in documents]

    def find(self, filters=None):
        query = dict(filters or {})
        return [
            dict(document)
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]


def test_default_cohorts_group_by_strategy_market_context_and_pnl():
    q = FakeQuery([
        {"strategy_id": "trend_momentum", "strategy_version": "1.1.2", "symbol": "EURUSD", "timeframe": "5m", "session": "London", "regime": "trend", "direction": "LONG", "realized_pnl": 10},
        {"strategy_id": "trend_momentum", "strategy_version": "1.1.2", "symbol": "EURUSD", "timeframe": "5m", "session": "London", "regime": "trend", "direction": "LONG", "realized_pnl": -4},
        {"strategy_id": "trend_momentum", "strategy_version": "1.1.2", "symbol": "GBPUSD", "timeframe": "5m", "session": "London", "regime": "range", "direction": "LONG", "realized_pnl": 3},
    ])
    result = summarize_trade_evidence_by_cohort(q)
    assert DEFAULT_COHORT_DIMENSIONS == ("strategy_id", "strategy_version", "symbol", "timeframe", "regime", "session")
    assert len(result) == 2
    first = result[0]
    assert first.dimensions == (
        ("strategy_id", "trend_momentum"),
        ("strategy_version", "1.1.2"),
        ("symbol", "EURUSD"),
        ("timeframe", "5m"),
        ("regime", "trend"),
        ("session", "London"),
    )
    assert first.summary.pnl_records == 2
    assert first.summary.total_pnl == 6.0
    assert first.summary.expectancy == 3.0


def test_dimension_attribution_returns_each_value():
    q = FakeQuery([
        {"symbol": "EURUSD", "realized_pnl": 5},
        {"symbol": "EURUSD", "realized_pnl": -2},
        {"symbol": "GBPUSD", "realized_pnl": 4},
    ])
    result = summarize_trade_evidence_by_dimension(q, "symbol")
    assert set(result) == {"EURUSD", "GBPUSD"}
    assert result["EURUSD"].total_pnl == 3.0
    assert result["GBPUSD"].total_pnl == 4.0


def test_missing_dimensions_are_explicitly_retained():
    q = FakeQuery([{"symbol": "EURUSD", "realized_pnl": 1}])
    result = summarize_trade_evidence_by_cohort(q, dimensions=("session", "symbol"))
    assert result[0].dimensions == (("session", MISSING_VALUE), ("symbol", "EURUSD"))


def test_filters_apply_before_cohort_grouping():
    q = FakeQuery([
        {"symbol": "EURUSD", "session": "London", "realized_pnl": 5},
        {"symbol": "EURUSD", "session": "New York", "realized_pnl": -2},
    ])
    result = summarize_trade_evidence_by_cohort(q, {"symbol": "EURUSD"}, ("session",))
    assert [item.dimensions[0][1] for item in result] == ["London", "New York"]
    assert result[0].summary.total_pnl == 5.0
    assert result[1].summary.total_pnl == -2.0


def test_invalid_dimensions_are_rejected():
    q = FakeQuery([])
    for dimensions in ((), ("",), ("symbol", "symbol")):
        try:
            summarize_trade_evidence_by_cohort(q, dimensions=dimensions)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")


def test_invalid_filters_are_rejected():
    try:
        summarize_trade_evidence_by_cohort(FakeQuery([]), filters=[])
    except TypeError:
        pass
    else:
        raise AssertionError("expected TypeError")


def test_cohort_layer_has_no_execution_authority():
    result = summarize_trade_evidence_by_cohort(FakeQuery([]))
    assert not hasattr(result, "buy")
    assert not hasattr(result, "sell")
    assert not hasattr(result, "execute")
