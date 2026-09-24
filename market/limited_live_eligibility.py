"""Deterministic limited-live eligibility assessment boundary.

This module decides whether supplied evidence satisfies configurable eligibility
criteria for consideration of a separately controlled limited-live deployment.
It never authorizes execution and never contacts a broker.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    OPERATIONALLY_BLOCKED = "OPERATIONALLY_BLOCKED"


class EvidenceClass(str, Enum):
    HISTORICAL = "historical"
    SIMULATED = "simulated"
    OOS = "oos"
    FORWARD = "forward"
    LIVE = "live"


@dataclass(frozen=True)
class LimitedLiveCriteria:
    minimum_forward_records: int = 30
    minimum_forward_pnl_records: int = 20
    require_positive_forward_pnl: bool = True
    require_cost_coverage: bool = True
    require_risk_coverage: bool = True
    require_oos_evidence: bool = True
    require_statistical_robustness: bool = True
    require_regime_session_analysis: bool = True
    require_economic_edge_candidate: bool = True
    maximum_forward_degradation_ratio: float | None = None
    maximum_risk_amount: float | None = None
    require_operational_readiness: bool = True
    eligibility_max_age_seconds: float | None = 86400.0


@dataclass(frozen=True)
class EligibilityEvidence:
    forward_records: int
    forward_pnl_records: int
    forward_total_pnl: float
    forward_cost_coverage: bool
    forward_risk_coverage: bool
    oos_status: str
    statistical_status: str
    regime_session_status: str
    economic_edge_status: str
    forward_degradation_ratio: float | None = None
    evidence_classes: tuple[str, ...] = (EvidenceClass.FORWARD.value,)
    operational_readiness: bool = False
    evaluated_at: str | None = None
    source_fingerprints: tuple[str, ...] = ()
    evidence_age_seconds: float | None = None
    maximum_observed_risk_amount: float | None = None


@dataclass(frozen=True)
class EligibilityDecision:
    status: EligibilityStatus
    reasons: tuple[str, ...]
    criteria_fingerprint: str
    evidence_fingerprint: str
    assessment_fingerprint: str
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
        if not math.isfinite(value):
            raise ValueError("non-finite numeric value")
        return value
    return value


def _fingerprint(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _invalid_reasons(criteria: LimitedLiveCriteria, evidence: EligibilityEvidence) -> list[str]:
    reasons: list[str] = []
    if evidence.forward_records < 0 or evidence.forward_pnl_records < 0:
        reasons.append("negative_forward_sample_count")
    if evidence.forward_pnl_records > evidence.forward_records:
        reasons.append("forward_pnl_records_exceed_forward_records")
    if not math.isfinite(evidence.forward_total_pnl):
        reasons.append("non_finite_forward_pnl")
    if evidence.forward_degradation_ratio is not None and (
        not math.isfinite(evidence.forward_degradation_ratio) or evidence.forward_degradation_ratio < 0
    ):
        reasons.append("invalid_forward_degradation_ratio")
    if criteria.maximum_forward_degradation_ratio is not None and criteria.maximum_forward_degradation_ratio < 0:
        reasons.append("invalid_maximum_forward_degradation_ratio")
    if criteria.maximum_risk_amount is not None and (
        not math.isfinite(criteria.maximum_risk_amount) or criteria.maximum_risk_amount < 0
    ):
        reasons.append("invalid_maximum_risk_amount")
    if evidence.maximum_observed_risk_amount is not None and (
        not math.isfinite(evidence.maximum_observed_risk_amount) or evidence.maximum_observed_risk_amount < 0
    ):
        reasons.append("invalid_observed_risk_amount")
    if any(not isinstance(v, str) or not v.strip() for v in evidence.evidence_classes):
        reasons.append("invalid_evidence_class")
    return reasons


def assess_limited_live_eligibility(
    criteria: LimitedLiveCriteria, evidence: EligibilityEvidence
) -> EligibilityDecision:
    """Assess eligibility only; an eligible result is never execution authority."""
    invalid = _invalid_reasons(criteria, evidence)
    criteria_fp = _fingerprint(criteria)
    evidence_fp = _fingerprint(evidence)
    if invalid:
        status = EligibilityStatus.INVALID_EVIDENCE
        reasons = tuple(invalid)
    else:
        reasons_list: list[str] = []
        insufficient = False
        if evidence.forward_records < criteria.minimum_forward_records:
            reasons_list.append("forward_sample_below_minimum")
            insufficient = True
        if evidence.forward_pnl_records < criteria.minimum_forward_pnl_records:
            reasons_list.append("forward_pnl_sample_below_minimum")
            insufficient = True
        if criteria.require_positive_forward_pnl and evidence.forward_total_pnl <= 0:
            reasons_list.append("forward_pnl_not_positive")
        if criteria.require_cost_coverage and not evidence.forward_cost_coverage:
            reasons_list.append("forward_cost_coverage_missing")
            insufficient = True
        if criteria.require_risk_coverage and not evidence.forward_risk_coverage:
            reasons_list.append("forward_risk_coverage_missing")
            insufficient = True
        if criteria.require_oos_evidence and evidence.oos_status not in {"OOS_EVIDENCE", "OOS_STABILITY"}:
            reasons_list.append("oos_evidence_requirement_not_met")
            insufficient = True
        if criteria.require_statistical_robustness and evidence.statistical_status not in {
            "UNCERTAINTY_QUANTIFIED", "WITHIN_SAMPLE_STABILITY"
        }:
            reasons_list.append("statistical_robustness_requirement_not_met")
            insufficient = True
        if criteria.require_regime_session_analysis and evidence.regime_session_status not in {
            "STABLE", "DESCRIPTIVE_ONLY", "CONCENTRATED"
        }:
            reasons_list.append("regime_session_analysis_requirement_not_met")
            insufficient = True
        if criteria.require_economic_edge_candidate and evidence.economic_edge_status != "EDGE_CANDIDATE":
            reasons_list.append("economic_edge_candidate_requirement_not_met")
            insufficient = True
        if criteria.maximum_forward_degradation_ratio is not None:
            if evidence.forward_degradation_ratio is None:
                reasons_list.append("forward_degradation_ratio_missing")
                insufficient = True
            elif evidence.forward_degradation_ratio > criteria.maximum_forward_degradation_ratio:
                reasons_list.append("forward_degradation_limit_exceeded")
        if criteria.maximum_risk_amount is not None:
            if evidence.maximum_observed_risk_amount is None:
                reasons_list.append("observed_risk_amount_missing")
                insufficient = True
            elif evidence.maximum_observed_risk_amount > criteria.maximum_risk_amount:
                reasons_list.append("maximum_risk_amount_exceeded")
        if criteria.require_operational_readiness and not evidence.operational_readiness:
            reasons_list.append("operational_readiness_not_confirmed")
            status = EligibilityStatus.OPERATIONALLY_BLOCKED
        elif insufficient:
            status = EligibilityStatus.INSUFFICIENT_EVIDENCE
        elif reasons_list:
            status = EligibilityStatus.INELIGIBLE
        else:
            status = EligibilityStatus.ELIGIBLE
        reasons = tuple(reasons_list) if reasons_list else ("all_configured_eligibility_gates_satisfied",)
    assessment_fp = _fingerprint({"status": status.value, "reasons": reasons, "criteria": criteria_fp, "evidence": evidence_fp})
    return EligibilityDecision(status, reasons, criteria_fp, evidence_fp, assessment_fp, False)


def eligibility_is_not_execution_authorization(decision: EligibilityDecision) -> bool:
    return decision.execution_authorized is False and decision.status != EligibilityStatus.ELIGIBLE or decision.execution_authorized is False
