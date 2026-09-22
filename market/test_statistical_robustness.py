from market.statistical_robustness import (
    DESCRIPTIVE_STATISTICS,
    INSUFFICIENT_DATA,
    UNCERTAINTY_QUANTIFIED,
    WITHIN_SAMPLE_STABILITY,
    StatisticalRobustnessCriteria,
    summarize_statistical_robustness,
    summarize_trade_evidence,
)


def _records(n=30):
    return [
        {
            "trade_id": f"T-{i}",
            "realized_pnl": 10.0 if i % 3 else -5.0,
            "total_costs": 1.0,
            "risk_amount": 5.0,
        }
        for i in range(n)
    ]


def test_empty_is_insufficient():
    result = summarize_statistical_robustness([])
    assert result.status == INSUFFICIENT_DATA
    assert result.usable_records == 0


def test_small_sample_is_descriptive_only():
    result = summarize_statistical_robustness(
        [{"realized_pnl": 1.0, "total_costs": 0.1, "risk_amount": 1.0}] * 3,
        criteria=StatisticalRobustnessCriteria(min_sample_size=5, bootstrap_iterations=100),
    )
    assert result.status == DESCRIPTIVE_STATISTICS
    assert result.mean_pnl == 1.0
    assert result.sample_adequate is False


def test_missing_cost_or_risk_does_not_become_zero():
    result = summarize_statistical_robustness(
        [{"realized_pnl": 5.0}] * 30,
        criteria=StatisticalRobustnessCriteria(bootstrap_iterations=50),
    )
    assert result.status == UNCERTAINTY_QUANTIFIED
    assert result.cost_covered_records == 0
    assert result.risk_covered_records == 0
    assert "cost_coverage_incomplete" in result.limitations
    assert "risk_coverage_incomplete" in result.limitations


def test_win_rate_and_descriptive_statistics():
    result = summarize_statistical_robustness(
        [{"realized_pnl": x, "total_costs": 1.0, "risk_amount": 2.0} for x in [10, 5, -2, -3, 0]],
        criteria=StatisticalRobustnessCriteria(min_sample_size=5, bootstrap_iterations=100),
    )
    assert result.wins == 2
    assert result.losses == 2
    assert result.breakeven == 1
    assert result.win_rate == 0.4
    assert result.total_pnl == 10.0
    assert result.median_pnl == 0.0
    assert result.win_rate_interval is not None


def test_bootstrap_is_reproducible():
    records = _records(30)
    criteria = StatisticalRobustnessCriteria(bootstrap_iterations=250, bootstrap_seed=77)
    a = summarize_statistical_robustness(records, criteria=criteria)
    b = summarize_statistical_robustness(records, criteria=criteria)
    assert a.bootstrap_mean_interval == b.bootstrap_mean_interval
    assert a.mean_pnl == b.mean_pnl


def test_concentration_is_visible_without_deleting_observations():
    records = [{"realized_pnl": 100.0, "total_costs": 1.0, "risk_amount": 10.0}]
    records += [{"realized_pnl": 1.0, "total_costs": 1.0, "risk_amount": 1.0}] * 29
    result = summarize_statistical_robustness(
        records,
        criteria=StatisticalRobustnessCriteria(bootstrap_iterations=50),
    )
    assert result.total_pnl == 129.0
    assert result.usable_records == 30
    assert result.pnl_excluding_top_win == 29.0
    assert result.top_wins_pnl == 104.0


def test_invalid_pnl_is_excluded_and_reported():
    records = _records(30) + [{"realized_pnl": float("nan"), "total_costs": 1.0, "risk_amount": 1.0}]
    result = summarize_statistical_robustness(records, criteria=StatisticalRobustnessCriteria(bootstrap_iterations=50))
    assert result.usable_records == 30
    assert result.invalid_pnl_records == 1
    assert "invalid_pnl_records_excluded" in result.limitations


def test_query_adapter_uses_read_only_find():
    class Query:
        def find(self, filters):
            assert filters == {"symbol": "EURUSD"}
            return _records(30)

    result = summarize_trade_evidence(
        Query(),
        filters={"symbol": "EURUSD"},
        criteria=StatisticalRobustnessCriteria(bootstrap_iterations=50),
    )
    assert result.usable_records == 30
    assert result.status == WITHIN_SAMPLE_STABILITY


def test_query_adapter_requires_find():
    try:
        summarize_trade_evidence(object())
    except TypeError as exc:
        assert "find(filters)" in str(exc)
    else:
        raise AssertionError("expected TypeError")


def test_no_execution_or_broker_capability():
    result = summarize_statistical_robustness(_records(30), criteria=StatisticalRobustnessCriteria(bootstrap_iterations=25))
    forbidden = {"execute", "buy", "sell", "cancel", "modify", "authorize"}
    assert not forbidden.intersection(result.__dict__.keys())
