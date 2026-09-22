from datetime import datetime, timezone

import pytest

from market.evidence_quality import (
    INCOMPLETE,
    INVALID,
    VALID,
    assess_trade_evidence,
    assess_trade_evidence_record,
)


class FakeQuery:
    def __init__(self, documents):
        self.documents = [dict(document) for document in documents]

    def find(self, filters=None):
        query = dict(filters or {})
        return [dict(d) for d in self.documents if all(d.get(k) == v for k, v in query.items())]


def complete(trade_id="T-1", fingerprint="fp-1"):
    return {
        "trade_id": trade_id,
        "_id": trade_id,
        "evidence_fingerprint": fingerprint,
        "strategy_id": "trend_momentum",
        "strategy_version": "1.1.2",
        "symbol": "EURUSD",
        "timeframe": "5m",
        "regime": "trend",
        "session": "London",
        "timestamp": datetime(2026, 9, 21, tzinfo=timezone.utc),
        "status": "CONFIRMED",
        "realized_pnl": 4.5,
    }


def test_complete_record_is_valid():
    result = assess_trade_evidence_record(complete())
    assert result.status == VALID
    assert result.missing_fields == ()
    assert result.issue_codes == ()


def test_missing_context_is_incomplete_not_invalid():
    document = complete()
    document.pop("session")
    document.pop("regime")
    result = assess_trade_evidence_record(document)
    assert result.status == INCOMPLETE
    assert result.missing_fields == ("regime", "session")
    assert result.issue_codes == ()


def test_structural_and_numeric_corruption_is_invalid():
    document = complete()
    document["_id"] = "OTHER"
    document["timestamp"] = "not-a-timestamp"
    document["realized_pnl"] = "nan"
    result = assess_trade_evidence_record(document)
    assert result.status == INVALID
    assert set(result.issue_codes) == {"trade_id_mismatch", "invalid_timestamp", "invalid_realized_pnl"}


def test_summary_reports_coverage_and_fingerprint_collisions():
    first = complete("T-1", "same-fingerprint")
    second = complete("T-2", "same-fingerprint")
    third = complete("T-3", "unique")
    third.pop("status")
    result = assess_trade_evidence(FakeQuery([first, second, third]))
    assert result.total_records == 3
    assert result.valid_records == 2
    assert result.incomplete_records == 1
    assert result.invalid_records == 0
    assert result.duplicate_fingerprint_records == 2
    assert result.field_coverage["status"] == 2
    assert result.issue_counts == {}
    assert result.assessments[0].fingerprint_occurrences == 2


def test_invalid_realized_pnl_is_counted_without_inferring_profitability():
    document = complete()
    document["realized_pnl"] = float("inf")
    result = assess_trade_evidence(FakeQuery([document]))
    assert result.invalid_records == 1
    assert result.issue_counts == {"invalid_realized_pnl": 1}


def test_filters_apply_before_quality_analysis():
    first = complete("T-1")
    second = complete("T-2")
    second["symbol"] = "GBPUSD"
    result = assess_trade_evidence(FakeQuery([first, second]), {"symbol": "EURUSD"})
    assert result.total_records == 1
    assert result.assessments[0].trade_id == "T-1"


def test_invalid_inputs_are_rejected():
    with pytest.raises(TypeError):
        assess_trade_evidence(FakeQuery([]), filters=[])
    with pytest.raises(TypeError):
        assess_trade_evidence_record([])
    with pytest.raises(ValueError):
        assess_trade_evidence_record(complete(), fingerprint_occurrences=0)


def test_quality_layer_has_no_execution_authority():
    result = assess_trade_evidence(FakeQuery([]))
    assert not hasattr(result, "buy")
    assert not hasattr(result, "sell")
    assert not hasattr(result, "execute")
