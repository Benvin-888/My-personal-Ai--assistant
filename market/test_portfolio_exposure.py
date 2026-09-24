from market.portfolio_exposure import *


def pos(i, symbol="EURUSD", strategy="trend", risk=10, fx=None):
    return PortfolioPosition(i, symbol, strategy, risk, fx or {"EUR": 10, "USD": -10})


def prop(symbol="GBPUSD", strategy="trend", risk=10, fx=None):
    return ProposedExposure("P-1", symbol, strategy, risk, fx or {"GBP": 10, "USD": -10})


def test_approves_within_limits():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(max_total_risk=50, max_symbol_risk=30), [pos("T-1")], prop())
    assert a.status is PortfolioExposureStatus.APPROVED
    assert a.execution_authorized is False


def test_total_risk_limit():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(max_total_risk=15), [pos("T-1")], prop())
    assert a.status is PortfolioExposureStatus.RISK_LIMIT_EXCEEDED
    assert "total_risk_limit_exceeded" in a.reasons


def test_symbol_concentration():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(max_symbol_risk=15), [pos("T-1", "EURUSD")], prop("EURUSD"))
    assert a.status is PortfolioExposureStatus.RISK_LIMIT_EXCEEDED
    assert "symbol_risk_limit_exceeded" in a.reasons


def test_strategy_limit():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(max_strategy_risk=15), [pos("T-1", strategy="trend")], prop(strategy="trend"))
    assert a.status is PortfolioExposureStatus.RISK_LIMIT_EXCEEDED


def test_currency_limit():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(max_currency_abs_exposure=15), [pos("T-1")], prop())
    assert a.status is PortfolioExposureStatus.LIMIT_EXCEEDED


def test_concentration_limit():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(max_concentration_ratio=0.2), [pos("T-1", risk=30)], prop(risk=10))
    assert a.status is PortfolioExposureStatus.CONCENTRATION_EXCEEDED


def test_correlation_limit():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(max_correlated_risk=15), [pos("T-1", "EURUSD")], prop("GBPUSD"), {"EURUSD":{"GBPUSD":0.9}})
    assert a.status is PortfolioExposureStatus.CORRELATION_LIMIT_EXCEEDED
    assert a.correlated_risk == 20


def test_missing_required_correlation_data():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(require_correlation_data=True), [pos("T-1")], prop())
    assert a.status is PortfolioExposureStatus.INSUFFICIENT_DATA


def test_correlation_is_symmetric():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(max_correlated_risk=15), [pos("T-1", "EURUSD")], prop("GBPUSD"), {"GBPUSD":{"EURUSD":0.9}})
    assert a.status is PortfolioExposureStatus.CORRELATION_LIMIT_EXCEEDED


def test_invalid_duplicate_position():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(), [pos("T-1"), pos("T-1")], prop())
    assert a.status is PortfolioExposureStatus.INVALID_EXPOSURE


def test_invalid_nonfinite_currency():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(), [pos("T-1")], prop(fx={"GBP": float("nan")}))
    assert a.status is PortfolioExposureStatus.INVALID_EXPOSURE


def test_requires_positive_risk_by_default():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(), [], prop(risk=0))
    assert a.status is PortfolioExposureStatus.INVALID_EXPOSURE


def test_fingerprint_is_deterministic():
    c = PortfolioExposureCriteria(max_total_risk=50)
    a = assess_portfolio_exposure(c, [pos("T-1")], prop())
    b = assess_portfolio_exposure(c, [pos("T-1")], prop())
    assert a.assessment_fingerprint == b.assessment_fingerprint


def test_fingerprint_changes_with_proposed_exposure():
    c = PortfolioExposureCriteria(max_total_risk=50)
    a = assess_portfolio_exposure(c, [pos("T-1")], prop(risk=10))
    b = assess_portfolio_exposure(c, [pos("T-1")], prop(risk=11))
    assert a.proposed_fingerprint != b.proposed_fingerprint
    assert a.assessment_fingerprint != b.assessment_fingerprint


def test_no_execution_authority():
    a = assess_portfolio_exposure(PortfolioExposureCriteria(), [], prop())
    assert portfolio_assessment_is_not_execution_authorization(a)
    assert not hasattr(a, "buy")
