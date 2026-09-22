import pytest

from market.strategy_attribution import MISSING, summarize_strategy_attribution


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


def test_groups_by_strategy_identity_and_version_deterministically():
    result = summarize_strategy_attribution(FakeQuery([
        {"trade_id": "b", "strategy_id": "trend", "strategy_version": "1.1.0", "realized_pnl": -2},
        {"trade_id": "a", "strategy_id": "trend", "strategy_version": "1.1.0", "realized_pnl": 6},
        {"trade_id": "c", "strategy_id": "mean", "strategy_version": "2.0.0", "realized_pnl": 3},
    ]))
    assert [(item.strategy_id, item.strategy_version) for item in result.groups] == [
        ("mean", "2.0.0"),
        ("trend", "1.1.0"),
    ]
    trend = result.groups[1]
    assert trend.total_realized_pnl == pytest.approx(4)
    assert trend.win_rate == pytest.approx(0.5)
    assert trend.expectancy == pytest.approx(2)
    assert result.strategy_count == 2
    assert result.version_count == 2


def test_cost_coverage_is_preserved_per_strategy():
    result = summarize_strategy_attribution(FakeQuery([
        {"trade_id": "a", "strategy_id": "trend", "strategy_version": "1", "gross_pnl": 10, "total_costs": 2},
        {"trade_id": "b", "strategy_id": "trend", "strategy_version": "1", "realized_pnl": 5},
    ]))
    group = result.groups[0]
    assert group.fully_costed_records == 1
    assert group.cost_coverage_rate == pytest.approx(0.5)
    assert group.derived_net_pnl == pytest.approx(8)
    assert group.unpriced_records == 0


def test_missing_strategy_identity_is_explicit_not_dropped():
    result = summarize_strategy_attribution(FakeQuery([
        {"trade_id": "a", "realized_pnl": 5},
        {"trade_id": "b", "strategy_id": "trend", "strategy_version": "1", "realized_pnl": 2},
    ]))
    assert result.unattributed_records == 1
    assert result.groups[0].strategy_id == MISSING
    assert result.groups[0].strategy_version == MISSING
    assert result.groups[1].strategy_id == "trend"


def test_filters_apply_before_attribution():
    result = summarize_strategy_attribution(
        FakeQuery([
            {"trade_id": "a", "symbol": "EURUSD", "strategy_id": "trend", "strategy_version": "1", "realized_pnl": 4},
            {"trade_id": "b", "symbol": "GBPUSD", "strategy_id": "trend", "strategy_version": "1", "realized_pnl": 9},
        ]),
        filters={"symbol": "EURUSD"},
    )
    assert result.total_records == 1
    assert result.groups[0].total_realized_pnl == pytest.approx(4)


def test_attribution_is_descriptive_and_has_no_execution_authority():
    result = summarize_strategy_attribution(FakeQuery([]))
    assert not hasattr(result, "buy")
    assert not hasattr(result, "sell")
    assert not hasattr(result, "execute")


def test_invalid_inputs_are_rejected():
    with pytest.raises(TypeError):
        summarize_strategy_attribution(FakeQuery([]), filters=[])
    with pytest.raises(ValueError):
        summarize_strategy_attribution(FakeQuery([]), tolerance=-1)
