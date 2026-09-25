from market.strategy_allocation import *


def proposed(stage=StrategyLifecycleStage.ELIGIBLE, amount=20.0, risk=2.0):
    return ProposedStrategyAllocation("trend", "1.0", amount, risk, stage)


def criteria(**kwargs):
    values = dict(max_total_allocation=100, max_strategy_allocation=60, max_total_risk_budget=10, max_strategy_risk_budget=6, max_strategy_concentration_ratio=None)
    values.update(kwargs)
    return StrategyAllocationCriteria(**values)


def test_approved_allocatable_strategy():
    a = assess_strategy_allocation(criteria(), [], proposed())
    assert a.status is StrategyAllocationStatus.APPROVED
    assert a.projected_total_allocation == 20
    assert a.execution_authorized is False


def test_lifecycle_blocks_unvalidated_strategy():
    a = assess_strategy_allocation(criteria(), [], proposed(StrategyLifecycleStage.RESEARCH))
    assert a.status is StrategyAllocationStatus.LIFECYCLE_BLOCKED
    assert "proposed_lifecycle_stage_not_allocatable" in a.reasons


def test_total_allocation_limit():
    existing = [StrategyAllocation("mean", "1.0", 90, 2, StrategyLifecycleStage.ELIGIBLE)]
    a = assess_strategy_allocation(criteria(), existing, proposed(amount=20, risk=1))
    assert a.status is StrategyAllocationStatus.LIMIT_EXCEEDED
    assert "total_allocation_limit_exceeded" in a.reasons


def test_strategy_concentration_limit():
    existing = [StrategyAllocation("trend", "1.0", 40, 2, StrategyLifecycleStage.ELIGIBLE), StrategyAllocation("mean", "1.0", 10, 1, StrategyLifecycleStage.ELIGIBLE)]
    a = assess_strategy_allocation(criteria(max_strategy_allocation=100, max_total_allocation=200, max_total_risk_budget=100, max_strategy_risk_budget=100, max_strategy_concentration_ratio=0.7), existing, proposed(amount=40, risk=2))
    assert a.status is StrategyAllocationStatus.CONCENTRATION_EXCEEDED


def test_strategy_risk_limit():
    existing = [StrategyAllocation("trend", "1.0", 10, 5, StrategyLifecycleStage.ELIGIBLE)]
    a = assess_strategy_allocation(criteria(), existing, proposed(amount=10, risk=2))
    assert a.status is StrategyAllocationStatus.LIMIT_EXCEEDED
    assert "strategy_risk_budget_limit_exceeded" in a.reasons


def test_correlation_limit():
    existing = [StrategyAllocation("mean", "1.0", 30, 5, StrategyLifecycleStage.ELIGIBLE)]
    c = criteria(max_correlated_risk_budget=6, require_correlation_data=True)
    a = assess_strategy_allocation(c, existing, proposed(risk=2), {"mean": {"trend": 0.9}})
    assert a.status is StrategyAllocationStatus.CORRELATION_LIMIT_EXCEEDED


def test_missing_correlation_is_not_zero():
    existing = [StrategyAllocation("mean", "1.0", 30, 2, StrategyLifecycleStage.ELIGIBLE)]
    c = criteria(max_correlated_risk_budget=10, require_correlation_data=True)
    a = assess_strategy_allocation(c, existing, proposed(), {})
    assert a.status is StrategyAllocationStatus.INSUFFICIENT_DATA


def test_invalid_values_rejected():
    a = assess_strategy_allocation(criteria(), [], proposed(amount=float("nan")))
    assert a.status is StrategyAllocationStatus.INVALID_ALLOCATION


def test_duplicate_allocations_rejected():
    existing = [StrategyAllocation("trend", "1.0", 10, 1, StrategyLifecycleStage.ELIGIBLE), StrategyAllocation("trend", "1.0", 5, 1, StrategyLifecycleStage.ELIGIBLE)]
    a = assess_strategy_allocation(criteria(), existing, proposed())
    assert a.status is StrategyAllocationStatus.INVALID_ALLOCATION


def test_deterministic_fingerprint():
    a = assess_strategy_allocation(criteria(), [], proposed())
    b = assess_strategy_allocation(criteria(), [], proposed())
    assert a.assessment_fingerprint == b.assessment_fingerprint


def test_allowed_lifecycle_can_be_configured():
    c = criteria(allowed_lifecycle_stages=(StrategyLifecycleStage.MONITORING,))
    a = assess_strategy_allocation(c, [], proposed(StrategyLifecycleStage.ELIGIBLE))
    assert a.status is StrategyAllocationStatus.LIFECYCLE_BLOCKED


def test_missing_risk_is_not_zero():
    a = assess_strategy_allocation(criteria(), [], proposed(risk=0))
    assert a.status is StrategyAllocationStatus.INVALID_ALLOCATION
