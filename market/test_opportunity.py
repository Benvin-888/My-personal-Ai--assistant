from __future__ import annotations

import copy

import pytest

from market.opportunity import (
    OpportunityPolicy,
    OpportunityStatus,
    TradeOpportunity,
    TradeOpportunityEngine,
    TradeOpportunityError,
    assess_trade_opportunity,
)
from market.strategy.models import SignalDirection


PAIR = "EURUSD"
INTERVAL = "5m"
TIMESTAMP = "2026-09-11T10:00:00+00:00"


def ensemble(**overrides):
    payload = {
        "success": True,
        "market": "forex",
        "analysis": "strategy_ensemble",
        "status": "EVALUATED",
        "pair": PAIR,
        "interval": INTERVAL,
        "timestamp_utc": TIMESTAMP,
        "decision": "LONG",
        "ensemble_score": 0.72,
        "agreement": 0.90,
        "conflict": 0.10,
        "confidence": 0.80,
        "contributions": [
            {"strategy_id": "trend_momentum", "score": 0.8, "direction": "LONG"},
            {"strategy_id": "mean_reversion", "score": 0.64, "direction": "LONG"},
        ],
    }
    payload.update(overrides)
    return payload


def regime(**overrides):
    payload = {
        "success": True,
        "analysis": "market_regime",
        "status": "EVALUATED",
        "pair": PAIR,
        "interval": INTERVAL,
        "timestamp_utc": TIMESTAMP,
        "regime": "BULLISH_TREND",
        "analysis_usable": True,
    }
    payload.update(overrides)
    return payload


def session(**overrides):
    payload = {
        "success": True,
        "analysis": "forex_session",
        "status": "EVALUATED",
        "pair": PAIR,
        "interval": INTERVAL,
        "timestamp_utc": TIMESTAMP,
        "phase": "SINGLE_SESSION",
        "active_sessions": ["LONDON"],
    }
    payload.update(overrides)
    return payload


def operational(**overrides):
    payload = {
        "success": True,
        "analysis": "market_operational_state",
        "status": "HEALTHY",
        "pair": PAIR,
        "interval": INTERVAL,
        "timestamp_utc": TIMESTAMP,
        "analysis_usable": True,
    }
    payload.update(overrides)
    return payload


def evaluate(**kwargs):
    params = {
        "regime": regime(),
        "session": session(),
        "operational_state": operational(),
    }
    params.update(kwargs)
    return assess_trade_opportunity(ensemble(), **params)


def test_candidate_requires_all_core_contexts():
    result = evaluate()
    assert result.status == OpportunityStatus.CANDIDATE
    assert result.direction == SignalDirection.LONG
    assert result.analysis_usable is True
    assert result.is_candidate is True


def test_candidate_to_dict_shape():
    result = evaluate().to_dict()
    assert result["success"] is True
    assert result["analysis"] == "trade_opportunity"
    assert result["status"] == "CANDIDATE"
    assert result["direction"] == "LONG"
    assert result["context"]["regime"] == "BULLISH_TREND"
    assert result["context"]["session_phase"] == "SINGLE_SESSION"
    assert result["context"]["active_sessions"] == ["LONDON"]


def test_neutral_ensemble_is_rejected():
    result = assess_trade_opportunity(
        ensemble(decision="NEUTRAL", ensemble_score=0.0),
        regime=regime(), session=session(), operational_state=operational()
    )
    assert result.status == OpportunityStatus.REJECTED
    assert "ensemble decision is NEUTRAL" in result.reasons


def test_unsuccessful_ensemble_is_rejected():
    result = assess_trade_opportunity(
        ensemble(success=False, status="INVALID_INPUT"),
        regime=regime(), session=session(), operational_state=operational()
    )
    assert result.status == OpportunityStatus.REJECTED
    assert "strategy ensemble is not successful" in result.reasons


def test_score_policy_can_reject():
    result = evaluate(policy=OpportunityPolicy(minimum_ensemble_score=0.80))
    assert result.status == OpportunityStatus.REJECTED
    assert "ensemble score is below opportunity policy threshold" in result.reasons


