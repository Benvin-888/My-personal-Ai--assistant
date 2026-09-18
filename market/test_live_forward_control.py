from datetime import datetime, timezone

import pytest

from market.broker_state import BrokerContractState, ReconciliationStatus, PositionLifecycle
from market.deriv_demo import DerivContractSpec
from market.deriv_live_execution import DerivLiveExecutionConfig, DerivLiveExecutionResult, DerivLiveExecutionStatus
from market.deriv_live_reconciliation import DerivLiveReconciliationResult
from market.execution import ExecutionMode, ExecutionRequest
from market.execution_outcome import ExecutionOutcome, ExecutionOutcomeStatus
from market.live_forward_control import (
    ControlledForwardStatus,
    ControlledLiveForwardController,
    ControlledLiveForwardError,
    ControlledLiveForwardPolicy,
)
from market.risk import TradePlan


def _plan(now: str, *, rr: float = 2.0, risk: float = 0.005, pair: str = "EURUSD"):
    return TradePlan(
        pair=pair, interval="5m", timestamp_utc=now, direction="LONG",
        entry_price=1.1000, stop_loss=1.0990, take_profit=1.1020,
        stop_distance=0.001, target_distance=0.002, reward_risk=rr,
        quantity=1.0, risk_amount=5.0, risk_fraction=risk,
    )


def _request(now: str, *, candidate="cand-1", evidence="evidence-1", rr=2.0, risk=0.005):
    return ExecutionRequest(
        request_id="req-239-1", plan=_plan(now, rr=rr, risk=risk),
        created_at_utc=now, mode=ExecutionMode.LIVE,
        candidate_id=candidate, source_evidence_fingerprint=evidence,
    )


def _contract():
    return DerivContractSpec(
        underlying_symbol="EURUSD", contract_type="CALL", currency="USD",
        amount=5.0, basis="stake", duration=5, duration_unit="m",
    )


class FakeExecution:
    def __init__(self, outcome_status=ExecutionOutcomeStatus.CONFIRMED):
        self.calls = 0
        self.outcome_status = outcome_status

    def execute(self, request, contract, *, total_risk_fraction=None, explicit_live_confirmation=False):
        self.calls += 1
        outcome = ExecutionOutcome(
            request_id=request.request_id, mode=ExecutionMode.LIVE,
            status=self.outcome_status, broker="deriv", account_scope="REAL123",
            broker_order_id="12345" if self.outcome_status in {ExecutionOutcomeStatus.SUBMITTED, ExecutionOutcomeStatus.CONFIRMED} else None,
            execution_price=5.0 if self.outcome_status is ExecutionOutcomeStatus.CONFIRMED else None,
            executed_quantity=5.0 if self.outcome_status is ExecutionOutcomeStatus.CONFIRMED else None,
            message="ok" if self.outcome_status is ExecutionOutcomeStatus.CONFIRMED else "not confirmed",
        )
        gateway = type("G", (), {"to_dict": lambda self: {}})()
        return DerivLiveExecutionResult(
            DerivLiveExecutionStatus.CONFIRMED if self.outcome_status is ExecutionOutcomeStatus.CONFIRMED else DerivLiveExecutionStatus.UNKNOWN,
            request.request_id, gateway, outcome=outcome,
        )


class FakeReconciliation:
    def __init__(self, status=ReconciliationStatus.MATCHED):
        self.calls = 0
        self.status = status

    def reconcile(self, request, outcome, expected):
        self.calls += 1
        state = BrokerContractState(
            broker="deriv", account_mode="live", contract_id=outcome.broker_order_id,
            contract_type=expected.contract_type, symbol=expected.underlying_symbol,
            currency=expected.currency, buy_price=5.0, lifecycle=PositionLifecycle.OPEN,
        )
        return DerivLiveReconciliationResult(
            self.status, request.request_id, outcome.broker_order_id,
            broker_state=state, execution_outcome=outcome,
        )


def controller(now, execution=None, reconciliation=None, **policy_kwargs):
    config = DerivLiveExecutionConfig("REAL123", "token", "app", live_enabled=True)
    policy = ControlledLiveForwardPolicy(enabled=True, **policy_kwargs)
    return ControlledLiveForwardController(
        config, policy=policy,
        execution=execution or FakeExecution(),
        reconciliation=reconciliation or FakeReconciliation(),
        clock=lambda: datetime.fromisoformat(now.replace("Z", "+00:00")),
    )


def test_requires_explicit_confirmation():
    now = "2026-09-19T20:00:00+00:00"
    execution = FakeExecution()
    result = controller(now, execution=execution).evaluate(_request(now), _contract())
    assert result.status is ControlledForwardStatus.REJECTED
    assert execution.calls == 0


def test_requires_candidate_and_evidence():
    now = "2026-09-19T20:00:00+00:00"
    for kwargs in ({"candidate": None}, {"evidence": None}):
        result = controller(now).evaluate(_request(now, **kwargs), _contract(), explicit_live_confirmation=True)
        assert result.status is ControlledForwardStatus.REJECTED


