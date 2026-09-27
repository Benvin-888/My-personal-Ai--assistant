"""Phase 2.72 capital and risk reservation ledger.

Maintains an auditable, point-in-time reservation state for capital and risk
capacity. Reservations prevent independently evaluated decisions from
oversubscribing the same budget, but they never authorize broker execution.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


class ReservationStatus(str, Enum):
    RESERVED = "RESERVED"
    RELEASED = "RELEASED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"
    INSUFFICIENT_CAPACITY = "INSUFFICIENT_CAPACITY"
    NOT_FOUND = "NOT_FOUND"


class ReservationLedgerStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID = "INVALID"


@dataclass(frozen=True)
class CapitalRiskReservation:
    reservation_id: str
    created_at: str
    account_scope: str
    strategy_id: str
    strategy_version: str
    capital_amount: float
    risk_amount: float
    expires_at: str | None = None
    source_decision_id: str | None = None
    status: ReservationStatus = ReservationStatus.RESERVED
    released_at: str | None = None
    consumed_at: str | None = None
    reservation_fingerprint: str = ""


@dataclass(frozen=True)
class ReservationLedgerSnapshot:
    observed_at: str
    account_scope: str
    capital_budget: float | None
    risk_budget: float | None
    committed_capital: float | None
    committed_risk: float | None
    reservations: tuple[CapitalRiskReservation, ...]
    criteria_version: str = "2.72.0"
    snapshot_fingerprint: str = ""


@dataclass(frozen=True)
class ReservationCriteria:
    require_source_decision_id: bool = True
    require_expiry: bool = True
    max_reservation_lifetime_seconds: float | None = None
    max_strategy_reserved_capital: float | None = None
    max_strategy_reserved_risk: float | None = None
    criteria_version: str = "2.72.0"


@dataclass(frozen=True)
class ReservationAssessment:
    status: ReservationLedgerStatus
    reasons: tuple[str, ...]
    account_scope: str
    available_capital_before: float | None
    available_risk_before: float | None
    active_reserved_capital: float | None
    active_reserved_risk: float | None
    available_capital_after: float | None
    available_risk_after: float | None
    strategy_reserved_capital: float | None
    strategy_reserved_risk: float | None
    criteria_fingerprint: str
    snapshot_fingerprint: str
    assessment_fingerprint: str
    execution_authorized: bool = False


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: _canonical(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, set):
        return sorted(_canonical(v) for v in value)
    if isinstance(value, float):
        return value if math.isfinite(value) else "<non_finite>"
    return value


def fingerprint(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _number(value: Any, name: str, positive: bool = False) -> str | None:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return f"invalid_{name}"
    if float(value) < 0 or (positive and float(value) <= 0):
        return f"invalid_{name}"
    return None


def _active(reservation: CapitalRiskReservation, observed_at: str) -> bool:
    # Time ordering is deliberately caller-supplied and lexical ISO-8601. A
    # reservation with an expiry at or before the observation is not active.
    return reservation.status is ReservationStatus.RESERVED and (
        reservation.expires_at is None or reservation.expires_at > observed_at
    )


def assess_reservation_capacity(
    snapshot: ReservationLedgerSnapshot,
    criteria: ReservationCriteria,
    strategy_id: str | None = None,
    strategy_version: str | None = None,
) -> ReservationAssessment:
    reasons: list[str] = []
    if not snapshot.account_scope.strip() or not snapshot.observed_at.strip():
        reasons.append("missing_snapshot_identity")
    if strategy_id is not None and not strategy_id.strip():
        reasons.append("missing_strategy_id")
    if strategy_version is not None and not strategy_version.strip():
        reasons.append("missing_strategy_version")

    for name, value in (
        ("capital_budget", snapshot.capital_budget),
        ("risk_budget", snapshot.risk_budget),
        ("committed_capital", snapshot.committed_capital),
        ("committed_risk", snapshot.committed_risk),
        ("max_reservation_lifetime_seconds", criteria.max_reservation_lifetime_seconds),
        ("max_strategy_reserved_capital", criteria.max_strategy_reserved_capital),
        ("max_strategy_reserved_risk", criteria.max_strategy_reserved_risk),
    ):
        if value is not None:
            err = _number(value, name)
            if err:
                reasons.append(err)

    for reservation in snapshot.reservations:
        if not reservation.reservation_id.strip() or not reservation.account_scope.strip():
            reasons.append("invalid_reservation_identity")
        if not reservation.strategy_id.strip() or not reservation.strategy_version.strip():
            reasons.append("invalid_reservation_strategy_identity")
        for name, value in (("capital_amount", reservation.capital_amount), ("risk_amount", reservation.risk_amount)):
            err = _number(value, name, positive=True)
            if err:
                reasons.append(err)
        if reservation.status is ReservationStatus.RESERVED and not reservation.reservation_fingerprint:
            reasons.append("missing_reservation_fingerprint")
        elif reservation.reservation_fingerprint and reservation.reservation_fingerprint != fingerprint(
            CapitalRiskReservation(**{**asdict(reservation), "reservation_fingerprint": ""})
        ):
            reasons.append("reservation_fingerprint_mismatch")
        if reservation.account_scope != snapshot.account_scope:
            reasons.append("reservation_account_scope_mismatch")

    snapshot_fp = fingerprint(ReservationLedgerSnapshot(**{**asdict(snapshot), "snapshot_fingerprint": ""}))
    criteria_fp = fingerprint(criteria)

    ids = [r.reservation_id for r in snapshot.reservations]
    if len(ids) != len(set(ids)):
        reasons.append("duplicate_reservation_id")

    active = [r for r in snapshot.reservations if _active(r, snapshot.observed_at)]
    active_capital = sum(r.capital_amount for r in active)
    active_risk = sum(r.risk_amount for r in active)
    strategy_capital = sum(r.capital_amount for r in active if strategy_id is None or (r.strategy_id == strategy_id and r.strategy_version == strategy_version))
    strategy_risk = sum(r.risk_amount for r in active if strategy_id is None or (r.strategy_id == strategy_id and r.strategy_version == strategy_version))

    if snapshot.capital_budget is None:
        reasons.append("capital_budget_missing")
    if snapshot.risk_budget is None:
        reasons.append("risk_budget_missing")

    available_capital_before = (
        snapshot.capital_budget - (snapshot.committed_capital or 0.0) if snapshot.capital_budget is not None else None
    )
    available_risk_before = (
        snapshot.risk_budget - (snapshot.committed_risk or 0.0) if snapshot.risk_budget is not None else None
    )
    available_capital_after = available_capital_before - active_capital if available_capital_before is not None else None
    available_risk_after = available_risk_before - active_risk if available_risk_before is not None else None

    if available_capital_after is not None and available_capital_after < 0:
        reasons.append("active_capital_reservations_exceed_budget")
    if available_risk_after is not None and available_risk_after < 0:
        reasons.append("active_risk_reservations_exceed_budget")
    if criteria.max_strategy_reserved_capital is not None and strategy_capital > criteria.max_strategy_reserved_capital:
        reasons.append("strategy_reserved_capital_exceeded")
    if criteria.max_strategy_reserved_risk is not None and strategy_risk > criteria.max_strategy_reserved_risk:
        reasons.append("strategy_reserved_risk_exceeded")

    invalid = any(r.startswith("invalid_") or r.endswith("_mismatch") or r == "duplicate_reservation_id" for r in reasons)
    missing = any("missing" in r for r in reasons)
    exceeded = any("exceed" in r for r in reasons)
    if invalid:
        status = ReservationLedgerStatus.INVALID
    elif missing:
        status = ReservationLedgerStatus.INSUFFICIENT_DATA
    elif exceeded:
        status = ReservationLedgerStatus.LIMITED
    else:
        status = ReservationLedgerStatus.AVAILABLE if available_capital_after is not None and available_risk_after is not None else ReservationLedgerStatus.INSUFFICIENT_DATA
        if status is ReservationLedgerStatus.AVAILABLE and (available_capital_after == 0 or available_risk_after == 0):
            status = ReservationLedgerStatus.LIMITED
            reasons.append("no_remaining_capacity")
        elif status is ReservationLedgerStatus.AVAILABLE:
            reasons = ["reservation_capacity_available"]

    reasons_tuple = tuple(sorted(set(reasons)))
    assessment_data = {
        "status": status.value,
        "reasons": reasons_tuple,
        "account_scope": snapshot.account_scope,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "criteria": criteria_fp,
        "snapshot": snapshot_fp,
        "active_reserved_capital": active_capital,
        "active_reserved_risk": active_risk,
    }
    assessment_fp = fingerprint(assessment_data)
    return ReservationAssessment(
        status, reasons_tuple, snapshot.account_scope, available_capital_before, available_risk_before,
        active_capital, active_risk, available_capital_after, available_risk_after,
        strategy_capital, strategy_risk, criteria_fp, snapshot_fp, assessment_fp, False,
    )


def validate_reservation_request(
    reservation: CapitalRiskReservation,
    snapshot: ReservationLedgerSnapshot,
    criteria: ReservationCriteria,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if reservation.status is not ReservationStatus.RESERVED:
        reasons.append("reservation_must_start_reserved")
    if not reservation.reservation_id.strip():
        reasons.append("missing_reservation_id")
    if not reservation.created_at.strip():
        reasons.append("missing_created_at")
    if reservation.account_scope != snapshot.account_scope:
        reasons.append("reservation_account_scope_mismatch")
    if not reservation.strategy_id.strip() or not reservation.strategy_version.strip():
        reasons.append("missing_strategy_identity")
    for name, value in (("capital_amount", reservation.capital_amount), ("risk_amount", reservation.risk_amount)):
        err = _number(value, name, positive=True)
        if err:
            reasons.append(err)
    if criteria.require_source_decision_id and not (reservation.source_decision_id or "").strip():
        reasons.append("source_decision_id_missing")
    if criteria.require_expiry and not (reservation.expires_at or "").strip():
        reasons.append("expiry_missing")
    if reservation.expires_at is not None and reservation.expires_at <= reservation.created_at:
        reasons.append("expiry_not_after_creation")
    if criteria.max_reservation_lifetime_seconds is not None and reservation.expires_at is not None:
        try:
            created = datetime.fromisoformat(reservation.created_at.replace("Z", "+00:00"))
            expires = datetime.fromisoformat(reservation.expires_at.replace("Z", "+00:00"))
            if (expires - created).total_seconds() > criteria.max_reservation_lifetime_seconds:
                reasons.append("reservation_lifetime_exceeded")
        except ValueError:
            reasons.append("invalid_reservation_timestamp")
    if reservation.reservation_fingerprint != fingerprint(
        CapitalRiskReservation(**{**asdict(reservation), "reservation_fingerprint": ""})
    ):
        reasons.append("reservation_fingerprint_mismatch")
    return tuple(sorted(set(reasons)))


def make_reservation(
    *,
    reservation_id: str,
    created_at: str,
    account_scope: str,
    strategy_id: str,
    strategy_version: str,
    capital_amount: float,
    risk_amount: float,
    expires_at: str | None,
    source_decision_id: str | None,
) -> CapitalRiskReservation:
    base = CapitalRiskReservation(
        reservation_id=reservation_id, created_at=created_at, account_scope=account_scope,
        strategy_id=strategy_id, strategy_version=strategy_version, capital_amount=capital_amount,
        risk_amount=risk_amount, expires_at=expires_at, source_decision_id=source_decision_id,
    )
    return CapitalRiskReservation(**{**asdict(base), "reservation_fingerprint": fingerprint(base)})


def apply_reservation_event(
    reservation: CapitalRiskReservation,
    event: ReservationStatus,
    event_at: str,
) -> CapitalRiskReservation:
    if event not in {ReservationStatus.RELEASED, ReservationStatus.CONSUMED, ReservationStatus.EXPIRED}:
        raise ValueError("unsupported_reservation_event")
    if reservation.status is not ReservationStatus.RESERVED:
        raise ValueError("reservation_not_active")
    if not event_at.strip():
        raise ValueError("event_at_missing")
    kwargs = asdict(reservation)
    kwargs["status"] = event
    kwargs["released_at"] = event_at if event is ReservationStatus.RELEASED else None
    kwargs["consumed_at"] = event_at if event is ReservationStatus.CONSUMED else None
    kwargs["reservation_fingerprint"] = ""
    updated = CapitalRiskReservation(**kwargs)
    return CapitalRiskReservation(**{**asdict(updated), "reservation_fingerprint": fingerprint(updated)})


def reservation_ledger_is_not_execution_authorization(value: ReservationAssessment) -> bool:
    return value.execution_authorized is False