def test_agreement_policy_can_reject():
    result = evaluate(policy=OpportunityPolicy(minimum_agreement=0.95))
    assert result.status == OpportunityStatus.REJECTED
    assert "ensemble agreement is below opportunity policy threshold" in result.reasons


def test_missing_regime_is_rejected_by_default():
    result = assess_trade_opportunity(
        ensemble(), session=session(), operational_state=operational()
    )
    assert result.status == OpportunityStatus.REJECTED
    assert "market regime context is required" in result.reasons


def test_unusable_regime_is_rejected():
    result = evaluate(regime={**regime(), "analysis_usable": False})
    assert result.status == OpportunityStatus.REJECTED
    assert "market regime context is not usable" in result.reasons


def test_missing_session_is_rejected_by_default():
    result = assess_trade_opportunity(
        ensemble(), regime=regime(), operational_state=operational()
    )
    assert result.status == OpportunityStatus.REJECTED
    assert "forex session context is required" in result.reasons


def test_off_session_is_valid_context_not_automatic_rejection():
    result = evaluate(session=session(phase="OFF_SESSION", active_sessions=[]))
    assert result.status == OpportunityStatus.CANDIDATE
    assert result.session_phase == "OFF_SESSION"
    assert result.active_sessions == ()
    assert result.metadata["session_is_context_only"] is True


def test_session_overlap_is_preserved_as_context():
    result = evaluate(session=session(phase="OVERLAP", active_sessions=["LONDON", "NEW_YORK"]))
    assert result.status == OpportunityStatus.CANDIDATE
    assert result.session_phase == "OVERLAP"
    assert result.active_sessions == ("LONDON", "NEW_YORK")


def test_missing_operational_state_is_rejected_by_default():
    result = assess_trade_opportunity(ensemble(), regime=regime(), session=session())
    assert result.status == OpportunityStatus.REJECTED
    assert "market operational state is required" in result.reasons


def test_unusable_operational_state_is_rejected():
    result = evaluate(operational_state=operational(status="UNUSABLE", analysis_usable=False))
    assert result.status == OpportunityStatus.REJECTED
    assert "market operational state does not permit analysis" in result.reasons


def test_degraded_operational_state_can_be_allowed():
    result = evaluate(
        operational_state=operational(status="DEGRADED", analysis_usable=False),
        policy=OpportunityPolicy(allow_degraded_operational_state=True),
    )
    assert result.status == OpportunityStatus.CANDIDATE
    assert any("DEGRADED" in warning for warning in result.warnings)


def test_regime_pair_mismatch_is_rejected():
    result = evaluate(regime=regime(pair="GBPUSD"))
    assert result.status == OpportunityStatus.REJECTED
    assert "regime pair does not match ensemble pair" in result.reasons


def test_regime_interval_mismatch_is_rejected():
    result = evaluate(regime=regime(interval="15m"))
    assert result.status == OpportunityStatus.REJECTED
    assert "regime interval does not match ensemble interval" in result.reasons


def test_regime_timestamp_mismatch_is_rejected():
    result = evaluate(regime=regime(timestamp_utc="2026-09-11T10:05:00+00:00"))
    assert result.status == OpportunityStatus.REJECTED
    assert "regime timestamp does not match ensemble timestamp" in result.reasons


def test_session_timestamp_mismatch_is_rejected():
    result = evaluate(session=session(timestamp_utc="2026-09-11T10:05:00+00:00"))
    assert result.status == OpportunityStatus.REJECTED
    assert "session timestamp does not match ensemble timestamp" in result.reasons


def test_operational_timestamp_mismatch_is_rejected():
    result = evaluate(
        operational_state=operational(timestamp_utc="2026-09-11T10:05:00+00:00")
    )
    assert result.status == OpportunityStatus.REJECTED
    assert "operational state timestamp does not match ensemble timestamp" in result.reasons


