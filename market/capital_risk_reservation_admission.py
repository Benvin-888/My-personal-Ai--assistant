"""Phase 2.73 controlled capital/risk reservation admission.

Adds a transactional, in-memory admission boundary on top of the 2.72
reservation model.  It prevents two independently proposed reservations from
both consuming the same observed capacity within one ledger instance.

This module does not authorize broker execution and does not persist to a
broker or database.  Persistence/transactional database semantics belong to a
later integration phase.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .capital_risk_reservation import (
    CapitalRiskReservation,
    ReservationCriteria,
    ReservationLedgerSnapshot,
    ReservationLedgerStatus,
    ReservationStatus,
    assess_reservation_capacity,
    make_reservation,
    validate_reservation_request,
    fingerprint,
)


@dataclass(frozen=True)
class ReservationAdmissionRequest:
    reservation_id: str
    created_at: str
    account_scope: str
    strategy_id: str
    strategy_version: str
    capital_amount: float
    risk_amount: float
    expires_at: str | None
    source_decision_id: str | None


@dataclass(frozen=True)
class ReservationAdmissionResult:
    status: ReservationLedgerStatus
    reservation: CapitalRiskReservation | None
    reasons: tuple[str, ...]
    ledger_revision: int
    source_snapshot_fingerprint: str
    admission_fingerprint: str
    execution_authorized: bool = False


class CapitalRiskReservationLedger:
    """Small deterministic reservation ledger with revision-checked admission.

    The caller supplies the point-in-time budget/commitment snapshot.  Once a
    reservation is admitted, subsequent admissions in this ledger instance
    see that reservation and therefore cannot independently oversubscribe the
    same capacity.
    """

    def __init__(self, *, criteria: ReservationCriteria | None = None) -> None:
        self.criteria = criteria or ReservationCriteria()
        self._reservations: dict[str, CapitalRiskReservation] = {}
        self._revision = 0

    @property
    def revision(self) -> int:
        return self._revision

    def reservations(self) -> tuple[CapitalRiskReservation, ...]:
        return tuple(self._reservations.values())

    def snapshot(
        self,
        *,
        observed_at: str,
        account_scope: str,
        capital_budget: float | None,
        risk_budget: float | None,
        committed_capital: float | None,
        committed_risk: float | None,
    ) -> ReservationLedgerSnapshot:
        return ReservationLedgerSnapshot(
            observed_at=observed_at,
            account_scope=account_scope,
            capital_budget=capital_budget,
            risk_budget=risk_budget,
            committed_capital=committed_capital,
            committed_risk=committed_risk,
            reservations=self.reservations(),
            criteria_version=self.criteria.criteria_version,
        )

    def admit(
        self,
        request: ReservationAdmissionRequest,
        *,
        snapshot: ReservationLedgerSnapshot,
        expected_revision: int | None = None,
    ) -> ReservationAdmissionResult:
        source_fp = fingerprint(snapshot)

        if expected_revision is not None and expected_revision != self._revision:
            return self._result(
                ReservationLedgerStatus.INVALID,
                None,
                ("ledger_revision_conflict",),
                source_fp,
            )

        if request.reservation_id in self._reservations:
            return self._result(
                ReservationLedgerStatus.INVALID,
                None,
                ("duplicate_reservation_id",),
                source_fp,
            )

        if snapshot.account_scope != request.account_scope:
            return self._result(
                ReservationLedgerStatus.INVALID,
                None,
                ("reservation_account_scope_mismatch",),
                source_fp,
            )

        candidate = make_reservation(
            reservation_id=request.reservation_id,
            created_at=request.created_at,
            account_scope=request.account_scope,
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            capital_amount=request.capital_amount,
            risk_amount=request.risk_amount,
            expires_at=request.expires_at,
            source_decision_id=request.source_decision_id,
        )
        errors = validate_reservation_request(candidate, snapshot, self.criteria)
        if errors:
            return self._result(ReservationLedgerStatus.INVALID, None, errors, source_fp)

        # Rebuild the point-in-time view with the ledger's current reservations
        # so capacity is checked against all already-admitted reservations.
        current = ReservationLedgerSnapshot(
            observed_at=snapshot.observed_at,
            account_scope=snapshot.account_scope,
            capital_budget=snapshot.capital_budget,
            risk_budget=snapshot.risk_budget,
            committed_capital=snapshot.committed_capital,
            committed_risk=snapshot.committed_risk,
            reservations=self.reservations(),
            criteria_version=snapshot.criteria_version,
        )
        assessment = assess_reservation_capacity(
            current,
            self.criteria,
            request.strategy_id,
            request.strategy_version,
        )
        if assessment.status not in {ReservationLedgerStatus.AVAILABLE, ReservationLedgerStatus.LIMITED}:
            return self._result(assessment.status, None, assessment.reasons, fingerprint(current))

        if assessment.available_capital_after is None or assessment.available_risk_after is None:
            return self._result(
                ReservationLedgerStatus.INSUFFICIENT_DATA,
                None,
                ("capacity_unavailable",),
                fingerprint(current),
            )

        if request.capital_amount > assessment.available_capital_after:
            return self._result(
                ReservationLedgerStatus.LIMITED,
                None,
                ("capital_capacity_exceeded",),
                fingerprint(current),
            )
        if request.risk_amount > assessment.available_risk_after:
            return self._result(
                ReservationLedgerStatus.LIMITED,
                None,
                ("risk_capacity_exceeded",),
                fingerprint(current),
            )

        if self.criteria.max_strategy_reserved_capital is not None:
            if assessment.strategy_reserved_capital + request.capital_amount > self.criteria.max_strategy_reserved_capital:
                return self._result(ReservationLedgerStatus.LIMITED, None, ("strategy_reserved_capital_exceeded",), fingerprint(current))
        if self.criteria.max_strategy_reserved_risk is not None:
            if assessment.strategy_reserved_risk + request.risk_amount > self.criteria.max_strategy_reserved_risk:
                return self._result(ReservationLedgerStatus.LIMITED, None, ("strategy_reserved_risk_exceeded",), fingerprint(current))

        self._reservations[candidate.reservation_id] = candidate
        self._revision += 1
        return self._result(ReservationLedgerStatus.AVAILABLE, candidate, ("reservation_admitted",), fingerprint(current))

    def _result(
        self,
        status: ReservationLedgerStatus,
        reservation: CapitalRiskReservation | None,
        reasons: Iterable[str],
        source_fp: str,
    ) -> ReservationAdmissionResult:
        normalized = tuple(sorted(set(reasons)))
        data = {
            "status": status.value,
            "reservation_id": reservation.reservation_id if reservation else None,
            "reasons": normalized,
            "revision": self._revision,
            "source_snapshot_fingerprint": source_fp,
        }
        return ReservationAdmissionResult(
            status=status,
            reservation=reservation,
            reasons=normalized,
            ledger_revision=self._revision,
            source_snapshot_fingerprint=source_fp,
            admission_fingerprint=fingerprint(data),
            execution_authorized=False,
        )

    def remove_terminal(self, reservation_id: str) -> bool:
        """Remove only a terminal reservation from the in-memory active set.

        Historical state remains the caller's responsibility.  This operation
        is deliberately not an execution or broker action.
        """
        reservation = self._reservations.get(reservation_id)
        if reservation is None or reservation.status is ReservationStatus.RESERVED:
            return False
        del self._reservations[reservation_id]
        self._revision += 1
        return True


def reservation_admission_fingerprint_matches(result: ReservationAdmissionResult) -> bool:
    """Verify the immutable reservation-admission fingerprint."""
    if not isinstance(result, ReservationAdmissionResult):
        return False
    data = {
        "status": result.status.value,
        "reservation_id": result.reservation.reservation_id if result.reservation else None,
        "reasons": tuple(result.reasons),
        "revision": result.ledger_revision,
        "source_snapshot_fingerprint": result.source_snapshot_fingerprint,
    }
    return result.admission_fingerprint == fingerprint(data)


def reservation_admission_is_not_execution_authorization(
    result: ReservationAdmissionResult,
) -> bool:
    return result.execution_authorized is False
