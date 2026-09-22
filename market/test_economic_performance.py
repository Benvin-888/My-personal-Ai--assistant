import pytest

from market.economic_performance import (
    assess_economic_record,
    summarize_economic_performance,
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


def test_realized_pnl_remains_authoritative_net_outcome():
    result = summarize_economic_performance(FakeQuery([
        {"trade_id": "a", "realized_pnl": 10, "gross_pnl": 12, "total_costs": 2},
        {"trade_id": "b", "realized_pnl": -4, "gross_pnl": -3, "total_costs": 1},
    ]))
    assert result.total_realized_pnl == pytest.approx(6)
    assert result.win_rate == pytest.approx(0.5)
    assert result.total_explicit_costs == pytest.approx(3)
    assert result.cost_coverage_rate == pytest.approx(1.0)
    assert result.derived_net_pnl == pytest.approx(6)
    assert result.inconsistent_records == 0


def test_component_costs_are_summed_only_when_explicitly_supplied():
    assessment = assess_economic_record({
        "trade_id": "a",
        "gross_pnl": 10,
        "transaction_cost": 1,
        "slippage_cost": 0.5,
        "financing_cost": 0.25,
    })
    assert assessment.explicit_costs == pytest.approx(1.75)
    assert assessment.derived_net_pnl == pytest.approx(8.25)
    assert assessment.fully_costed is True


def test_missing_costs_are_not_assumed_to_be_zero():
    result = summarize_economic_performance(FakeQuery([
        {"trade_id": "a", "realized_pnl": 5},
        {"trade_id": "b", "gross_pnl": 7},
    ]))
    assert result.total_realized_pnl == 5.0
    assert result.total_explicit_costs is None
    assert result.fully_costed_records == 0
    assert result.cost_coverage_rate == pytest.approx(0.0)
    assert result.unpriced_records == 1


def test_derived_net_is_available_without_realized_pnl_when_gross_and_costs_exist():
    result = summarize_economic_performance(FakeQuery([
        {"trade_id": "a", "gross_pnl": 10, "total_costs": 2},
        {"trade_id": "b", "gross_pnl": -4, "total_costs": 1},
    ]))
    assert result.realized_pnl_records == 0
    assert result.derived_net_pnl == pytest.approx(3)
    assert result.economic_pnl_records == 2


def test_invalid_numeric_values_do_not_become_economic_outcomes():
    assessment = assess_economic_record({
        "trade_id": "a",
        "realized_pnl": "not-a-number",
        "gross_pnl": "nan",
        "total_costs": "inf",
    })
    assert assessment.priced is False
    assert assessment.derived_net_pnl is None


def test_filters_are_applied_before_summary():
    result = summarize_economic_performance(
        FakeQuery([
            {"trade_id": "a", "symbol": "EURUSD", "realized_pnl": 5},
            {"trade_id": "b", "symbol": "GBPUSD", "realized_pnl": 8},
        ]),
        filters={"symbol": "EURUSD"},
    )
    assert result.total_records == 1
    assert result.total_realized_pnl == 5.0


def test_invalid_filters_and_tolerance_are_rejected():
    with pytest.raises(TypeError):
        summarize_economic_performance(FakeQuery([]), filters=[])
    with pytest.raises(ValueError):
        assess_economic_record({}, tolerance=-1)


def test_economic_layer_has_no_execution_authority():
    result = summarize_economic_performance(FakeQuery([]))
    assert not hasattr(result, "buy")
    assert not hasattr(result, "sell")
    assert not hasattr(result, "execute")
