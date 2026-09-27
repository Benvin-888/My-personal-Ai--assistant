"""Phase 2.74 reservation-to-decision admission integration.

This module binds an existing 2.73 capital/risk reservation admission to an
existing 2.67 DecisionAdmission.  It does not re-run upstream decision logic,
change the reservation ledger, or authorize execution.

The resulting binding is an auditable point-in-time link that can be carried
into the 2.68 decision journal/provenance layer.  Missing, stale, mismatched,
or non-active reservations fail closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping

from .capital_risk_reservation import CapitalRiskReservation, ReservationStatus
from .capital_risk_reservation_admission import ReservationAdmissionResult
from .decision_admission import AdmissionStatus, DecisionAdmission


class DecisionReservationStatus(str, Enum):
    BOUND = "BOUND"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class DecisionReservationCriteria:
    """Controls for binding reservation evidence to a decision admission."""

    require_admitted_decision: bool = True
    require_active_reservation: bool = True
    require_source_decision_id: bool = True
    require_strategy_match: bool = True
    require_risk_amount_match: bool = True
    require_account_scope: bool = True
    require_reservation_fingerprint: bool = True
    require_source_snapshot_fingerprint: bool = True
    require_admission_fingerprint: bool = True
    require_expiry: bool = True
    require_reservation_not_expired: bool = True


@dataclass(frozen=True)
class DecisionReservationBinding:
    """Immutable provenance link between a decision and its reservation."""

    decision_id: str
    candidate_id: str
    reservation_id: str
    account_scope: str
    strategy_id: str
    strategy_version: str
    decision_fingerprint: str
    reservation_fingerprint: str
    source_snapshot_fingerprint: str
    reservation_admission_fingerprint: str
    reservation_created_at: str
    reservation_expires_at: str | None
    reserved_capital: float
    reserved_risk: float
    binding_status: DecisionReservationStatus
    binding_fingerprint: str
    execution_authorized: bool = False


@dataclass(frozen=True)
class DecisionReservationAssessment:
    """Result of the 2.74 decision/reservation binding boundary."""

    status: DecisionReservationStatus
    reasons: tuple[str, ...]
    binding: DecisionReservationBinding | None
    decision_id: str
    decision_fingerprint: str
    reservation_id: str | None
    reservation_fingerprint: str | None
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
        if not math.isfinite(value):
            raise ValueError("non_finite_value")
    return value


def fingerprint(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _binding_fingerprint(binding: DecisionReservationBinding) -> str:
    return fingerprint(
        DecisionReservationBinding(
            **{**asdict(binding), "binding_fingerprint": ""}
        )
    )


def binding_fingerprint_matches(binding: Any) -> bool:
    """Verify the immutable decision/reservation binding fingerprint."""
    if not isinstance(binding, DecisionReservationBinding):
        return False
    return binding.binding_fingerprint == _binding_fingerprint(binding)


def _invalid_number(value: Any) -> bool:
    return (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    )


def bind_reservation_to_decision(
    decision: DecisionAdmission,
    reservation_result: ReservationAdmissionResult,
    *,
    account_scope: str,
    criteria: DecisionReservationCriteria | None = None,
    now: str | None = None,
) -> DecisionReservationAssessment:
    """Bind a 2.73 reservation admission to a 2.67 decision admission.

    The function consumes upstream results only.  It never creates an
    ExecutionRequest and never changes the decision or reservation state.
    """
    criteria = criteria or DecisionReservationCriteria()
    decision_fp = decision.decision_fingerprint
    reservation = reservation_result.reservation
    reasons: list[str] = []

    if not isinstance(account_scope, str) or not account_scope.strip():
        reasons.append("account_scope_missing")

    if criteria.require_admitted_decision and decision.status is not AdmissionStatus.ADMITTED:
        if decision.status is AdmissionStatus.EXPIRED:
            reasons.append("decision_expired")
            status = DecisionReservationStatus.EXPIRED
        elif decision.status is AdmissionStatus.BLOCKED:
            reasons.append("decision_blocked")
            status = DecisionReservationStatus.BLOCKED
        else:
            reasons.append("decision_not_admitted")
            status = DecisionReservationStatus.REJECTED
    else:
        status = DecisionReservationStatus.BOUND

    if reservation is None:
        reasons.append("reservation_missing")
        if reservation_result.status.value in {"INSUFFICIENT_DATA"}:
            status = DecisionReservationStatus.INSUFFICIENT_DATA
        elif status is DecisionReservationStatus.BOUND:
            status = DecisionReservationStatus.INSUFFICIENT_DATA
    else:
        if reservation_result.execution_authorized:
            reasons.append("reservation_result_cannot_authorize_execution")

        if reservation_result.status.value not in {"AVAILABLE", "LIMITED"}:
            reasons.append("reservation_admission_not_available")
            if reservation_result.status.value == "INSUFFICIENT_DATA":
                status = DecisionReservationStatus.INSUFFICIENT_DATA
            elif status is DecisionReservationStatus.BOUND:
                status = DecisionReservationStatus.REJECTED

        if criteria.require_active_reservation and reservation.status is not ReservationStatus.RESERVED:
            reasons.append("reservation_not_active")
            if reservation.status is ReservationStatus.EXPIRED:
                status = DecisionReservationStatus.EXPIRED
            elif status is DecisionReservationStatus.BOUND:
                status = DecisionReservationStatus.REJECTED

        if criteria.require_source_decision_id and reservation.source_decision_id != decision.decision_id:
            reasons.append("reservation_decision_id_mismatch")

        if criteria.require_strategy_match:
            if reservation.strategy_id != decision.strategy_id:
                reasons.append("reservation_strategy_id_mismatch")
            if reservation.strategy_version != decision.strategy_version:
                reasons.append("reservation_strategy_version_mismatch")

        if criteria.require_risk_amount_match:
            if decision.risk_amount is None:
                reasons.append("decision_risk_amount_missing")
            elif _invalid_number(decision.risk_amount):
                reasons.append("decision_risk_amount_invalid")
            elif not math.isclose(float(reservation.risk_amount), float(decision.risk_amount), rel_tol=0.0, abs_tol=1e-12):
                reasons.append("reservation_risk_amount_mismatch")

        if criteria.require_account_scope and reservation.account_scope != account_scope:
            reasons.append("reservation_account_scope_mismatch")

        if criteria.require_reservation_fingerprint and not reservation.reservation_fingerprint:
            reasons.append("reservation_fingerprint_missing")

        if criteria.require_source_snapshot_fingerprint and not reservation_result.source_snapshot_fingerprint:
            reasons.append("source_snapshot_fingerprint_missing")

        if criteria.require_admission_fingerprint and not reservation_result.admission_fingerprint:
            reasons.append("reservation_admission_fingerprint_missing")

        if criteria.require_expiry and not reservation.expires_at:
            reasons.append("reservation_expiry_missing")

        if reservation.expires_at:
            expiry = _parse_timestamp(reservation.expires_at)
            if expiry is None:
                reasons.append("reservation_expiry_invalid")
            if criteria.require_reservation_not_expired:
                if now is None:
                    reasons.append("reservation_expiry_check_time_missing")
                else:
                    observed = _parse_timestamp(now)
                    if observed is None:
                        reasons.append("reservation_expiry_check_time_invalid")
                    elif expiry is not None and observed >= expiry:
                        reasons.append("reservation_expired")
                        status = DecisionReservationStatus.EXPIRED

        if _invalid_number(reservation.capital_amount) or float(reservation.capital_amount) <= 0:
            reasons.append("reservation_capital_amount_invalid")
        if _invalid_number(reservation.risk_amount) or float(reservation.risk_amount) <= 0:
            reasons.append("reservation_risk_amount_invalid")

    if reasons:
        if status is DecisionReservationStatus.BOUND:
            status = DecisionReservationStatus.INVALID if any(
                reason.endswith("_invalid") or reason.endswith("_missing") for reason in reasons
            ) else DecisionReservationStatus.REJECTED

    if reservation is not None:
        binding_base = DecisionReservationBinding(
            decision_id=decision.decision_id,
            candidate_id=decision.candidate_id,
            reservation_id=reservation.reservation_id,
            account_scope=reservation.account_scope,
            strategy_id=reservation.strategy_id,
            strategy_version=reservation.strategy_version,
            decision_fingerprint=decision.decision_fingerprint,
            reservation_fingerprint=reservation.reservation_fingerprint,
            source_snapshot_fingerprint=reservation_result.source_snapshot_fingerprint,
            reservation_admission_fingerprint=reservation_result.admission_fingerprint,
            reservation_created_at=reservation.created_at,
            reservation_expires_at=reservation.expires_at,
            reserved_capital=float(reservation.capital_amount),
            reserved_risk=float(reservation.risk_amount),
            binding_status=status,
            binding_fingerprint="",
            execution_authorized=False,
        )
        binding = DecisionReservationBinding(
            **{**asdict(binding_base), "binding_fingerprint": _binding_fingerprint(binding_base)}
        )
    else:
        binding = None

    normalized = tuple(sorted(set(reasons)))
    allowed = status is DecisionReservationStatus.BOUND and binding is not None
    return DecisionReservationAssessment(
        status=status,
        reasons=normalized,
        binding=binding,
        decision_id=decision.decision_id,
        decision_fingerprint=decision_fp,
        reservation_id=reservation.reservation_id if reservation is not None else None,
        reservation_fingerprint=reservation.reservation_fingerprint if reservation is not None else None,
        execution_admission_allowed=allowed,
        execution_authorized=False,
    )


def decision_reservation_is_not_execution_authorization(
    assessment: DecisionReservationAssessment,
) -> bool:
    """Explicitly document that reservation binding is not execution authority."""
    return assessment.execution_authorized is False