def test_rejects_stale_plan():
    now = "2026-09-19T20:00:00+00:00"
    old = "2026-09-19T19:58:00+00:00"
    result = controller(now).evaluate(_request(old), _contract(), explicit_live_confirmation=True)
    assert result.status is ControlledForwardStatus.REJECTED
    assert "too old" in result.reasons[0]


def test_rejects_high_stake():
    now = "2026-09-19T20:00:00+00:00"
    contract = DerivContractSpec("EURUSD", "CALL", 20.0, "stake", "USD", 5, "m")
    result = controller(now).evaluate(_request(now), contract, explicit_live_confirmation=True)
    assert result.status is ControlledForwardStatus.REJECTED


def test_rejects_high_risk():
    now = "2026-09-19T20:00:00+00:00"
    result = controller(now).evaluate(_request(now, risk=0.02), _contract(), explicit_live_confirmation=True)
    assert result.status is ControlledForwardStatus.REJECTED


def test_rejects_low_reward_risk():
    now = "2026-09-19T20:00:00+00:00"
    result = controller(now).evaluate(_request(now, rr=0.5), _contract(), explicit_live_confirmation=True)
    assert result.status is ControlledForwardStatus.REJECTED


def test_requires_matching_symbol():
    now = "2026-09-19T20:00:00+00:00"
    contract = DerivContractSpec("GBPUSD", "CALL", 5.0, "stake", "USD", 5, "m")
    result = controller(now).evaluate(_request(now), contract, explicit_live_confirmation=True)
    assert result.status is ControlledForwardStatus.REJECTED


def test_success_requires_execution_and_reconciliation():
    now = "2026-09-19T20:00:00+00:00"
    execution, reconciliation = FakeExecution(), FakeReconciliation()
    result = controller(now, execution=execution, reconciliation=reconciliation).evaluate(
        _request(now), _contract(), explicit_live_confirmation=True
    )
    assert result.status is ControlledForwardStatus.EXECUTED_AND_RECONCILED
    assert result.successful
    assert execution.calls == 1
    assert reconciliation.calls == 1


def test_mismatch_is_not_success():
    now = "2026-09-19T20:00:00+00:00"
    result = controller(now, reconciliation=FakeReconciliation(ReconciliationStatus.MISMATCH)).evaluate(
        _request(now), _contract(), explicit_live_confirmation=True
    )
    assert result.status is ControlledForwardStatus.EXECUTED_UNVERIFIED
    assert not result.successful


def test_unknown_reconciliation_is_not_success():
    now = "2026-09-19T20:00:00+00:00"
    result = controller(now, reconciliation=FakeReconciliation(ReconciliationStatus.UNKNOWN)).evaluate(
        _request(now), _contract(), explicit_live_confirmation=True
    )
    assert result.status is ControlledForwardStatus.UNKNOWN
    assert not result.successful


def test_non_confirmed_execution_is_not_success():
    now = "2026-09-19T20:00:00+00:00"
    result = controller(now, execution=FakeExecution(ExecutionOutcomeStatus.UNKNOWN)).evaluate(
        _request(now), _contract(), explicit_live_confirmation=True
    )
    assert result.status is ControlledForwardStatus.UNKNOWN
    assert not result.successful


def test_one_shot_limit_blocks_second_execution():
    now = "2026-09-19T20:00:00+00:00"
    execution = FakeExecution()
    ctrl = controller(now, execution=execution)
    first = ctrl.evaluate(_request(now), _contract(), explicit_live_confirmation=True)
    second = ctrl.evaluate(_request(now), _contract(), explicit_live_confirmation=True)
    assert first.successful
    assert second.status is ControlledForwardStatus.REJECTED
    assert execution.calls == 1


def test_disabled_policy_never_calls_execution():
    now = "2026-09-19T20:00:00+00:00"
    execution = FakeExecution()
    config = DerivLiveExecutionConfig("REAL123", "token", "app", live_enabled=True)
    ctrl = ControlledLiveForwardController(
        config, policy=ControlledLiveForwardPolicy(enabled=False), execution=execution,
        reconciliation=FakeReconciliation(), clock=lambda: datetime.fromisoformat(now.replace("Z", "+00:00")),
    )
    result = ctrl.evaluate(_request(now), _contract(), explicit_live_confirmation=True)
    assert result.status is ControlledForwardStatus.REJECTED
    assert execution.calls == 0


def test_future_timestamp_is_rejected():
    now = "2026-09-19T20:00:00+00:00"
    future = "2026-09-19T20:00:10+00:00"
    result = controller(now).evaluate(_request(future), _contract(), explicit_live_confirmation=True)
    assert result.status is ControlledForwardStatus.REJECTED


def test_safe_summary_exposes_no_credentials():
    summary = ControlledLiveForwardPolicy().safe_summary()
    assert summary["credentials_exposed"] is False
    assert "authorization_token" not in summary


def test_result_serialization_marks_only_reconciled_success():
    now = "2026-09-19T20:00:00+00:00"
    result = controller(now).evaluate(_request(now), _contract(), explicit_live_confirmation=True)
    payload = result.to_dict()
    assert payload["success"] is True
    assert payload["live_trade_verified"] is True
    assert payload["credentials_exposed"] is False
