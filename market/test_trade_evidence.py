from market.performance_journal import InMemoryPerformanceJournal
from market.trade_evidence import TradeEvidence


def test_trade_evidence_round_trip():
    evidence = TradeEvidence(
        "t1", "trend_momentum", "1.1.2",
        "EURUSD", "5m", "trend",
        "london", "abc"
    )

    journal = InMemoryPerformanceJournal()
    journal.record(evidence)

    assert journal.get("t1") == evidence
    assert evidence.to_dict()["strategy_id"] == "trend_momentum"


def test_evidence_has_no_execution_capability():
    evidence = TradeEvidence(
        "t1", "s", "v", "EURUSD",
        "5m", "trend", "london", "fp"
    )
    assert not hasattr(evidence, "execute")
    assert not hasattr(evidence, "buy")
