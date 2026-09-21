from market.mongodb_evidence_analytics import summarize_trade_evidence


class FakeQuery:
    def __init__(self, documents):
        self.documents = list(documents)

    def find(self, filters=None):
        query = dict(filters or {})
        return [dict(d) for d in self.documents if all(d.get(k) == v for k, v in query.items())]


def test_performance_summary_uses_explicit_realized_pnl_only():
    q = FakeQuery([
        {"trade_id": "T-1", "symbol": "EURUSD", "status": "CONFIRMED", "realized_pnl": 10},
        {"trade_id": "T-2", "symbol": "EURUSD", "status": "FAILED", "realized_pnl": -4},
        {"trade_id": "T-3", "symbol": "GBPUSD", "status": "CONFIRMED", "realized_pnl": 0},
        {"trade_id": "T-4", "symbol": "GBPUSD", "status": "UNKNOWN"},
    ])
    result = summarize_trade_evidence(q)
    assert result.total_records == 4
    assert result.status_counts == {"CONFIRMED": 2, "FAILED": 1, "UNKNOWN": 1}
    assert result.symbols == {"EURUSD": 2, "GBPUSD": 2}
    assert result.pnl_records == 3
    assert result.winning_trades == 1
    assert result.losing_trades == 1
    assert result.breakeven_trades == 1
    assert result.total_pnl == 6.0
    assert result.gross_profit == 10.0
    assert result.gross_loss == -4.0
    assert result.win_rate == 1 / 3
    assert result.profit_factor == 2.5
    assert result.expectancy == 2.0


def test_filters_and_no_pnl_return_none_for_pnl_metrics():
    q = FakeQuery([
        {"trade_id": "T-1", "symbol": "EURUSD", "status": "CONFIRMED"},
        {"trade_id": "T-2", "symbol": "GBPUSD", "status": "FAILED", "realized_pnl": "bad"},
    ])
    result = summarize_trade_evidence(q, {"symbol": "EURUSD"})
    assert result.total_records == 1
    assert result.symbols == {"EURUSD": 1}
    assert result.pnl_records == 0
    assert result.total_pnl is None
    assert result.win_rate is None
    assert result.profit_factor is None
    assert result.expectancy is None


def test_invalid_filters_are_rejected():
    try:
        summarize_trade_evidence(FakeQuery([]), [])
    except TypeError:
        pass
    else:
        raise AssertionError("expected TypeError")


def test_analytics_has_no_execution_authority():
    result = summarize_trade_evidence(FakeQuery([]))
    assert not hasattr(result, "buy")
    assert not hasattr(result, "sell")
    assert not hasattr(result, "execute")
