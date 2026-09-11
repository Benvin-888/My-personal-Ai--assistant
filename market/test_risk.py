from __future__ import annotations

from types import SimpleNamespace

import pytest

from market.risk import (
    AccountSnapshot,
    ExposureSnapshot,
    RiskEngine,
    RiskManagementError,
    RiskPolicy,
    RiskStatus,
    StopLossPolicy,
    StopMethod,
    TakeProfitPolicy,
    TargetMethod,
    assess_risk,
)


def opportunity(direction="LONG", candidate=True):
    return SimpleNamespace(
        pair="EURUSD",
        interval="5m",
        timestamp_utc="2026-09-11T10:00:00+00:00",
        direction=direction,
        is_candidate=candidate,
    )


def account(equity=10_000.0, peak_equity=None):
    return AccountSnapshot(equity=equity, peak_equity=peak_equity)


def test_default_policy_is_conservative_and_serializable():
    policy = RiskPolicy()
    assert policy.default_risk_fraction == pytest.approx(0.005)
    assert policy.max_risk_fraction_per_trade == pytest.approx(0.01)
    assert policy.to_dict()["minimum_reward_risk"] == pytest.approx(1.5)


def test_account_drawdown_is_deterministic():
    assert account(9000, 10000).drawdown_fraction == pytest.approx(0.10)


def test_stop_price_distance():
    policy = StopLossPolicy(method=StopMethod.PRICE_DISTANCE, distance=0.002)
    assert policy.calculate(1.1) == pytest.approx(0.002)


def test_stop_fixed_pips():
    policy = StopLossPolicy(method=StopMethod.FIXED_PIPS, pips=20)
    assert policy.calculate(1.1, pip_size=0.0001) == pytest.approx(0.002)


def test_stop_atr_multiple():
    policy = StopLossPolicy(method=StopMethod.ATR_MULTIPLE, atr_multiple=2)
    assert policy.calculate(1.1, atr=0.0015) == pytest.approx(0.003)


def test_target_reward_risk():
    policy = TakeProfitPolicy(method=TargetMethod.REWARD_RISK, reward_risk=2)
    assert policy.calculate(1.1, 0.002) == pytest.approx(0.004)


def test_target_fixed_pips():
    policy = TakeProfitPolicy(method=TargetMethod.FIXED_PIPS, pips=30)
    assert policy.calculate(1.1, 0.002, pip_size=0.0001) == pytest.approx(0.003)


def test_candidate_is_approved_with_valid_plan():
    result = assess_risk(
        opportunity(),
        entry_price=1.1000,
        stop_loss=1.0980,
        take_profit=1.1030,
        account=account(),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert result.status == RiskStatus.APPROVED
    assert result.plan is not None
    assert result.plan.quantity == pytest.approx(0.25)
    assert result.plan.reward_risk == pytest.approx(1.5)
    assert result.approved is True


def test_short_direction_validates_reverse_geometry():
    result = assess_risk(
        opportunity("SHORT"),
        entry_price=1.1000,
        stop_loss=1.1020,
        take_profit=1.0970,
        account=account(),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert result.status == RiskStatus.APPROVED
    assert result.plan.direction == "SHORT"


def test_long_stop_must_be_below_entry():
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.101,
        take_profit=1.104,
        account=account(),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert result.status == RiskStatus.REJECTED
    assert "LONG stop-loss" in result.reasons[0]


def test_short_target_must_be_below_entry():
    result = assess_risk(
        opportunity("SHORT"),
        entry_price=1.1,
        stop_loss=1.101,
        take_profit=1.101,
        account=account(),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert result.status == RiskStatus.REJECTED
    assert "SHORT take-profit" in result.reasons[0]


def test_reward_risk_minimum_is_enforced():
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.1005,
        account=account(),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert result.status == RiskStatus.REJECTED
    assert "reward-to-risk" in result.reasons[0]


def test_risk_fraction_cannot_exceed_policy():
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(),
        risk_fraction=0.02,
        value_per_price_unit=100_000,
    )
    assert result.status == RiskStatus.REJECTED
    assert "per-trade maximum" in result.reasons[0]


def test_total_risk_limit_is_enforced():
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(),
        exposure=ExposureSnapshot(open_risk_amount=260.0),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert result.status == RiskStatus.REJECTED
    assert "total portfolio risk" in result.reasons[0]


def test_daily_loss_limit_is_enforced():
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(),
        exposure=ExposureSnapshot(daily_realized_pnl=-260.0),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert result.status == RiskStatus.REJECTED
    assert "daily loss" in result.reasons[0]


def test_drawdown_limit_is_enforced():
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(8900, 10000),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert result.status == RiskStatus.REJECTED
    assert "drawdown" in result.reasons[0]


def test_consecutive_loss_limit_is_enforced():
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(),
        exposure=ExposureSnapshot(consecutive_losses=3),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert result.status == RiskStatus.REJECTED
    assert "consecutive-loss" in result.reasons[0]


def test_open_position_limit_is_enforced():
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(),
        exposure=ExposureSnapshot(open_positions=5),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert result.status == RiskStatus.REJECTED
    assert "open-position" in result.reasons[0]


def test_quantity_step_rounds_down_not_up():
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(),
        value_per_price_unit=100_000,
        quantity_step=0.1,
    )
    assert result.status == RiskStatus.APPROVED
    assert result.plan.quantity <= 0.005 * 10_000 / (0.002 * 100_000)
    assert any("rounded down" in warning for warning in result.warnings)


def test_max_position_units_caps_size():
    policy = RiskPolicy(max_position_units=0.1)
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(),
        policy=policy,
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert result.status == RiskStatus.APPROVED
    assert result.plan.quantity == pytest.approx(0.1)
    assert any("capped" in warning for warning in result.warnings)


def test_non_candidate_opportunity_is_rejected_as_input_error():
    with pytest.raises(RiskManagementError):
        assess_risk(
            opportunity(candidate=False),
            entry_price=1.1,
            stop_loss=1.098,
            take_profit=1.104,
            account=account(),
        )


def test_invalid_account_is_rejected():
    with pytest.raises(RiskManagementError):
        AccountSnapshot(equity=0)


def test_invalid_policy_is_rejected():
    with pytest.raises(RiskManagementError):
        RiskPolicy(default_risk_fraction=0.02, max_risk_fraction_per_trade=0.01)


def test_invalid_value_per_price_unit_is_rejected():
    with pytest.raises(RiskManagementError):
        assess_risk(
            opportunity(),
            entry_price=1.1,
            stop_loss=1.098,
            take_profit=1.104,
            account=account(),
            value_per_price_unit=0,
        )


def test_plan_serialization_is_auditable():
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    payload = result.to_dict()
    assert payload["analysis"] == "risk_management"
    assert payload["approved"] is True
    assert payload["plan"]["stop_loss"] == pytest.approx(1.098)
    assert "risk_amount" in payload["plan"]


def test_risk_engine_matches_function():
    engine = RiskEngine()
    direct = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    via_engine = engine.assess(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert via_engine == direct


def test_risk_approval_is_not_execution_authorization():
    result = assess_risk(
        opportunity(),
        entry_price=1.1,
        stop_loss=1.098,
        take_profit=1.104,
        account=account(),
        value_per_price_unit=100_000,
        quantity_step=0.01,
    )
    assert "execution authorization" in result.warnings[0]