def test_short_direction_is_preserved():
    result = assess_trade_opportunity(
        ensemble(decision="SHORT", ensemble_score=-0.75),
        regime=regime(regime="BEARISH_TREND"),
        session=session(),
        operational_state=operational(),
    )
    assert result.status == OpportunityStatus.CANDIDATE
    assert result.direction == SignalDirection.SHORT
    assert result.ensemble_score == pytest.approx(-0.75)


def test_contributions_are_snapshotted():
    payload = ensemble()
    result = assess_trade_opportunity(
        payload, regime=regime(), session=session(), operational_state=operational()
    )
    payload["contributions"][0]["score"] = 0.01
    assert result.strategy_contributions[0]["score"] == 0.8


def test_source_contributions_survive_serialization():
    result = evaluate()
    serialized = result.to_dict()
    assert len(serialized["ensemble"]["contributions"]) == 2
    assert serialized["ensemble"]["contributions"][0]["strategy_id"] == "trend_momentum"


def test_engine_matches_function():
    engine = TradeOpportunityEngine()
    direct = evaluate()
    via_engine = engine.assess(
        ensemble(), regime=regime(), session=session(), operational_state=operational()
    )
    assert via_engine == direct


def test_policy_is_serializable():
    policy = OpportunityPolicy(minimum_ensemble_score=0.55, minimum_agreement=0.75)
    assert policy.to_dict()["minimum_ensemble_score"] == 0.55
    assert policy.to_dict()["minimum_agreement"] == 0.75


def test_policy_rejects_invalid_score_threshold():
    with pytest.raises(TradeOpportunityError):
        OpportunityPolicy(minimum_ensemble_score=1.1)


def test_policy_rejects_invalid_agreement_threshold():
    with pytest.raises(TradeOpportunityError):
        OpportunityPolicy(minimum_agreement=-0.1)


def test_non_mapping_ensemble_is_rejected_as_input_error():
    with pytest.raises(TradeOpportunityError):
        assess_trade_opportunity([], regime=regime(), session=session(), operational_state=operational())


def test_missing_ensemble_identity_is_rejected():
    payload = ensemble()
    payload.pop("pair")
    with pytest.raises(TradeOpportunityError):
        assess_trade_opportunity(payload, regime=regime(), session=session(), operational_state=operational())


def test_invalid_numeric_ensemble_score_is_rejected():
    with pytest.raises(TradeOpportunityError):
        assess_trade_opportunity(
            ensemble(ensemble_score="bad"), regime=regime(), session=session(), operational_state=operational()
        )


def test_invalid_session_active_sessions_is_rejected():
    result = evaluate(session=session(active_sessions="LONDON"))
    assert result.status == OpportunityStatus.REJECTED
    assert "forex session active_sessions is invalid" in result.reasons


def test_missing_optional_source_timestamp_is_allowed_for_context():
    result = evaluate(
        regime=regime(timestamp_utc=None),
        session=session(timestamp_utc=None),
        operational_state=operational(timestamp_utc=None),
    )
    assert result.status == OpportunityStatus.CANDIDATE


def test_ensemble_timestamp_can_be_none():
    result = assess_trade_opportunity(
        ensemble(timestamp_utc=None), regime=regime(), session=session(), operational_state=operational()
    )
    assert result.status == OpportunityStatus.CANDIDATE
    assert result.timestamp_utc is None


def test_metadata_marks_point_in_time_contract():
    result = evaluate()
    assert result.metadata["point_in_time"] is True
    assert result.metadata["contract_version"] == "2.6.12"


def test_result_is_immutable_at_top_level():
    result = evaluate()
    with pytest.raises(Exception):
        result.status = OpportunityStatus.REJECTED


def test_context_can_preserve_additional_audit_fields():
    result = evaluate()
    result2 = TradeOpportunity(
        **{**result.__dict__, "context": {"source": "test"}}
    )
    serialized = result2.to_dict()
    assert serialized["context"]["source"] == "test"


def test_deep_copy_input_does_not_change_result():
    payload = copy.deepcopy(ensemble())
    result = assess_trade_opportunity(
        payload, regime=regime(), session=session(), operational_state=operational()
    )
    payload["contributions"].append({"strategy_id": "new"})
    assert len(result.strategy_contributions) == 2
