import pytest

from market.risk_adjusted_performance import summarize_risk_adjusted_performance


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


def test_calculates_explicit_risk_metrics_and_realized_path_drawdown():
    result = summarize_risk_adjusted_performance(FakeQuery([
        {"trade_id": "a", "timestamp": "2026-01-01T00:00:00+00:00", "realized_pnl": 5, "risk_amount": 2},
        {"trade_id": "b", "timestamp": "2026-01-02T00:00:00+00:00", "realized_pnl": -3, "risk_amount": 2},
        {"trade_id": "c", "timestamp": "2026-01-03T00:00:00+00:00", "realized_pnl": 6, "risk_amount": 3},
    ]))
    assert result.total_realized_pnl == pytest.approx(8)
    assert result.total_explicit_risk == pytest.approx(7)
    assert result.average_explicit_risk == pytest.approx(7 / 3)
    assert result.risk_coverage_rate == pytest.approx(1)
    assert result.pnl_to_risk_ratio == pytest.approx(8 / 7)
    assert result.max_realized_pnl_drawdown == pytest.approx(3)
    assert result.realized_pnl_drawdown_ratio == pytest.approx(8 / 3)
    assert result.risk_adjusted_expectancy == pytest.approx(8 / 3)


def test_missing_risk_is_not_treated_as_zero():
    result = summarize_risk_adjusted_performance(FakeQuery([
        {"trade_id": "a", "realized_pnl": 5},
        {"trade_id": "b", "realized_pnl": -2, "risk_amount": 2},
    ]))
    assert result.risk_covered_records == 1
    assert result.unrisked_records == 1
    assert result.risk_coverage_rate == pytest.approx(0.5)
    assert result.total_explicit_risk == pytest.approx(2)


def test_invalid_or_negative_risk_is_unavailable():
    result = summarize_risk_adjusted_performance(FakeQuery([
        {"trade_id": "a", "realized_pnl": 5, "risk_amount": -1},
        {"trade_id": "b", "realized_pnl": 2, "risk_amount": "bad"},
    ]))
    assert result.risk_covered_records == 0
    assert result.total_explicit_risk is None
    assert result.pnl_to_risk_ratio is None


def test_cost_coverage_remains_separate_from_risk_coverage():
    result = summarize_risk_adjusted_performance(FakeQuery([
        {"trade_id": "a", "gross_pnl": 10, "total_costs": 2, "realized_pnl": 8, "risk_amount": 4},
        {"trade_id": "b", "realized_pnl": 3, "risk_amount": 1},
    ]))
    assert result.fully_costed_records == 1
    assert result.cost_coverage_rate == pytest.approx(0.5)
    assert result.risk_covered_records == 2
    assert result.risk_coverage_rate == pytest.approx(1)


def test_filters_apply_before_calculation():
    result = summarize_risk_adjusted_performance(
        FakeQuery([
            {"trade_id": "a", "symbol": "EURUSD", "realized_pnl": 4, "risk_amount": 2},
            {"trade_id": "b", "symbol": "GBPUSD", "realized_pnl": 9, "risk_amount": 3},
        ]),
        filters={"symbol": "EURUSD"},
    )
    assert result.total_records == 1
    assert result.total_realized_pnl == pytest.approx(4)
    assert result.pnl_to_risk_ratio == pytest.approx(2)


def test_empty_cohort_has_no_false_risk_metrics():
    result = summarize_risk_adjusted_performance(FakeQuery([]))
    assert result.total_records == 0
    assert result.total_explicit_risk is None
    assert result.max_realized_pnl_drawdown is None
    assert result.risk_adjusted_expectancy is None


def test_invalid_inputs_are_rejected():
    with pytest.raises(TypeError):
        summarize_risk_adjusted_performance(FakeQuery([]), filters=[])
    with pytest.raises(ValueError):
        summarize_risk_adjusted_performance(FakeQuery([]), tolerance=-1)
