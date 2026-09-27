"""Phase 2.76 controlled decision-to-execution-request bridge.

This boundary consumes already-admitted decision/reservation evidence and an
explicitly approved execution contract.  It verifies that the exact trade
terms supplied for execution still match the authoritative upstream state.

It does not execute, authorize, contact a broker, read credentials, resize a
trade, or choose execution terms.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping

from .capital_risk_reservation import CapitalRiskReservation, fingerprint as reservation_fingerprint
from .decision_admission import decision_admission_fingerprint_matches
from .decision_reservation_integration import (
    DecisionReservationAssessment,
    DecisionReservationStatus,
    binding_fingerprint_matches,
)


class ExecutionRequestBridgeStatus(str, Enum):
    MATERIALIZED = "MATERIALIZED"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ExecutionContractCriteria:
    """Explicitly approved execution terms required by the 2.76 bridge."""

    broker: str
    execution_mode: str
    account_scope: str
    currency: str
    order_type: str
    contract_type: str | None
    approved_stake: float | None
    criteria_version: str = "2.76.0"

    def __post_init__(self) -> None:
        for name in ("broker", "execution_mode", "account_scope", "currency", "order_type"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name}_missing")
        if self.approved_stake is not None:
            if isinstance(self.approved_stake, bool) or not isinstance(self.approved_stake, (int, float)):
                raise ValueError("approved_stake_invalid")
            if not math.isfinite(float(self.approved_stake)) or float(self.approved_stake) <= 0:
                raise ValueError("approved_stake_invalid")


@dataclass(frozen=True)
class ApprovedExecutionIntent:
    """Exact trade terms supplied by the upstream approved execution path."""

    broker: str
    execution_mode: str
    account_scope: str
    symbol: str
    direction: str
    quantity: float
    stake: float | None
    currency: str
    order_type: str
    requested_at: str
    expires_at: str
    contract_type: str | None = None


@dataclass(frozen=True)
class ExecutionRequestCandidate:
    """Immutable execution request candidate awaiting downstream safety gates."""

    request_id: str
    decision_id: str
    candidate_id: str
    reservation_id: str
    account_scope: str
    broker: str
    execution_mode: str
    symbol: str
    direction: str
    quantity: float
    stake: float | None
    currency: str
    order_type: str
    contract_type: str | None
    requested_at: str
    expires_at: str
    strategy_id: str
    strategy_version: str
    decision_fingerprint: str
    reservation_fingerprint: str
    reservation_admission_fingerprint: str
    source_snapshot_fingerprint: str
    decision_reservation_binding_fingerprint: str
    execution_contract_fingerprint: str
    request_fingerprint: str
    execution_authorized: bool = False


@dataclass(frozen=True)
class ExecutionRequestBridgeAssessment:
    """Result of request materialization; never execution authority."""

    status: ExecutionRequestBridgeStatus
    reasons: tuple[str, ...]
    request: ExecutionRequestCandidate | None
    decision_id: str
    reservation_id: str | None
    binding_fingerprint: str | None
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
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non_finite_value")
    return value


def fingerprint(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def execution_contract_fingerprint(criteria: ExecutionContractCriteria) -> str:
    return fingerprint(criteria)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _valid_positive_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0
    )


def _valid_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _same_text(left: Any, right: Any) -> bool:
    return _valid_text(left) and _valid_text(right) and left.strip().casefold() == right.strip().casefold()


def _canonical_direction(value: Any) -> str | None:
    if not _valid_text(value):
        return None
    normalized = value.strip().upper()
    return {"LONG": "BUY", "SHORT": "SELL", "BUY": "BUY", "SELL": "SELL"}.get(normalized)


def _same_number(left: Any, right: Any) -> bool:
    if not _valid_positive_number(left) or not _valid_positive_number(right):
        return False
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)


def _request_fingerprint(request: ExecutionRequestCandidate) -> str:
    base = ExecutionRequestCandidate(**{**asdict(request), "request_fingerprint": ""})
    return fingerprint(base)


def _reservation_binding_fingerprint_matches(reservation: Any, decision_id: str) -> bool:
    """Verify reservation fingerprint from the immutable fields carried by the binding."""
    required = (
        "reservation_id", "account_scope", "strategy_id", "strategy_version",
        "reserved_capital", "reserved_risk", "reservation_created_at",
        "reservation_expires_at", "reservation_fingerprint",
    )
    if any(not hasattr(reservation, name) for name in required):
        return False
    reconstructed = CapitalRiskReservation(
        reservation_id=reservation.reservation_id,
        created_at=reservation.reservation_created_at,
        account_scope=reservation.account_scope,
        strategy_id=reservation.strategy_id,
        strategy_version=reservation.strategy_version,
        capital_amount=float(reservation.reserved_capital),
        risk_amount=float(reservation.reserved_risk),
        expires_at=reservation.reservation_expires_at,
        source_decision_id=decision_id,
    )
    return reservation.reservation_fingerprint == reservation_fingerprint(reconstructed)


def materialize_execution_request(
    decision: Any,
    binding: DecisionReservationAssessment,
    intent: ApprovedExecutionIntent,
    *,
    request_id: str,
    now: str,
    criteria: ExecutionContractCriteria,
) -> ExecutionRequestBridgeAssessment:
    """Materialize a candidate only when every approved contract is consistent."""
    reasons: list[str] = []
    status = ExecutionRequestBridgeStatus.MATERIALIZED

    if not isinstance(criteria, ExecutionContractCriteria):
        return ExecutionRequestBridgeAssessment(
            status=ExecutionRequestBridgeStatus.INVALID,
            reasons=("execution_contract_criteria_invalid",),
            request=None,
            decision_id=str(getattr(decision, "decision_id", "") or ""),
            reservation_id=None,
            binding_fingerprint=None,
            execution_admission_allowed=False,
            execution_authorized=False,
        )

    if not _valid_text(request_id):
        reasons.append("request_id_missing")
    observed_at = _parse_timestamp(now)
    if observed_at is None:
        reasons.append("request_time_invalid")

    decision_id = getattr(decision, "decision_id", None)
    candidate_id = getattr(decision, "candidate_id", None)
    strategy_id = getattr(decision, "strategy_id", None)
    strategy_version = getattr(decision, "strategy_version", None)
    decision_fp = getattr(decision, "decision_fingerprint", None)
    decision_status = getattr(getattr(decision, "status", None), "value", getattr(decision, "status", None))

    if not _valid_text(decision_id) or not _valid_text(candidate_id):
        reasons.append("decision_identity_missing")
    if decision_status != "ADMITTED":
        reasons.append("decision_not_admitted")
        if decision_status == "EXPIRED":
            status = ExecutionRequestBridgeStatus.EXPIRED
        elif decision_status == "BLOCKED":
            status = ExecutionRequestBridgeStatus.BLOCKED
        else:
            status = ExecutionRequestBridgeStatus.REJECTED
    if not _valid_text(decision_fp):
        reasons.append("decision_fingerprint_missing")
    elif not decision_admission_fingerprint_matches(decision):
        reasons.append("decision_fingerprint_mismatch")
        status = ExecutionRequestBridgeStatus.INVALID
    if not _valid_text(strategy_id) or not _valid_text(strategy_version):
        reasons.append("strategy_identity_missing")

    if not isinstance(binding, DecisionReservationAssessment) or binding.binding is None:
        reasons.append("binding_type_invalid")
        status = ExecutionRequestBridgeStatus.INVALID
        reservation = None
    else:
        reservation = binding.binding
        if binding.status is not DecisionReservationStatus.BOUND or not binding.execution_admission_allowed:
            reasons.append("decision_reservation_binding_not_allowed")
            if binding.status is DecisionReservationStatus.EXPIRED:
                status = ExecutionRequestBridgeStatus.EXPIRED
            elif binding.status is DecisionReservationStatus.BLOCKED:
                status = ExecutionRequestBridgeStatus.BLOCKED
            elif binding.status is DecisionReservationStatus.INSUFFICIENT_DATA:
                status = ExecutionRequestBridgeStatus.INSUFFICIENT_DATA
            elif status is ExecutionRequestBridgeStatus.MATERIALIZED:
                status = ExecutionRequestBridgeStatus.REJECTED
        if binding.execution_authorized:
            reasons.append("binding_cannot_authorize_execution")
            status = ExecutionRequestBridgeStatus.INVALID
        if not binding_fingerprint_matches(binding.binding):
            reasons.append("binding_fingerprint_mismatch")
            status = ExecutionRequestBridgeStatus.INVALID

    if reservation is None:
        reasons.append("reservation_binding_missing")
    else:
        if reservation.decision_id != decision_id:
            reasons.append("binding_decision_id_mismatch")
        if reservation.account_scope != getattr(binding.binding, "account_scope", None):
            reasons.append("binding_account_scope_inconsistent")
        if reservation.strategy_id != strategy_id or reservation.strategy_version != strategy_version:
            reasons.append("binding_strategy_mismatch")
        if not _reservation_binding_fingerprint_matches(reservation, decision_id):
            reasons.append("reservation_fingerprint_mismatch")
            status = ExecutionRequestBridgeStatus.INVALID
        if not _valid_text(reservation.reservation_admission_fingerprint):
            reasons.append("reservation_admission_fingerprint_missing")
        if not _valid_text(reservation.source_snapshot_fingerprint):
            reasons.append("source_snapshot_fingerprint_missing")
        if not _valid_text(reservation.binding_fingerprint):
            reasons.append("binding_fingerprint_missing")

    if not isinstance(intent, ApprovedExecutionIntent):
        reasons.append("intent_type_invalid")
        status = ExecutionRequestBridgeStatus.INVALID
    else:
        for name, value in (
            ("broker", intent.broker),
            ("execution_mode", intent.execution_mode),
            ("account_scope", intent.account_scope),
            ("symbol", intent.symbol),
            ("direction", intent.direction),
            ("currency", intent.currency),
            ("order_type", intent.order_type),
            ("requested_at", intent.requested_at),
            ("expires_at", intent.expires_at),
        ):
            if not _valid_text(value):
                reasons.append(f"{name}_missing")

        if _canonical_direction(intent.direction) is None:
            reasons.append("direction_invalid")
        if not _valid_positive_number(intent.quantity):
            reasons.append("quantity_invalid")
        if intent.stake is not None and not _valid_positive_number(intent.stake):
            reasons.append("stake_invalid")

        requested_at = _parse_timestamp(intent.requested_at)
        expires_at = _parse_timestamp(intent.expires_at)
        if requested_at is None:
            reasons.append("requested_at_invalid")
        if expires_at is None:
            reasons.append("expires_at_invalid")
        if requested_at is not None and expires_at is not None and expires_at <= requested_at:
            reasons.append("request_expiry_not_after_request_time")
        if observed_at is not None and expires_at is not None and observed_at >= expires_at:
            reasons.append("request_expired")
            status = ExecutionRequestBridgeStatus.EXPIRED
        if requested_at is not None and observed_at is not None and requested_at > observed_at:
            reasons.append("request_time_in_future")

        decision_expires_at = _parse_timestamp(getattr(decision, "expires_at", None))
        if decision_expires_at is None:
            reasons.append("decision_expiry_invalid")
        elif requested_at is not None and requested_at > decision_expires_at:
            reasons.append("request_after_decision_expiry")
            status = ExecutionRequestBridgeStatus.EXPIRED
        elif expires_at is not None and expires_at > decision_expires_at:
            reasons.append("request_expiry_after_decision_expiry")
            status = ExecutionRequestBridgeStatus.EXPIRED

        if reservation is not None and reservation.reservation_expires_at:
            reservation_expires_at = _parse_timestamp(reservation.reservation_expires_at)
            if reservation_expires_at is None:
                reasons.append("reservation_expiry_invalid")
            elif requested_at is not None and requested_at > reservation_expires_at:
                reasons.append("request_after_reservation_expiry")
                status = ExecutionRequestBridgeStatus.EXPIRED
            elif expires_at is not None and expires_at > reservation_expires_at:
                reasons.append("request_expiry_after_reservation_expiry")
                status = ExecutionRequestBridgeStatus.EXPIRED

        if not _same_text(intent.broker, criteria.broker):
            reasons.append("intent_broker_mismatch")
        if not _same_text(intent.execution_mode, criteria.execution_mode):
            reasons.append("intent_execution_mode_mismatch")
        if not _same_text(intent.account_scope, criteria.account_scope):
            reasons.append("intent_account_scope_policy_mismatch")
        if not _same_text(intent.currency, criteria.currency):
            reasons.append("intent_currency_mismatch")
        if not _same_text(intent.order_type, criteria.order_type):
            reasons.append("intent_order_type_mismatch")
        if criteria.contract_type is None:
            if intent.contract_type is not None:
                reasons.append("intent_contract_type_mismatch")
        elif not _same_text(intent.contract_type, criteria.contract_type):
            reasons.append("intent_contract_type_mismatch")
        if criteria.approved_stake is None:
            if intent.stake is not None:
                reasons.append("intent_stake_not_approved")
        elif not _same_number(intent.stake, criteria.approved_stake):
            reasons.append("intent_stake_mismatch")

    if reservation is not None and isinstance(intent, ApprovedExecutionIntent):
        if intent.account_scope != reservation.account_scope:
            reasons.append("intent_account_scope_mismatch")
        if decision_id != reservation.decision_id:
            reasons.append("reservation_decision_id_mismatch")
        decision_direction = _canonical_direction(getattr(decision, "direction", None))
        intent_direction = _canonical_direction(intent.direction)
        if decision_direction is None:
            reasons.append("decision_direction_missing")
        elif intent_direction != decision_direction:
            reasons.append("intent_direction_mismatch")
        decision_symbol = getattr(decision, "symbol", None)
        if not _same_text(intent.symbol, decision_symbol):
            reasons.append("intent_symbol_mismatch")
        decision_quantity = getattr(decision, "quantity", None)
        if decision_quantity is None or not _same_number(intent.quantity, decision_quantity):
            reasons.append("intent_quantity_mismatch")
        if criteria.approved_stake is not None and not math.isclose(float(reservation.reserved_risk), float(criteria.approved_stake), rel_tol=0.0, abs_tol=1e-12):
            reasons.append("approved_stake_reservation_risk_mismatch")
        if not _same_text(intent.account_scope, reservation.account_scope):
            reasons.append("intent_binding_account_scope_mismatch")

    # The reservation admission fingerprint is evidence owned by the admission
    # result.  When the binding does not expose the original result, its value
    # is nevertheless cryptographically covered by the binding fingerprint.
    if isinstance(binding, DecisionReservationAssessment) and binding.binding is not None:
        if not _valid_text(binding.binding.reservation_admission_fingerprint):
            reasons.append("reservation_admission_fingerprint_missing")

    if reasons and status is ExecutionRequestBridgeStatus.MATERIALIZED:
        status = ExecutionRequestBridgeStatus.INVALID

    allowed = status is ExecutionRequestBridgeStatus.MATERIALIZED and not reasons
    request = None
    if allowed and reservation is not None:
        contract_fp = execution_contract_fingerprint(criteria)
        candidate = ExecutionRequestCandidate(
            request_id=request_id,
            decision_id=decision_id,
            candidate_id=candidate_id,
            reservation_id=reservation.reservation_id,
            account_scope=reservation.account_scope,
            broker=intent.broker.strip(),
            execution_mode=intent.execution_mode.strip().upper(),
            symbol=intent.symbol.strip().upper(),
            direction=_canonical_direction(intent.direction),
            quantity=float(intent.quantity),
            stake=None if intent.stake is None else float(intent.stake),
            currency=intent.currency.strip().upper(),
            order_type=intent.order_type.strip().upper(),
            contract_type=None if intent.contract_type is None else intent.contract_type.strip().upper(),
            requested_at=intent.requested_at,
            expires_at=intent.expires_at,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            decision_fingerprint=decision_fp,
            reservation_fingerprint=reservation.reservation_fingerprint,
            reservation_admission_fingerprint=reservation.reservation_admission_fingerprint,
            source_snapshot_fingerprint=reservation.source_snapshot_fingerprint,
            decision_reservation_binding_fingerprint=reservation.binding_fingerprint,
            execution_contract_fingerprint=contract_fp,
            request_fingerprint="",
            execution_authorized=False,
        )
        request = ExecutionRequestCandidate(**{**asdict(candidate), "request_fingerprint": _request_fingerprint(candidate)})

    normalized = tuple(sorted(set(reasons)))
    return ExecutionRequestBridgeAssessment(
        status=status,
        reasons=normalized,
        request=request,
        decision_id=decision_id or "",
        reservation_id=reservation.reservation_id if reservation is not None else None,
        binding_fingerprint=reservation.binding_fingerprint if reservation is not None else None,
        execution_admission_allowed=bool(allowed and request is not None),
        execution_authorized=False,
    )


def execution_request_bridge_is_not_execution_authorization(
    assessment: ExecutionRequestBridgeAssessment,
) -> bool:
    return assessment.execution_authorized is False
