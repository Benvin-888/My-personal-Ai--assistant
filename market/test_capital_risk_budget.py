from market.capital_risk_budget import (
    CapitalRiskBudgetCriteria, CapitalRiskBudgetStatus, CapitalRiskSnapshot,
    ProposedBudgetUse, StrategyBudgetAllocation, assess_capital_risk_budget,
    capital_risk_budget_is_not_execution_authorization,
)


def snap(**kw):
    base = dict(observed_at="2026-09-25T10:00:00Z", account_scope="demo-account",
                account_balance=10000.0, reserved_capital=1000.0, committed_capital=2000.0,
                committed_risk=100.0, capital_budget=7000.0, risk_budget=300.0)
    base.update(kw)
    return CapitalRiskSnapshot(**base)


def prop(**kw):
    base = dict(strategy_id="trend_momentum", strategy_version="1.1.2", capital_required=1000.0, risk_required=40.0)
    base.update(kw)
    return ProposedBudgetUse(**base)


def test_available_when_budgets_cover_use():
    a = assess_capital_risk_budget(snap(), [], prop(), CapitalRiskBudgetCriteria())
    assert a.status is CapitalRiskBudgetStatus.AVAILABLE
    assert a.remaining_capital == 6000.0
    assert a.remaining_risk == 260.0


def test_missing_capital_budget_fails_closed():
    a = assess_capital_risk_budget(snap(capital_budget=None), [], prop(), CapitalRiskBudgetCriteria())
    assert a.status is CapitalRiskBudgetStatus.INSUFFICIENT_DATA
    assert "capital_budget_missing" in a.reasons


def test_missing_risk_budget_fails_closed():
    a = assess_capital_risk_budget(snap(risk_budget=None), [], prop(), CapitalRiskBudgetCriteria())
    assert a.status is CapitalRiskBudgetStatus.INSUFFICIENT_DATA


def test_balance_is_not_capital_budget_by_default():
    a = assess_capital_risk_budget(snap(capital_budget=None), [], prop(), CapitalRiskBudgetCriteria())
    assert a.available_capital is None


def test_explicit_balance_fallback_is_net_of_reserves_and_commitments():
    c = CapitalRiskBudgetCriteria(allow_balance_as_capital_budget=True, require_explicit_capital_budget=True)
    a = assess_capital_risk_budget(snap(capital_budget=None), [], prop(), c)
    assert a.available_capital == 7000.0


def test_capital_exceeded():
    a = assess_capital_risk_budget(snap(), [], prop(capital_required=8000), CapitalRiskBudgetCriteria())
    assert a.status is CapitalRiskBudgetStatus.EXCEEDED
    assert "capital_budget_exceeded" in a.reasons


def test_risk_exceeded():
    a = assess_capital_risk_budget(snap(), [], prop(risk_required=400), CapitalRiskBudgetCriteria())
    assert a.status is CapitalRiskBudgetStatus.EXCEEDED
    assert "risk_budget_exceeded" in a.reasons


def test_strategy_budget_exceeded():
    allocations = [StrategyBudgetAllocation("trend_momentum", "1.1.2", 500.0, 20.0)]
    c = CapitalRiskBudgetCriteria(max_strategy_capital=1000.0, max_strategy_risk=50.0)
    a = assess_capital_risk_budget(snap(), allocations, prop(capital_required=600, risk_required=40), c)
    assert a.status is CapitalRiskBudgetStatus.EXCEEDED
    assert "strategy_capital_budget_exceeded" in a.reasons


def test_invalid_negative_use():
    a = assess_capital_risk_budget(snap(), [], prop(risk_required=-1), CapitalRiskBudgetCriteria())
    assert a.status is CapitalRiskBudgetStatus.INVALID


def test_fingerprint_is_deterministic():
    c = CapitalRiskBudgetCriteria()
    a = assess_capital_risk_budget(snap(), [], prop(), c)
    b = assess_capital_risk_budget(snap(), [], prop(), c)
    assert a.assessment_fingerprint == b.assessment_fingerprint


def test_account_balance_is_not_execution_authority():
    a = assess_capital_risk_budget(snap(), [], prop(), CapitalRiskBudgetCriteria())
    assert capital_risk_budget_is_not_execution_authorization(a)
    assert a.execution_authorized is False


def test_existing_allocations_reduce_remaining_budget():
    allocations = [StrategyBudgetAllocation("mean_reversion", "1.0.0", 2000.0, 80.0)]
    a = assess_capital_risk_budget(snap(), allocations, prop(), CapitalRiskBudgetCriteria())
    assert a.status is CapitalRiskBudgetStatus.AVAILABLE
    assert a.projected_capital_used == 3000.0
    assert a.projected_risk_used == 120.0
    assert a.remaining_capital == 4000.0
    assert a.remaining_risk == 180.0


def test_max_deployable_capital_can_tighten_explicit_budget():
    c = CapitalRiskBudgetCriteria(max_deployable_capital=500.0)
    a = assess_capital_risk_budget(snap(), [], prop(), c)
    assert a.status is CapitalRiskBudgetStatus.EXCEEDED
    assert a.available_capital == 500.0
