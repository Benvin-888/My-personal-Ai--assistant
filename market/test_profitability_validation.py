from __future__ import annotations

import pytest

from market.profitability_validation import (
    INSUFFICIENT,
    INVALID,
    VALID,
    ProfitabilityValidationCriteria,
    validate_profitability,
)


class FakeQuery:
    def __init__(self, records):
        self.records = list(records)

    def find(self, filters=None):
        if not filters:
            return list(self.records)
        return [r for r in self.records if all(r.get(k) == v for k, v in filters.items())]


def record(i, pnl, *, cost=1.0, risk=10.0, status="CONFIRMED"):
    return {
        "trade_id": f"t{i}",
        "evidence_fingerprint": f"fp{i}",
        "timestamp": f"2026-01-01T00:00:{i:02d}+00:00",
        "status": status,
        "strategy_id": "trend_momentum",
        "strategy_version": "1.1.0",
        "symbol": "EURUSD",
        "timeframe": "5m",
        "regime": "trend",
        "session": "london",
        "realized_pnl": pnl,
        "gross_pnl": pnl + cost,
        "transaction_cost": cost,
        "risk_amount": risk,
    }


def test_valid_profitable_cohort():
    query = FakeQuery([record(i, 5.0) for i in range(30)])
    result = validate_profitability(query)
    assert result.status == VALID
    assert result.realized_pnl_records == 30
    assert result.total_realized_pnl == 150.0
    assert result.failed_checks == ()


def test_small_sample_is_not_called_profitable():
    query = FakeQuery([record(i, 5.0) for i in range(5)])
    result = validate_profitability(query)
    assert result.status == INSUFFICIENT
    assert "minimum_realized_pnl_records" in result.failed_checks


def test_missing_costs_fail_full_cost_coverage():
    rows = [record(i, 5.0) for i in range(30)]
    for row in rows[:3]:
        row.pop("transaction_cost")
        row["gross_pnl"] = 6.0
    result = validate_profitability(FakeQuery(rows))
    assert result.status == INSUFFICIENT
    assert result.cost_coverage_rate < 1.0
    assert "cost_coverage_rate" in result.failed_checks


def test_missing_risk_is_not_zero():
    rows = [record(i, 5.0) for i in range(30)]
    for row in rows[:4]:
        row.pop("risk_amount")
    result = validate_profitability(FakeQuery(rows))
    assert result.status == INSUFFICIENT
    assert result.risk_coverage_rate < 1.0
    assert "risk_coverage_rate" in result.failed_checks


def test_negative_or_zero_pnl_fails_positive_gate():
    result = validate_profitability(FakeQuery([record(i, -1.0) for i in range(30)]))
    assert result.status == INSUFFICIENT
    assert "positive_net_pnl" in result.failed_checks
    assert "profit_factor" in result.failed_checks


def test_invalid_evidence_is_distinguished_from_insufficient_evidence():
    rows = [record(i, 5.0) for i in range(30)]
    rows[0]["trade_id"] = ""
    result = validate_profitability(FakeQuery(rows))
    assert result.status == INVALID
    assert result.invalid_evidence_records >= 1
    assert "invalid_evidence_records" in result.failed_checks


def test_filters_are_applied_before_validation():
    rows = [record(i, 5.0) for i in range(30)] + [record(30 + i, -5.0) for i in range(10)]
    for row in rows[30:]:
        row["symbol"] = "GBPUSD"
    result = validate_profitability(FakeQuery(rows), filters={"symbol": "EURUSD"})
    assert result.status == VALID
    assert result.total_records == 30


def test_custom_criteria_are_enforced():
    rows = [record(i, 2.0) for i in range(20)] + [record(20 + i, -1.0) for i in range(10)]
    criteria = ProfitabilityValidationCriteria(min_profit_factor=5.0)
    result = validate_profitability(FakeQuery(rows), criteria=criteria)
    assert result.status == INSUFFICIENT
    assert "profit_factor" in result.failed_checks


def test_invalid_arguments_rejected():
    with pytest.raises(TypeError):
        validate_profitability(FakeQuery([]), filters=[])
    with pytest.raises(ValueError):
        validate_profitability(FakeQuery([]), tolerance=-1)
    with pytest.raises(ValueError):
        ProfitabilityValidationCriteria(min_cost_coverage_rate=2.0)
