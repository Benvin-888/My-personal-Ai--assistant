"""APEX / BENVIN Trade Opportunity Contract.

Phase 2.6.12

This module converts already-produced strategy, regime, session, and market
operational observations into one immutable, auditable candidate-opportunity
contract.

It does NOT:
    - calculate stop-loss or take-profit levels
    - calculate position size or monetary risk
    - place, modify, or cancel orders
    - authorize execution
    - assume a trading session is profitable

The contract is deliberately provider-neutral and point-in-time friendly.
All observations must be supplied by callers; this module performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Any, Mapping

from .strategy.models import SignalDirection


class TradeOpportunityError(ValueError):
    """Raised when opportunity input or configuration is invalid."""


class OpportunityStatus(str, Enum):
    """Lifecycle status of an opportunity assessment."""

    CANDIDATE = "CANDIDATE"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class OpportunityPolicy:
    """Deterministic admission policy for candidate opportunities."""

    require_successful_ensemble: bool = True
    require_usable_regime: bool = True
    require_session_context: bool = True
    require_operational_state: bool = True
    allow_degraded_operational_state: bool = False
    require_non_neutral_decision: bool = True
    minimum_ensemble_score: float = 0.0
    minimum_agreement: float = 0.0

    def __post_init__(self) -> None:
        for name in ("minimum_ensemble_score", "minimum_agreement"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(float(value))
            ):
                raise TradeOpportunityError(f"{name} must be finite numeric")

        if not 0.0 <= float(self.minimum_ensemble_score) <= 1.0:
            raise TradeOpportunityError("minimum_ensemble_score must be between 0 and 1")
        if not 0.0 <= float(self.minimum_agreement) <= 1.0:
            raise TradeOpportunityError("minimum_agreement must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "require_successful_ensemble": self.require_successful_ensemble,
            "require_usable_regime": self.require_usable_regime,
            "require_session_context": self.require_session_context,
            "require_operational_state": self.require_operational_state,
            "allow_degraded_operational_state": self.allow_degraded_operational_state,
            "require_non_neutral_decision": self.require_non_neutral_decision,
            "minimum_ensemble_score": float(self.minimum_ensemble_score),
            "minimum_agreement": float(self.minimum_agreement),
        }


def _mapping(value: Any, name: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TradeOpportunityError(f"{name} must be a mapping when supplied")
    return value


def _non_empty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TradeOpportunityError(f"{name} must be a non-empty string")
    return value.strip()


def _number(value: Any, name: str, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise TradeOpportunityError(f"{name} must be finite numeric")
    result = float(value)
    if minimum is not None and result < minimum:
        raise TradeOpportunityError(f"{name} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise TradeOpportunityError(f"{name} must be at most {maximum}")
    return result


def _timestamp(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TradeOpportunityError(f"{name} must be a non-empty string or None")
    return value.strip()


@dataclass(frozen=True)
class TradeOpportunity:
    """Immutable point-in-time candidate opportunity contract."""

    pair: str
    interval: str
    timestamp_utc: str | None
    status: OpportunityStatus
    direction: SignalDirection
    ensemble_score: float
    agreement: float
    conflict: float
    confidence: float
    regime: str
    session_phase: str
    active_sessions: tuple[str, ...]
    operational_state: str | None
    analysis_usable: bool
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    strategy_contributions: tuple[dict[str, Any], ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, OpportunityStatus):
            raise ValueError("status must be an OpportunityStatus")
        if not isinstance(self.direction, SignalDirection):
            raise ValueError("direction must be a SignalDirection")
        _non_empty(self.pair, "pair")
        _non_empty(self.interval, "interval")
        _number(self.ensemble_score, "ensemble_score", -1.0, 1.0)
        _number(self.agreement, "agreement", 0.0, 1.0)
        _number(self.conflict, "conflict", 0.0, 1.0)
        _number(self.confidence, "confidence", 0.0, 1.0)
        if not isinstance(self.regime, str) or not self.regime.strip():
            raise ValueError("regime must be a non-empty string")
        if not isinstance(self.session_phase, str) or not self.session_phase.strip():
            raise ValueError("session_phase must be a non-empty string")
        if not isinstance(self.analysis_usable, bool):
            raise ValueError("analysis_usable must be boolean")
        if self.operational_state is not None and not isinstance(self.operational_state, str):
            raise ValueError("operational_state must be a string or None")

    @property
    def is_candidate(self) -> bool:
        return self.status == OpportunityStatus.CANDIDATE

    def to_dict(self) -> dict[str, Any]:
        result = {
            "success": self.status == OpportunityStatus.CANDIDATE,
            "market": "forex",
            "analysis": "trade_opportunity",
            "status": self.status.value,
            "pair": self.pair,
            "interval": self.interval,
            "timeframe": self.interval,
            "timestamp_utc": self.timestamp_utc,
            "direction": self.direction.value,
            "opportunity": self.is_candidate,
            "ensemble": {
                "score": round(float(self.ensemble_score), 6),
                "agreement": round(float(self.agreement), 6),
                "conflict": round(float(self.conflict), 6),
                "confidence": round(float(self.confidence), 6),
                "contributions": [dict(item) for item in self.strategy_contributions],
            },
            "context": {
                "regime": self.regime,
                "session_phase": self.session_phase,
                "active_sessions": list(self.active_sessions),
                "operational_state": self.operational_state,
            },
            "analysis_usable": self.analysis_usable,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "evidence": list(self.evidence),
            "metadata": dict(self.metadata),
        }
        if self.context:
            result["context"].update(dict(self.context))
        if self.error is not None:
            result["error"] = self.error
        return result


def _identity(ensemble: Mapping[str, Any]) -> tuple[str, str, str | None]:
    pair = _non_empty(ensemble.get("pair"), "ensemble pair")
    interval = _non_empty(ensemble.get("interval", ensemble.get("timeframe")), "ensemble interval")
    timestamp = _timestamp(ensemble.get("timestamp_utc"), "ensemble timestamp_utc")
    return pair.upper(), interval, timestamp


def _check_identity(
    payload: Mapping[str, Any],
    *,
    pair: str,
    interval: str,
    timestamp: str | None,
    name: str,
) -> str | None:
    payload_pair = payload.get("pair")
    if payload_pair is not None and str(payload_pair).strip().upper() != pair:
        return f"{name} pair does not match ensemble pair"
    payload_interval = payload.get("interval", payload.get("timeframe"))
    if payload_interval is not None and str(payload_interval).strip() != interval:
        return f"{name} interval does not match ensemble interval"
    payload_timestamp = payload.get("timestamp_utc")
    if payload_timestamp is not None and timestamp is not None and str(payload_timestamp).strip() != timestamp:
        return f"{name} timestamp does not match ensemble timestamp"
    return None


def _rejected(
    *,
    pair: str,
    interval: str,
    timestamp: str | None,
    direction: SignalDirection,
    score: float,
    agreement: float,
    conflict: float,
    confidence: float,
    regime: str = "UNKNOWN",
    session_phase: str = "UNKNOWN",
    active_sessions: tuple[str, ...] = (),
    operational_state: str | None = None,
    reasons: list[str],
    warnings: list[str] | None = None,
    evidence: list[str] | None = None,
    contributions: tuple[dict[str, Any], ...] = (),
    metadata: dict[str, Any] | None = None,
    status: OpportunityStatus = OpportunityStatus.REJECTED,
    error: str | None = None,
) -> TradeOpportunity:
    return TradeOpportunity(
        pair=pair,
        interval=interval,
        timestamp_utc=timestamp,
        status=status,
        direction=direction,
        ensemble_score=score,
        agreement=agreement,
        conflict=conflict,
        confidence=confidence,
        regime=regime,
        session_phase=session_phase,
        active_sessions=active_sessions,
        operational_state=operational_state,
        analysis_usable=False,
        reasons=tuple(reasons),
        warnings=tuple(warnings or ()),
        evidence=tuple(evidence or ()),
        strategy_contributions=contributions,
        metadata=metadata or {},
        error=error,
    )


def assess_trade_opportunity(
    ensemble: Mapping[str, Any],
    *,
    regime: Mapping[str, Any] | None = None,
    session: Mapping[str, Any] | None = None,
    operational_state: Mapping[str, Any] | None = None,
    policy: OpportunityPolicy | None = None,
) -> TradeOpportunity:
    """Assess a candidate opportunity from existing deterministic evidence."""
    policy = policy or OpportunityPolicy()
    ensemble = _mapping(ensemble, "ensemble")
    if ensemble is None:
        raise TradeOpportunityError("ensemble is required")
    regime = _mapping(regime, "regime")
    session = _mapping(session, "session")
    operational_state = _mapping(operational_state, "operational_state")

    try:
        pair, interval, timestamp = _identity(ensemble)
        try:
            direction = SignalDirection(ensemble.get("decision", SignalDirection.NEUTRAL.value))
        except (TypeError, ValueError):
            return _rejected(
                pair=pair,
                interval=interval,
                timestamp=timestamp,
                direction=SignalDirection.NEUTRAL,
                score=0.0,
                agreement=0.0,
                conflict=0.0,
                confidence=0.0,
                reasons=["ensemble decision is invalid"],
                status=OpportunityStatus.INVALID_INPUT,
            )

        score = _number(ensemble.get("ensemble_score", 0.0), "ensemble_score", -1.0, 1.0)
        agreement = _number(ensemble.get("agreement", 0.0), "agreement", 0.0, 1.0)
        conflict = _number(ensemble.get("conflict", 0.0), "conflict", 0.0, 1.0)
        confidence = _number(ensemble.get("confidence", 0.0), "confidence", 0.0, 1.0)

        reasons: list[str] = []
        warnings: list[str] = []
        evidence: list[str] = []

        if policy.require_successful_ensemble and ensemble.get("success") is not True:
            reasons.append("strategy ensemble is not successful")

        if policy.require_non_neutral_decision and direction == SignalDirection.NEUTRAL:
            reasons.append("ensemble decision is NEUTRAL")

        if abs(score) < float(policy.minimum_ensemble_score):
            reasons.append("ensemble score is below opportunity policy threshold")
        if agreement < float(policy.minimum_agreement):
            reasons.append("ensemble agreement is below opportunity policy threshold")

        regime_name = "UNKNOWN"
        regime_usable = False
        if regime is None:
            if policy.require_usable_regime:
                reasons.append("market regime context is required")
        else:
            mismatch = _check_identity(regime, pair=pair, interval=interval, timestamp=timestamp, name="regime")
            if mismatch:
                reasons.append(mismatch)
            regime_name = str(regime.get("regime", "UNKNOWN"))
            regime_usable = regime.get("analysis_usable") is True and regime.get("status") == "EVALUATED"
            if policy.require_usable_regime and not regime_usable:
                reasons.append("market regime context is not usable")

        session_phase = "UNKNOWN"
        active_sessions: tuple[str, ...] = ()
        if session is None:
            if policy.require_session_context:
                reasons.append("forex session context is required")
        else:
            mismatch = _check_identity(session, pair=pair, interval=interval, timestamp=timestamp, name="session")
            if mismatch:
                reasons.append(mismatch)
            session_status = str(session.get("status", "UNKNOWN"))
            if policy.require_session_context and session_status != "EVALUATED":
                reasons.append("forex session context is not evaluated")
            session_phase = str(session.get("phase", "UNKNOWN"))
            raw_sessions = session.get("active_sessions", ())
            if not isinstance(raw_sessions, (list, tuple)):
                reasons.append("forex session active_sessions is invalid")
            else:
                active_sessions = tuple(str(item) for item in raw_sessions)

        operational_name = None
        operational_usable = False
        if operational_state is None:
            if policy.require_operational_state:
                reasons.append("market operational state is required")
        else:
            mismatch = _check_identity(
                operational_state,
                pair=pair,
                interval=interval,
                timestamp=timestamp,
                name="operational state",
            )
            if mismatch:
                reasons.append(mismatch)
            operational_name = str(operational_state.get("status", "UNKNOWN"))
            operational_usable = operational_state.get("analysis_usable") is True
            if not operational_usable:
                if policy.allow_degraded_operational_state and operational_name == "DEGRADED":
                    warnings.append("operational state is DEGRADED but policy permits analysis")
                    operational_usable = True
                elif policy.require_operational_state:
                    reasons.append("market operational state does not permit analysis")

        contributions = ensemble.get("contributions", ())
        if isinstance(contributions, list):
            contribution_snapshot = tuple(dict(item) for item in contributions if isinstance(item, Mapping))
        elif isinstance(contributions, tuple):
            contribution_snapshot = tuple(dict(item) for item in contributions if isinstance(item, Mapping))
        else:
            contribution_snapshot = ()
            warnings.append("ensemble contributions were unavailable or invalid")

        evidence.append(f"ensemble decision={direction.value}")
        evidence.append(f"ensemble score={score:.6f}")
        evidence.append(f"ensemble agreement={agreement:.6f}")
        if regime is not None:
            evidence.append(f"market regime={regime_name}")
        if session is not None:
            evidence.append(f"session phase={session_phase}")
            evidence.append(
                "active sessions=" + (", ".join(active_sessions) if active_sessions else "NONE")
            )
        if operational_name is not None:
            evidence.append(f"operational state={operational_name}")

        metadata = {
            "calculation": "deterministic_python",
            "contract_version": "2.6.12",
            "point_in_time": True,
            "session_is_context_only": True,
            "policy": policy.to_dict(),
        }

        if reasons:
            return _rejected(
                pair=pair,
                interval=interval,
                timestamp=timestamp,
                direction=direction,
                score=score,
                agreement=agreement,
                conflict=conflict,
                confidence=confidence,
                regime=regime_name,
                session_phase=session_phase,
                active_sessions=active_sessions,
                operational_state=operational_name,
                reasons=reasons,
                warnings=warnings,
                evidence=evidence,
                contributions=contribution_snapshot,
                metadata=metadata,
            )

        return TradeOpportunity(
            pair=pair,
            interval=interval,
            timestamp_utc=timestamp,
            status=OpportunityStatus.CANDIDATE,
            direction=direction,
            ensemble_score=score,
            agreement=agreement,
            conflict=conflict,
            confidence=confidence,
            regime=regime_name,
            session_phase=session_phase,
            active_sessions=active_sessions,
            operational_state=operational_name,
            analysis_usable=True,
            reasons=(),
            warnings=tuple(warnings),
            evidence=tuple(evidence),
            strategy_contributions=contribution_snapshot,
            metadata=metadata,
        )
    except TradeOpportunityError:
        raise
    except Exception as exc:
        return _rejected(
            pair=str(ensemble.get("pair", "UNKNOWN")),
            interval=str(ensemble.get("interval", "UNKNOWN")),
            timestamp=ensemble.get("timestamp_utc"),
            direction=SignalDirection.NEUTRAL,
            score=0.0,
            agreement=0.0,
            conflict=0.0,
            confidence=0.0,
            reasons=[f"opportunity assessment error: {exc}"],
            status=OpportunityStatus.ERROR,
            error=str(exc),
        )


class TradeOpportunityEngine:
    """Reusable facade for deterministic opportunity assessment."""

    def __init__(self, policy: OpportunityPolicy | None = None) -> None:
        self.policy = policy or OpportunityPolicy()

    def assess(self, ensemble: Mapping[str, Any], **kwargs: Any) -> TradeOpportunity:
        kwargs.setdefault("policy", self.policy)
        return assess_trade_opportunity(ensemble, **kwargs)


__all__ = [
    "OpportunityPolicy",
    "OpportunityStatus",
    "TradeOpportunity",
    "TradeOpportunityEngine",
    "TradeOpportunityError",
    "assess_trade_opportunity",
]
