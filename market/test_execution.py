from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market.execution import (
    ExecutionAdapterCapability,
    ExecutionGateway,
    ExecutionMode,
    ExecutionPolicy,
    ExecutionStatus,
)
from market.opportunity import OpportunityStatus, TradeOpportunity
from market.risk import AccountSnapshot, RiskDecision, RiskPolicy, RiskStatus, assess_risk
from market.strategy.models import SignalDirection


def candidate() -> TradeOpportunity:
    return TradeOpportunity(
        pair="EURUSD", interval="5m", timestamp_utc="2026-09-14T20:00:00+00:00",
        status=OpportunityStatus.CANDIDATE, direction=SignalDirection.LONG,
        ensemble_score=0.8, agreement=0.8, conflict=0.1, confidence=0.8,
        regime="TREND", session_phase="LONDON", active_sessions=("London",),
        operational_state="READY", analysis_usable=True,
    )


def approved() -> RiskDecision:
    return assess_risk(candidate(), entry_price=1.1000, stop_loss=1.0950, take_profit=1.1100,
                       account=AccountSnapshot(equity=10000), policy=RiskPolicy(),
                       risk_fraction=0.005, value_per_price_unit=1.0, quantity_step=1.0)


def request(gateway: ExecutionGateway):
    return gateway.create_request(approved(), request_id="REQ-1",
                                  created_at_utc="2026-09-14T20:00:01+00:00")


def enabled_gateway() -> ExecutionGateway:
    return ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.PAPER))


def test_default_gateway_is_disabled():
    g = ExecutionGateway()
    assert g.policy.mode is ExecutionMode.DISABLED


def test_create_request_requires_risk_approval():
    g = ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.PAPER))
    rejected = RiskDecision(RiskStatus.REJECTED, "EURUSD", "5m", None, "LONG")
    with pytest.raises(ValueError):
        g.create_request(rejected, request_id="REQ", created_at_utc="2026-09-14T20:00:00+00:00")


def test_create_request_requires_plan():
    g = ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.PAPER))
    no_plan = RiskDecision(RiskStatus.APPROVED, "EURUSD", "5m", None, "LONG")
    with pytest.raises(ValueError):
        g.create_request(no_plan, request_id="REQ", created_at_utc="2026-09-14T20:00:00+00:00")


def test_request_is_fingerprinted_deterministically():
    a = request(enabled_gateway())
    b = ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.PAPER)).create_request(
        approved(), request_id="REQ-1", created_at_utc="2026-09-14T20:00:01+00:00")
    assert a.fingerprint == b.fingerprint


def test_disabled_gateway_rejects():
    g = ExecutionGateway()
    r = g.create_request(approved(), request_id="REQ-1", created_at_utc="2026-09-14T20:00:01+00:00")
    result = g.validate(r, adapter_capability=ExecutionAdapterCapability.VALIDATION_ONLY)
    assert result.status is ExecutionStatus.REJECTED
    assert "disabled" in " ".join(result.reasons)
    assert result.execution_authorized is False


def test_paper_gateway_requires_explicit_adapter():
    g = enabled_gateway()
    result = g.validate(request(g))
    assert result.status is ExecutionStatus.REJECTED
    assert "adapter capability" in " ".join(result.reasons)


def test_paper_gateway_can_be_ready_for_adapter():
    g = enabled_gateway()
    result = g.validate(request(g), adapter_capability=ExecutionAdapterCapability.PAPER)
    assert result.status is ExecutionStatus.READY_FOR_ADAPTER
    assert result.ready_for_adapter is True
    assert result.execution_authorized is False
    assert result.broker_access is False
    assert result.order_placed is False


def test_duplicate_request_is_rejected():
    g = enabled_gateway()
    r = request(g)
    first = g.validate(r, adapter_capability=ExecutionAdapterCapability.PAPER)
    second = g.validate(r, adapter_capability=ExecutionAdapterCapability.PAPER)
    assert first.status is ExecutionStatus.READY_FOR_ADAPTER
    assert second.status is ExecutionStatus.DUPLICATE


def test_excessive_trade_risk_is_rejected():
    g = enabled_gateway()
    r = request(g)
    bad_plan = r.plan.__class__(**{**r.plan.__dict__, "risk_fraction": 0.02})
    bad = r.__class__(**{**r.__dict__, "plan": bad_plan})
    result = g.validate(bad, adapter_capability=ExecutionAdapterCapability.PAPER)
    assert result.status is ExecutionStatus.REJECTED


def test_excessive_total_risk_is_rejected():
    g = enabled_gateway()
    result = g.validate(request(g), total_risk_fraction=0.03,
                        adapter_capability=ExecutionAdapterCapability.PAPER)
    assert result.status is ExecutionStatus.REJECTED
    assert "total risk" in " ".join(result.reasons)


def test_invalid_long_geometry_is_rejected():
    g = enabled_gateway()
    r = request(g)
    bad_plan = r.plan.__class__(**{**r.plan.__dict__, "stop_loss": 1.105})
    bad = r.__class__(**{**r.__dict__, "plan": bad_plan})
    result = g.validate(bad, adapter_capability=ExecutionAdapterCapability.PAPER)
    assert result.status is ExecutionStatus.REJECTED


def test_timezone_is_required_for_request_timestamp():
    g = ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.PAPER))
    with pytest.raises(ValueError):
        g.create_request(approved(), request_id="REQ", created_at_utc="2026-09-14T20:00:00")


def test_wrong_mode_is_rejected():
    g = enabled_gateway()
    r = request(g)
    bad = r.__class__(**{**r.__dict__, "mode": ExecutionMode.DEMO})
    result = g.validate(bad, adapter_capability=ExecutionAdapterCapability.PAPER)
    assert result.status is ExecutionStatus.REJECTED


def test_live_never_implies_authorization():
    g = ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.LIVE))
    r = request(g)
    result = g.validate(r, adapter_capability=ExecutionAdapterCapability.LIVE)
    assert result.status is ExecutionStatus.READY_FOR_ADAPTER
    assert result.execution_authorized is False
    assert result.to_dict()["order_placed"] is False


def test_functional_wrapper():
    g = enabled_gateway()
    r = request(g)
    result = g.validate(r, adapter_capability=ExecutionAdapterCapability.PAPER)
    assert result.request_fingerprint == r.fingerprint


def test_policy_rejects_invalid_fraction():
    with pytest.raises(ValueError):
        ExecutionPolicy(maximum_risk_fraction=1.1)
