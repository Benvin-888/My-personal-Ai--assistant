"""Phase 2.67 controlled live decision admission pipeline.

This module orchestrates existing APEX decision boundaries for one point-in-time
candidate.  It does not implement market intelligence, economics, risk,
portfolio, monitoring, degradation, or safety inference itself.  It consumes
structured upstream results and produces an auditable DecisionAdmission.

A DecisionAdmission is not an ExecutionRequest and never grants broker or
execution authority.  A fresh final safety check is required immediately before
an external execution boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


class AdmissionStatus(str, Enum):
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"


class DecisionStage(str, Enum):
    MARKET = "MARKET"
    OPPORTUNITY = "OPPORTUNITY"
    ECONOMIC_EDGE = "ECONOMIC_EDGE"
    ELIGIBILITY = "ELIGIBILITY"
    PORTFOLIO = "PORTFOLIO"
    RISK = "RISK"
    MONITORING = "MONITORING"
    DEGRADATION = "DEGRADATION"
    SAFETY = "SAFETY"
    FRESHNESS = "FRESHNESS"


@dataclass(frozen=True)
class DecisionContext:
    decision_id: str
    observed_at: str
    symbol: str
    timeframe: str
    strategy_id: str
    strategy_version: str
    candidate_id: str
    direction: str
    quantity: float | None
    risk_amount: float | None
    market_fingerprint: str
    opportunity_fingerprint: str
    evidence_fingerprint: str
    economic_edge_fingerprint: str
    eligibility_fingerprint: str
    portfolio_fingerprint: str
    risk_fingerprint: str
    monitoring_fingerprint: str
    degradation_fingerprint: str
    safety_fingerprint: str


@dataclass(frozen=True)
class StageResult:
    stage: DecisionStage
    status: str
    passed: bool
    reasons: tuple[str, ...] = ()
    fingerprint: str = ""


@dataclass(frozen=True)
class AdmissionCriteria:
    decision_ttl_seconds: float = 10.0
    require_market_pass: bool = True
    require_opportunity_pass: bool = True
    require_economic_edge_pass: bool = True
    require_eligibility_pass: bool = True
    require_portfolio_pass: bool = True
    require_risk_pass: bool = True
    require_monitoring_pass: bool = True
    block_on_degradation: bool = True
    require_safety_admissible: bool = True
    require_fresh_safety_recheck: bool = True


@dataclass(frozen=True)
class DecisionAdmission:
    decision_id: str
    candidate_id: str
    status: AdmissionStatus
    symbol: str
    timeframe: str
    strategy_id: str
    strategy_version: str
    direction: str
    quantity: float | None
    risk_amount: float | None
    observed_at: str
    expires_at: str
    stages: tuple[StageResult, ...]
    blocking_reasons: tuple[str, ...]
    evidence_fingerprint: str
    decision_fingerprint: str
    safety_state: str
    execution_admission_allowed: bool
    execution_authorized: bool = False


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: _canonical(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, set):
        return sorted(_canonical(v) for v in value)
    if isinstance(value, float):
        return value if math.isfinite(value) else "<non_finite>"
    return value


def _fingerprint(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
    else:
        for name in names:
            if hasattr(value, name):
                return getattr(value, name)
    return default


def _status(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value) if value is not None else ""


def _passed(value: Any) -> bool:
    explicit = _read(value, "passed", "valid", "admissible", "execution_admission_allowed")
    if explicit is not None:
        return explicit is True
    status = _status(_read(value, "status", default=value)).upper()
    return status in {"QUALIFIED", "QUALIFIED_WITH_LIMITATIONS", "ELIGIBLE", "APPROVED", "HEALTHY", "ADMITTED", "OOS_STABILITY", "OOS_EVIDENCE", "EDGE_CANDIDATE"}


def _reasons(value: Any) -> tuple[str, ...]:
    reasons = _read(value, "blocking_reasons", "reasons", default=())
    if reasons is None:
        return ()
    if isinstance(reasons, str):
        return (reasons,)
    return tuple(sorted(str(item) for item in reasons))


def _stage(stage: DecisionStage, result: Any, required: bool) -> StageResult:
    status = _status(_read(result, "status", default=result))
    passed = _passed(result) if required else True
    reasons = _reasons(result)
    return StageResult(stage=stage, status=status, passed=passed, reasons=reasons, fingerprint=_read(result, "fingerprint", "assessment_fingerprint", "evidence_fingerprint", default=_fingerprint(result)))


def _validate_context(context: DecisionContext) -> tuple[str, ...]:
    required = {
        "decision_id": context.decision_id,
        "observed_at": context.observed_at,
        "symbol": context.symbol,
        "timeframe": context.timeframe,
        "strategy_id": context.strategy_id,
        "strategy_version": context.strategy_version,
        "candidate_id": context.candidate_id,
        "direction": context.direction,
    }
    missing = [name for name, value in required.items() if not isinstance(value, str) or not value.strip()]
    reasons = [f"missing_{name}" for name in missing]
    if context.quantity is not None and (not isinstance(context.quantity, (int, float)) or isinstance(context.quantity, bool) or not math.isfinite(float(context.quantity)) or context.quantity <= 0):
        reasons.append("invalid_quantity")
    if context.risk_amount is not None and (not isinstance(context.risk_amount, (int, float)) or isinstance(context.risk_amount, bool) or not math.isfinite(float(context.risk_amount)) or context.risk_amount < 0):
        reasons.append("invalid_risk_amount")
    return tuple(sorted(reasons))


def _expiry_is_valid(context: DecisionContext, now_seconds: float, ttl_seconds: float) -> bool:
    """Validate freshness using caller-supplied elapsed seconds, avoiding clock dependence."""
    return math.isfinite(now_seconds) and now_seconds >= 0 and now_seconds <= ttl_seconds


def evaluate_decision_admission(
    context: DecisionContext,
    criteria: AdmissionCriteria,
    *,
    market: Any,
    opportunity: Any,
    economic_edge: Any,
    eligibility: Any,
    portfolio: Any,
    risk: Any,
    monitoring: Any,
    degradation: Any,
    safety: Any,
    elapsed_seconds: float = 0.0,
    final_safety_recheck: Any | None = None,
) -> DecisionAdmission:
    """Evaluate a candidate through existing boundaries without executing it."""
    invalid = _validate_context(context)
    if not math.isfinite(criteria.decision_ttl_seconds) or criteria.decision_ttl_seconds <= 0:
        invalid = tuple(sorted((*invalid, "invalid_decision_ttl_seconds")))
    if not _expiry_is_valid(context, elapsed_seconds, criteria.decision_ttl_seconds):
        status = AdmissionStatus.EXPIRED if not invalid else AdmissionStatus.INVALID
        reason = "decision_expired" if not invalid else "invalid_context"
        return _build_admission(context, status, (), (reason,), safety, evidence=context.evidence_fingerprint)
    if invalid:
        return _build_admission(context, AdmissionStatus.INVALID, (), invalid, safety, evidence=context.evidence_fingerprint)

    stages = (
        _stage(DecisionStage.MARKET, market, criteria.require_market_pass),
        _stage(DecisionStage.OPPORTUNITY, opportunity, criteria.require_opportunity_pass),
        _stage(DecisionStage.ECONOMIC_EDGE, economic_edge, criteria.require_economic_edge_pass),
        _stage(DecisionStage.ELIGIBILITY, eligibility, criteria.require_eligibility_pass),
        _stage(DecisionStage.PORTFOLIO, portfolio, criteria.require_portfolio_pass),
        _stage(DecisionStage.RISK, risk, criteria.require_risk_pass),
        _stage(DecisionStage.MONITORING, monitoring, criteria.require_monitoring_pass),
        _stage(DecisionStage.DEGRADATION, degradation, criteria.block_on_degradation),
        _stage(DecisionStage.SAFETY, safety, criteria.require_safety_admissible),
    )
    if criteria.require_fresh_safety_recheck:
        stages += (_stage(DecisionStage.FRESHNESS, final_safety_recheck if final_safety_recheck is not None else {"status": "MISSING", "passed": False, "reasons": ("fresh_safety_recheck_required",)}, True),)

    failed = [stage for stage in stages if not stage.passed]
    reasons = tuple(sorted({reason for stage in failed for reason in stage.reasons}))
    if not reasons and failed:
        reasons = tuple(f"{stage.stage.value.lower()}_gate_failed" for stage in failed)

    if any(stage.stage is DecisionStage.SAFETY and not stage.passed for stage in failed) or any(stage.stage is DecisionStage.FRESHNESS and not stage.passed for stage in failed):
        status = AdmissionStatus.BLOCKED
    elif any(stage.stage is DecisionStage.ELIGIBILITY and not stage.passed for stage in failed):
        status = AdmissionStatus.REJECTED
    elif any(stage.status.upper() in {"INSUFFICIENT_EVIDENCE", "INSUFFICIENT_DATA", "DESCRIPTIVE_ONLY"} for stage in failed):
        status = AdmissionStatus.INSUFFICIENT_EVIDENCE
    elif failed:
        status = AdmissionStatus.REJECTED
    else:
        status = AdmissionStatus.ADMITTED

    return _build_admission(context, status, stages, reasons, safety, evidence=context.evidence_fingerprint)


def _build_admission(context: DecisionContext, status: AdmissionStatus, stages: Sequence[StageResult], reasons: Sequence[str], safety: Any, *, evidence: str) -> DecisionAdmission:
    safety_state = _status(_read(safety, "state", default="UNKNOWN"))
    payload = {
        "decision_id": context.decision_id,
        "candidate_id": context.candidate_id,
        "status": status,
        "stages": stages,
        "reasons": tuple(sorted(set(reasons))),
        "safety_state": safety_state,
        "evidence": evidence,
    }
    return DecisionAdmission(
        decision_id=context.decision_id,
        candidate_id=context.candidate_id,
        status=status,
        symbol=context.symbol,
        timeframe=context.timeframe,
        strategy_id=context.strategy_id,
        strategy_version=context.strategy_version,
        direction=context.direction,
        quantity=context.quantity,
        risk_amount=context.risk_amount,
        observed_at=context.observed_at,
        expires_at=f"{context.observed_at}+{status.value}",
        stages=tuple(stages),
        blocking_reasons=tuple(sorted(set(reasons))),
        evidence_fingerprint=evidence,
        decision_fingerprint=_fingerprint(payload),
        safety_state=safety_state,
        execution_admission_allowed=status is AdmissionStatus.ADMITTED,
        execution_authorized=False,
    )


def final_safety_recheck_passes(admission: DecisionAdmission, safety: Any) -> bool:
    """Return whether an admitted decision still has a valid final safety state."""
    if admission.status is not AdmissionStatus.ADMITTED or not admission.execution_admission_allowed:
        return False
    return _passed(safety) and _status(_read(safety, "state", default="")) == "ARMED"


def decision_admission_is_not_execution_request(admission: DecisionAdmission) -> bool:
    return admission.execution_authorized is False
