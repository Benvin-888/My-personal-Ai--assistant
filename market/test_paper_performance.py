from dataclasses import replace

import pytest

from market.paper import PaperTradingEngine, PaperTradingResult
from market.paper_performance import (
    PaperEvaluationStatus,
    PaperPerformanceEngine,
    PaperPerformanceError,
    PaperPerformancePolicy,
    evaluate_paper_performance,
)
from market.risk import TradePlan


def base_candles():
    return [
        {"timestamp_utc": f"2026-01-01T00:0{i}:00+00:00", "open": 1.1000 + i * 0.0010,
         "high": 1.1020 + i * 0.0010, "low": 1.0990 + i * 0.0010, "close": 1.1010 + i * 0.0010}
        for i in range(5)
    ]


def make_plan(direction="LONG"):
    if direction == "LONG":
        return TradePlan("EURUSD", "5m", "2026-01-01T00:00:00+00:00", "LONG", 1.1000,
                         1.0980, 1.1020, 0.0020, 0.0020, 1.0, 1000.0, 2.0, 0.0002)
    return TradePlan("EURUSD", "5m", "2026-01-01T00:00:00+00:00", "SHORT", 1.1000,
                     1.1020, 1.0980, 0.0020, 0.0020, 1.0, 1000.0, 2.0, 0.0002)


def profitable_result():
    # First prefix produces a target hit on the next bar.
    candles = [
        {"timestamp_utc": "2026-01-01T00:00:00+00:00", "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1005},
        {"timestamp_utc": "2026-01-01T00:05:00+00:00", "open": 1.1005, "high": 1.1030, "low": 1.1000, "close": 1.1025},
        {"timestamp_utc": "2026-01-01T00:10:00+00:00", "open": 1.1025, "high": 1.1040, "low": 1.1020, "close": 1.1030},
    ]
    return PaperTradingEngine().run(candles, lambda frame: make_plan() if len(frame) == 1 else None)


def test_metrics_measure_net_and_trade_statistics():
    result = profitable_result()
    evaluation = evaluate_paper_performance(result, policy=PaperPerformancePolicy(minimum_trades=1))
    m = evaluation.metrics
    assert m.trade_count == 1
    assert m.winning_trades == 1
    assert m.net_pnl == pytest.approx(result.realized_pnl)
    assert m.gross_profit > 0
    assert m.gross_loss == 0
    assert m.profit_factor is None
    assert m.average_r_multiple > 0
    assert m.return_pct > 0


def test_small_sample_is_insufficient_not_pass():
    evaluation = PaperPerformanceEngine().evaluate(profitable_result())
    assert evaluation.status is PaperEvaluationStatus.INSUFFICIENT_DATA
    assert evaluation.economically_credible is False


def test_positive_result_can_pass_with_small_test_policy():
    policy = PaperPerformancePolicy(minimum_trades=1)
    evaluation = PaperPerformanceEngine(policy).evaluate(profitable_result())
    assert evaluation.status is PaperEvaluationStatus.PASS
    assert evaluation.economically_credible is True


def test_fingerprint_is_deterministic():
    a = evaluate_paper_performance(profitable_result(), policy=PaperPerformancePolicy(minimum_trades=1))
    b = evaluate_paper_performance(profitable_result(), policy=PaperPerformancePolicy(minimum_trades=1))
    assert a.evidence_fingerprint == b.evidence_fingerprint


def test_source_fingerprint_is_preserved():
    result = profitable_result()
    evaluation = evaluate_paper_performance(result, policy=PaperPerformancePolicy(minimum_trades=1))
    assert evaluation.metadata["source_paper_evidence_fingerprint"] == result.evidence_fingerprint


def test_group_metadata_supports_session_and_regime_evidence():
    result = profitable_result()
    trade_id = result.trades[0].trade_id
    evaluation = evaluate_paper_performance(
        result,
        policy=PaperPerformancePolicy(minimum_trades=1),
        group_metadata={trade_id: {"session": "London", "regime": "TREND"}},
    )
    keys = {(g.group_key, g.group_value) for g in evaluation.groups}
    assert ("session", "London") in keys
    assert ("regime", "TREND") in keys


def test_unknown_group_trade_is_rejected():
    with pytest.raises(PaperPerformanceError):
        evaluate_paper_performance(profitable_result(), group_metadata={"UNKNOWN": {"session": "London"}})


def test_invalid_group_metadata_type_is_rejected():
    result = profitable_result()
    with pytest.raises(PaperPerformanceError):
        PaperPerformanceEngine().evaluate(result, group_metadata={result.trades[0].trade_id: "London"})


def test_equity_reconciliation_is_enforced():
    result = profitable_result()
    bad = replace(result, ending_equity=result.ending_equity + 1.0)
    with pytest.raises(PaperPerformanceError):
        PaperPerformanceEngine().evaluate(bad)


def test_realized_pnl_reconciliation_is_enforced():
    result = profitable_result()
    bad = replace(result, realized_pnl=result.realized_pnl + 1.0)
    with pytest.raises(PaperPerformanceError):
        PaperPerformanceEngine().evaluate(bad)


def test_policy_rejects_invalid_trade_count():
    with pytest.raises(PaperPerformanceError):
        PaperPerformancePolicy(minimum_trades=0)


def test_policy_rejects_invalid_drawdown_fraction():
    with pytest.raises(PaperPerformanceError):
        PaperPerformancePolicy(maximum_drawdown_fraction=1.5)


def test_policy_rejects_invalid_cost_burden_fraction():
    with pytest.raises(PaperPerformanceError):
        PaperPerformancePolicy(maximum_cost_burden_fraction=-0.1)


def test_metadata_declares_no_execution_authority():
    evaluation = evaluate_paper_performance(profitable_result(), policy=PaperPerformancePolicy(minimum_trades=1))
    assert evaluation.metadata["broker_access"] is False
    assert evaluation.metadata["execution_authorization"] is False
    assert evaluation.metadata["order_placement"] is False


def test_to_dict_is_structured_and_immutable_result():
    evaluation = evaluate_paper_performance(profitable_result(), policy=PaperPerformancePolicy(minimum_trades=1))
    payload = evaluation.to_dict()
    assert payload["status"] == "PASS"
    assert payload["metrics"]["trade_count"] == 1
    assert payload["economically_credible"] is True


def test_duration_metrics_are_positive_for_closed_trade():
    evaluation = evaluate_paper_performance(profitable_result(), policy=PaperPerformancePolicy(minimum_trades=1))
    assert evaluation.metrics.average_trade_duration_seconds >= 0
    assert evaluation.metrics.median_trade_duration_seconds >= 0


def test_default_policy_does_not_make_a_profitability_claim():
    evaluation = evaluate_paper_performance(profitable_result())
    assert evaluation.metadata["profitability_guarantee"] is False


def test_failed_economic_checks_are_not_promoted():
    policy = PaperPerformancePolicy(minimum_trades=1, minimum_expectancy=2.0)
    evaluation = evaluate_paper_performance(profitable_result(), policy=policy)
    assert evaluation.status is PaperEvaluationStatus.FAIL
    assert any(check.name == "expectancy" and not check.passed for check in evaluation.checks)
