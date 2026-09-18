from __future__ import annotations

import pytest

from .execution import ExecutionMode, ExecutionRequest
from .execution_outcome import (
    ExecutionOutcome,
    ExecutionOutcomeError,
    ExecutionOutcomeStatus,
    validate_execution_outcome,
)
from .risk import TradePlan


def _request() -> ExecutionRequest:
    plan = TradePlan(
        pair="EURUSD",
        interval="5m",
        direction="LONG",
        entry_price=1.1000,
        stop_loss=1.0990,
        take_profit=1.1020,
        stop_distance=0.0010,
        target_distance=0.0020,
        reward_risk=2.0,
        quantity=1000.0,
        risk_amount=1.0,
        risk_fraction=0.005,
        timestamp_utc="2026-09-18T20:00:00+00:00",
    )
    return ExecutionRequest(
        request_id="req-1",
        plan=plan,
        created_at_utc="2026-09-18T20:00:01+00:00",
        mode=ExecutionMode.LIVE,
    )


def _outcome(status=ExecutionOutcomeStatus.CONFIRMED, **kwargs):
    defaults = dict(
        request_id="req-1",
        mode=ExecutionMode.LIVE,
        status=status,
        broker="deriv",
        account_scope="real",
        broker_order_id="order-1" if status in {ExecutionOutcomeStatus.SUBMITTED, ExecutionOutcomeStatus.CONFIRMED} else None,
        execution_price=1.1001 if status is ExecutionOutcomeStatus.CONFIRMED else None,
        executed_quantity=1000.0 if status is ExecutionOutcomeStatus.CONFIRMED else None,
    )
    defaults.update(kwargs)
    return ExecutionOutcome(**defaults)


def test_only_confirmed_is_successful():
    assert _outcome().successful is True
    assert _outcome(ExecutionOutcomeStatus.SUBMITTED).successful is False
    assert _outcome(ExecutionOutcomeStatus.REJECTED).successful is False
    assert _outcome(ExecutionOutcomeStatus.FAILED).successful is False
    assert _outcome(ExecutionOutcomeStatus.UNKNOWN).successful is False


def test_unknown_is_explicitly_uncertain():
    outcome = _outcome(ExecutionOutcomeStatus.UNKNOWN)
    assert outcome.uncertain is True
    assert outcome.terminal is False


def test_submitted_requires_broker_order_id():
    with pytest.raises(ExecutionOutcomeError):
        _outcome(ExecutionOutcomeStatus.SUBMITTED, broker_order_id=None)


def test_confirmed_requires_fill_details():
    with pytest.raises(ExecutionOutcomeError):
        _outcome(ExecutionOutcomeStatus.CONFIRMED, execution_price=None)
    with pytest.raises(ExecutionOutcomeError):
        _outcome(ExecutionOutcomeStatus.CONFIRMED, executed_quantity=None)


def test_confirmed_requires_positive_fill_details():
    with pytest.raises(ExecutionOutcomeError):
        _outcome(ExecutionOutcomeStatus.CONFIRMED, execution_price=0)
    with pytest.raises(ExecutionOutcomeError):
        _outcome(ExecutionOutcomeStatus.CONFIRMED, executed_quantity=0)


def test_nonfinite_numbers_are_rejected():
    with pytest.raises(ExecutionOutcomeError):
        _outcome(ExecutionOutcomeStatus.CONFIRMED, execution_price=float("nan"))
    with pytest.raises(ExecutionOutcomeError):
        _outcome(ExecutionOutcomeStatus.CONFIRMED, executed_quantity=float("inf"))


def test_request_identity_and_mode_are_bound():
    request = _request()
    outcome = _outcome()
    assert validate_execution_outcome(request, outcome) is outcome

    with pytest.raises(ExecutionOutcomeError):
        validate_execution_outcome(request, _outcome(request_id="req-2"))

    with pytest.raises(ExecutionOutcomeError):
        validate_execution_outcome(request, _outcome(mode=ExecutionMode.DEMO))


def test_mapping_parser_is_strict_about_status_and_mode():
    payload = _outcome().to_dict()
    parsed = ExecutionOutcome.from_mapping(payload)
    assert parsed.successful is True
    assert parsed.broker_order_id == "order-1"

    with pytest.raises(ExecutionOutcomeError):
        ExecutionOutcome.from_mapping({"request_id": "req-1"})


def test_success_field_cannot_upgrade_submitted_state():
    payload = _outcome(ExecutionOutcomeStatus.SUBMITTED).to_dict()
    payload["success"] = True
    parsed = ExecutionOutcome.from_mapping(payload)
    assert parsed.status is ExecutionOutcomeStatus.SUBMITTED
    assert parsed.successful is False


def test_unknown_state_cannot_be_success():
    payload = _outcome(ExecutionOutcomeStatus.UNKNOWN).to_dict()
    payload["success"] = True
    parsed = ExecutionOutcome.from_mapping(payload)
    assert parsed.successful is False


def test_rejected_and_failed_are_terminal():
    assert _outcome(ExecutionOutcomeStatus.REJECTED).terminal is True
    assert _outcome(ExecutionOutcomeStatus.FAILED).terminal is True


def test_to_dict_never_reports_success_for_nonconfirmed():
    for status in ExecutionOutcomeStatus:
        if status is ExecutionOutcomeStatus.CONFIRMED:
            continue
        kwargs = {}
        if status is ExecutionOutcomeStatus.SUBMITTED:
            kwargs["broker_order_id"] = "order-1"
        outcome = _outcome(status, **kwargs)
        assert outcome.to_dict()["success"] is False
        assert outcome.to_dict()["successful"] is False


def test_metadata_must_be_dict():
    with pytest.raises(ExecutionOutcomeError):
        _outcome(metadata=["secret"])
