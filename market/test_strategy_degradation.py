from market.strategy_degradation import (
    DegradationCriteria,
    DegradationStatus,
    StrategyOutcome,
    assess_strategy_degradation,
    degradation_assessment_is_not_execution_authorization,
)


def _cohort(n, pnl=1.0, risk=1.0, won=True):
    return [
        StrategyOutcome(
            trade_id=f"T{i}", strategy_id="trend_momentum", strategy_version="1.1.2",
            symbol="EURUSD", timeframe="5m", evidence_class="FORWARD",
            realized_pnl=pnl, risk_amount=risk, total_costs=0.1, won=won,
        ) for i in range(n)
    ]


def test_healthy_cohorts_are_not_marked_degraded():
    result = assess_strategy_degradation(DegradationCriteria(), _cohort(30), _cohort(20, pnl=0.9))
    assert result.status is DegradationStatus.HEALTHY


def test_material_expectancy_drop_is_degradation():
    result = assess_strategy_degradation(DegradationCriteria(), _cohort(30), _cohort(20, pnl=0.0, won=False))
    assert result.status is DegradationStatus.DEGRADED
    assert "expectancy_degraded_to_nonpositive" in result.reasons


def test_small_current_sample_is_insufficient():
    result = assess_strategy_degradation(DegradationCriteria(), _cohort(30), _cohort(19))
    assert result.status is DegradationStatus.INSUFFICIENT_DATA


def test_missing_costs_are_not_zero():
    current = [StrategyOutcome(
        trade_id=f"C{i}", strategy_id="trend_momentum", strategy_version="1.1.2",
        symbol="EURUSD", timeframe="5m", evidence_class="FORWARD", realized_pnl=1.0, risk_amount=1.0,
    ) for i in range(20)]
    result = assess_strategy_degradation(DegradationCriteria(), _cohort(30), current)
    assert result.status is DegradationStatus.INSUFFICIENT_DATA
    assert "cost_coverage_incomplete" in result.reasons


def test_missing_risk_is_not_zero():
    current = [StrategyOutcome(
        trade_id=f"C{i}", strategy_id="trend_momentum", strategy_version="1.1.2",
        symbol="EURUSD", timeframe="5m", evidence_class="FORWARD", realized_pnl=1.0, total_costs=0.1,
    ) for i in range(20)]
    result = assess_strategy_degradation(DegradationCriteria(), _cohort(30), current)
    assert result.status is DegradationStatus.INSUFFICIENT_DATA
    assert "risk_coverage_incomplete" in result.reasons


def test_identity_mismatch_is_invalid():
    current = _cohort(20)
    current[0] = StrategyOutcome(**{**current[0].__dict__, "strategy_version": "9.9.9"})
    result = assess_strategy_degradation(DegradationCriteria(), _cohort(30), current)
    assert result.status is DegradationStatus.INVALID_EVIDENCE
    assert "strategy_or_market_identity_mismatch" in result.reasons


def test_evidence_class_isolation_is_enforced():
    current = [StrategyOutcome(**{**r.__dict__, "evidence_class": "LIVE"}) for r in _cohort(20)]
    result = assess_strategy_degradation(DegradationCriteria(), _cohort(30), current)
    assert result.status is DegradationStatus.INVALID_EVIDENCE
    assert "evidence_class_mismatch" in result.reasons


def test_win_rate_drop_can_trigger_degradation():
    baseline = _cohort(30, won=True)
    current = _cohort(20, won=False)
    result = assess_strategy_degradation(DegradationCriteria(), baseline, current)
    assert result.status is DegradationStatus.DEGRADED
    assert "win_rate_drop_limit_exceeded" in result.reasons


def test_profit_factor_drop_can_trigger_degradation():
    baseline = _cohort(30, pnl=2.0, won=True)
    baseline = baseline[:20] + [StrategyOutcome(**{**r.__dict__, "trade_id": f"B{i}", "realized_pnl": -1.0, "won": False}) for i, r in enumerate(baseline[20:])]
    current = _cohort(20, pnl=0.2, won=True)
    current = current[:15] + [StrategyOutcome(**{**r.__dict__, "trade_id": f"C{i}", "realized_pnl": -0.2, "won": False}) for i, r in enumerate(current[15:])]
    result = assess_strategy_degradation(DegradationCriteria(maximum_profit_factor_drop=0.1, maximum_expectancy_degradation_ratio=1.0), baseline, current)
    assert result.status is DegradationStatus.DEGRADED
    assert "profit_factor_drop_limit_exceeded" in result.reasons


def test_fingerprint_is_deterministic_and_sensitive():
    baseline = _cohort(30)
    current = _cohort(20)
    a = assess_strategy_degradation(DegradationCriteria(), baseline, current)
    b = assess_strategy_degradation(DegradationCriteria(), baseline, current)
    assert a.assessment_fingerprint == b.assessment_fingerprint
    changed = list(current)
    changed[0] = StrategyOutcome(**{**changed[0].__dict__, "realized_pnl": 1.5})
    c = assess_strategy_degradation(DegradationCriteria(), baseline, changed)
    assert c.assessment_fingerprint != a.assessment_fingerprint


def test_execution_authority_is_always_false():
    result = assess_strategy_degradation(DegradationCriteria(), _cohort(30), _cohort(20))
    assert degradation_assessment_is_not_execution_authorization(result)
    assert result.execution_authorized is False
