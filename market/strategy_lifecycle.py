"""Phase 2.69 strategy lifecycle management.

This module manages the auditable research/deployment state of a strategy.
It consumes evidence produced by earlier APEX phases; it does not create
profitability evidence, allocate capital, or authorize broker execution.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping


class StrategyLifecycleError(ValueError):
    """Raised when a lifecycle transition violates the contract."""


class StrategyLifecycleStage(str, Enum):
    IDEA = "IDEA"
    RESEARCH = "RESEARCH"
    VALIDATING = "VALIDATING"
    FORWARD = "FORWARD"
    ELIGIBLE = "ELIGIBLE"
    LIMITED_LIVE = "LIMITED_LIVE"
    MONITORING = "MONITORING"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class StrategyLifecycleState:
    strategy_id: str
    strategy_version: str
    stage: StrategyLifecycleStage
    changed_at: str
    reason: str
    evidence_fingerprints: Mapping[str, str] | None = None
    criteria_versions: Mapping[str, str] | None = None
    lifecycle_fingerprint: str = ""


@dataclass(frozen=True)
class StrategyLifecycleCriteria:
    """Explicit evidence requirements for forward lifecycle progression."""

    require_profitability_validation: bool = True
    require_statistical_robustness: bool = True
    require_oos_evidence: bool = True
    require_regime_session_stability: bool = True
    require_economic_edge: bool = True
    require_forward_evidence: bool = True
    require_eligibility: bool = True
    require_monitoring_healthy: bool = True
    require_degradation_healthy: bool = True
    criteria_version: str = "2.69.0"


@dataclass(frozen=True)
class StrategyLifecycleEvidence:
    """Point-in-time evidence summary supplied by upstream engines."""

    profitability_status: str | None = None
    statistical_status: str | None = None
    oos_status: str | None = None
    regime_session_status: str | None = None
    economic_edge_status: str | None = None
    forward_status: str | None = None
    eligibility_status: str | None = None
    monitoring_status: str | None = None
    degradation_status: str | None = None
    fingerprints: Mapping[str, str] | None = None


def _canonical(value: Any) -> Any:
    if hasattr(value, "value") and isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: _canonical(v) for k, v in asdict(value).items() if k != "lifecycle_fingerprint"}
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise StrategyLifecycleError("non_finite_value")
    return value


def fingerprint(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise StrategyLifecycleError(f"missing_{field}")


_ALLOWED_FORWARD = {
    StrategyLifecycleStage.IDEA: {StrategyLifecycleStage.RESEARCH, StrategyLifecycleStage.RETIRED},
    StrategyLifecycleStage.RESEARCH: {StrategyLifecycleStage.VALIDATING, StrategyLifecycleStage.IDEA, StrategyLifecycleStage.RETIRED},
    StrategyLifecycleStage.VALIDATING: {StrategyLifecycleStage.FORWARD, StrategyLifecycleStage.RESEARCH, StrategyLifecycleStage.RETIRED},
    StrategyLifecycleStage.FORWARD: {StrategyLifecycleStage.ELIGIBLE, StrategyLifecycleStage.VALIDATING, StrategyLifecycleStage.RETIRED},
    StrategyLifecycleStage.ELIGIBLE: {StrategyLifecycleStage.LIMITED_LIVE, StrategyLifecycleStage.FORWARD, StrategyLifecycleStage.SUSPENDED, StrategyLifecycleStage.RETIRED},
    StrategyLifecycleStage.LIMITED_LIVE: {StrategyLifecycleStage.MONITORING, StrategyLifecycleStage.DEGRADED, StrategyLifecycleStage.SUSPENDED, StrategyLifecycleStage.RETIRED},
    StrategyLifecycleStage.MONITORING: {StrategyLifecycleStage.DEGRADED, StrategyLifecycleStage.SUSPENDED, StrategyLifecycleStage.RETIRED},
    StrategyLifecycleStage.DEGRADED: {StrategyLifecycleStage.MONITORING, StrategyLifecycleStage.SUSPENDED, StrategyLifecycleStage.VALIDATING, StrategyLifecycleStage.RETIRED},
    StrategyLifecycleStage.SUSPENDED: {StrategyLifecycleStage.VALIDATING, StrategyLifecycleStage.RETIRED},
    StrategyLifecycleStage.RETIRED: set(),
}


def validate_state(state: StrategyLifecycleState) -> StrategyLifecycleState:
    _text(state.strategy_id, "strategy_id")
    _text(state.strategy_version, "strategy_version")
    _text(state.changed_at, "changed_at")
    _text(state.reason, "reason")
    _canonical(state.evidence_fingerprints)
    _canonical(state.criteria_versions)
    expected = fingerprint(StrategyLifecycleState(
        strategy_id=state.strategy_id, strategy_version=state.strategy_version,
        stage=state.stage, changed_at=state.changed_at, reason=state.reason,
        evidence_fingerprints=state.evidence_fingerprints,
        criteria_versions=state.criteria_versions,
    ))
    if state.lifecycle_fingerprint and state.lifecycle_fingerprint != expected:
        raise StrategyLifecycleError("lifecycle_fingerprint_mismatch")
    return StrategyLifecycleState(
        strategy_id=state.strategy_id, strategy_version=state.strategy_version,
        stage=state.stage, changed_at=state.changed_at, reason=state.reason,
        evidence_fingerprints=state.evidence_fingerprints,
        criteria_versions=state.criteria_versions,
        lifecycle_fingerprint=expected,
    )


def _required_failures(stage: StrategyLifecycleStage, evidence: StrategyLifecycleEvidence, criteria: StrategyLifecycleCriteria) -> tuple[str, ...]:
    if stage == StrategyLifecycleStage.VALIDATING:
        checks = {
            "profitability_validation": (criteria.require_profitability_validation, evidence.profitability_status in {"VALID", "PROFITABLE_CANDIDATE"}),
            "statistical_robustness": (criteria.require_statistical_robustness, evidence.statistical_status in {"UNCERTAINTY_QUANTIFIED", "WITHIN_SAMPLE_STABILITY"}),
            "oos_evidence": (criteria.require_oos_evidence, evidence.oos_status in {"OOS_EVIDENCE", "OOS_STABILITY"}),
            "regime_session_stability": (criteria.require_regime_session_stability, evidence.regime_session_status == "STABLE"),
            "economic_edge": (criteria.require_economic_edge, evidence.economic_edge_status == "EDGE_CANDIDATE"),
        }
    elif stage == StrategyLifecycleStage.FORWARD:
        checks = {"forward_evidence": (criteria.require_forward_evidence, evidence.forward_status in {"EXECUTED", "RECONCILIATION_PENDING", "OUTCOME_CONFIRMED", "FORWARD_EVIDENCE"})}
    elif stage == StrategyLifecycleStage.ELIGIBLE:
        checks = {"eligibility": (criteria.require_eligibility, evidence.eligibility_status == "ELIGIBLE")}
    elif stage == StrategyLifecycleStage.LIMITED_LIVE:
        checks = {
            "monitoring": (criteria.require_monitoring_healthy, evidence.monitoring_status == "HEALTHY"),
            "degradation": (criteria.require_degradation_healthy, evidence.degradation_status == "HEALTHY"),
        }
    else:
        return ()
    return tuple(name for name, (required, passed) in checks.items() if required and not passed)


def transition(
    current: StrategyLifecycleState,
    target: StrategyLifecycleStage,
    *,
    changed_at: str,
    reason: str,
    evidence: StrategyLifecycleEvidence | None = None,
    criteria: StrategyLifecycleCriteria | None = None,
) -> StrategyLifecycleState:
    """Create the next lifecycle state after validating transition gates."""
    current = validate_state(current)
    evidence = evidence or StrategyLifecycleEvidence()
    criteria = criteria or StrategyLifecycleCriteria()
    if target not in _ALLOWED_FORWARD[current.stage]:
        raise StrategyLifecycleError(f"invalid_transition:{current.stage.value}->{target.value}")
    _text(changed_at, "changed_at")
    _text(reason, "reason")
    failures = _required_failures(target, evidence, criteria)
    if failures:
        raise StrategyLifecycleError("evidence_gate_failed:" + ",".join(failures))
    return validate_state(StrategyLifecycleState(
        strategy_id=current.strategy_id,
        strategy_version=current.strategy_version,
        stage=target,
        changed_at=changed_at,
        reason=reason,
        evidence_fingerprints=evidence.fingerprints,
        criteria_versions={"2.69": criteria.criteria_version},
    ))


def initial_state(strategy_id: str, strategy_version: str, *, changed_at: str, reason: str = "strategy_created") -> StrategyLifecycleState:
    return validate_state(StrategyLifecycleState(
        strategy_id=strategy_id, strategy_version=strategy_version,
        stage=StrategyLifecycleStage.IDEA, changed_at=changed_at, reason=reason,
    ))


class InMemoryStrategyLifecycle:
    """Append-only lifecycle history; it has no execution or capital authority."""

    def __init__(self) -> None:
        self._current: dict[str, StrategyLifecycleState] = {}
        self._history: dict[str, list[StrategyLifecycleState]] = {}

    def create(self, state: StrategyLifecycleState) -> str:
        state = validate_state(state)
        if state.stage is not StrategyLifecycleStage.IDEA:
            raise StrategyLifecycleError("initial_stage_must_be_idea")
        if state.strategy_id in self._current:
            raise StrategyLifecycleError("strategy_already_exists")
        self._current[state.strategy_id] = state
        self._history[state.strategy_id] = [state]
        return state.strategy_id

    def get(self, strategy_id: str) -> StrategyLifecycleState | None:
        return self._current.get(strategy_id)

    def history(self, strategy_id: str) -> tuple[StrategyLifecycleState, ...]:
        return tuple(self._history.get(strategy_id, ()))

    def transition(self, strategy_id: str, target: StrategyLifecycleStage, **kwargs: Any) -> StrategyLifecycleState:
        current = self._current.get(strategy_id)
        if current is None:
            raise StrategyLifecycleError("strategy_not_found")
        state = transition(current, target, **kwargs)
        self._current[strategy_id] = state
        self._history[strategy_id].append(state)
        return state
