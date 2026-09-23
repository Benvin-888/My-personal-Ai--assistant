"""Phase 2.58 regime and Forex-session stability analysis.

This module measures how recorded economic evidence behaves across declared
market regimes and trading sessions. It is descriptive validation only: it
never selects a preferred regime/session, optimizes parameters, predicts
future performance, or grants execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping

from .economic_performance import assess_economic_record

MISSING = "<missing>"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
INVALID_EVIDENCE = "INVALID_EVIDENCE"
DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
CONCENTRATED = "CONCENTRATED"
UNSTABLE = "UNSTABLE"
STABLE = "STABLE"


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _label(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    if value is None:
        return MISSING
    text = str(value).strip()
    return text or MISSING


def _risk(document: Mapping[str, Any]) -> float | None:
    for field in ("risk_amount", "max_risk", "initial_risk"):
        value = _finite(document.get(field))
        if value is not None and value >= 0:
            return value
    return None


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RegimeSessionStabilityCriteria:
    """Conservative thresholds for descriptive stability assessment."""

    min_records_per_cohort: int = 10
    min_observed_cohorts: int = 2
    min_profitable_cohort_fraction: float = 0.67
    require_cost_coverage: bool = True
    require_risk_coverage: bool = True
    require_evidence_class: bool = True

    def __post_init__(self) -> None:
        for field in ("min_records_per_cohort", "min_observed_cohorts"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{field} must be a positive integer")
        if not 0 < self.min_profitable_cohort_fraction <= 1:
            raise ValueError("min_profitable_cohort_fraction must be between 0 and 1")


@dataclass(frozen=True)
class RegimeSessionCohort:
    """Economic evidence summary for one regime/session cohort."""

    regime: str
    session: str
    total_records: int
    realized_pnl_records: int
    total_realized_pnl: float | None
    expectancy: float | None
    win_rate: float | None
    profit_factor: float | None
    fully_costed_records: int
    cost_coverage_rate: float | None
    risk_covered_records: int
    risk_coverage_rate: float | None
    total_risk: float | None
    pnl_to_risk: float | None
    profitable: bool | None
    sufficient_sample: bool
    complete_costs: bool
    complete_risk: bool
    evidence_class: str


@dataclass(frozen=True)
class StabilityDimensionSummary:
    """Aggregate stability view for regime-only or session-only cohorts."""

    dimension: str
    cohort_count: int
    eligible_cohort_count: int
    profitable_cohort_count: int
    profitable_cohort_fraction: float | None
    complete_cost_cohorts: int
    complete_risk_cohorts: int
    missing_label_cohorts: int
    sufficient_sample: bool
    complete_costs: bool
    complete_risk: bool
    status: str
    cohorts: tuple[RegimeSessionCohort, ...]


@dataclass(frozen=True)
class RegimeSessionStabilitySummary:
    """Complete deterministic regime, session and regime×session analysis."""

    status: str
    evidence_class: str
    total_records: int
    usable_records: int
    regime: StabilityDimensionSummary
    session: StabilityDimensionSummary
    matrix: tuple[RegimeSessionCohort, ...]
    limitations: tuple[str, ...]
    evidence_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "evidence_class": self.evidence_class,
            "total_records": self.total_records,
            "usable_records": self.usable_records,
            "regime": self.regime.__dict__,
            "session": self.session.__dict__,
            "matrix": [item.__dict__ for item in self.matrix],
            "limitations": list(self.limitations),
            "evidence_fingerprint": self.evidence_fingerprint,
        }


def _cohort(records: list[Mapping[str, Any]], regime: str, session: str, criteria: RegimeSessionStabilityCriteria) -> RegimeSessionCohort:
    assessments = [assess_economic_record(record) for record in records]
    realized = [item.realized_pnl for item in assessments if item.realized_pnl is not None]
    costs = [item for item in assessments if item.explicit_costs is not None]
    risks = [_risk(record) for record in records]
    risks = [value for value in risks if value is not None]
    total_pnl = sum(realized) if realized else None
    winners = sum(value > 0 for value in realized)
    losers = sum(value < 0 for value in realized)
    gross_profit = sum(value for value in realized if value > 0) if realized else None
    gross_loss = sum(value for value in realized if value < 0) if realized else None
    profit_factor = (
        gross_profit / abs(gross_loss)
        if gross_profit is not None and gross_loss is not None and gross_loss < 0
        else None
    )
    total_risk = sum(risks) if risks else None
    pnl_to_risk = total_pnl / total_risk if total_pnl is not None and total_risk and total_risk > 0 else None
    evidence_classes = {_label(record, "evidence_class") for record in records}
    evidence_class = next(iter(evidence_classes)) if len(evidence_classes) == 1 else "<mixed>"
    return RegimeSessionCohort(
        regime=regime,
        session=session,
        total_records=len(records),
        realized_pnl_records=len(realized),
        total_realized_pnl=total_pnl,
        expectancy=total_pnl / len(realized) if realized else None,
        win_rate=winners / len(realized) if realized else None,
        profit_factor=profit_factor,
        fully_costed_records=len(costs),
        cost_coverage_rate=len(costs) / len(records) if records else None,
        risk_covered_records=len(risks),
        risk_coverage_rate=len(risks) / len(records) if records else None,
        total_risk=total_risk,
        pnl_to_risk=pnl_to_risk,
        profitable=total_pnl > 0 if total_pnl is not None else None,
        sufficient_sample=len(records) >= criteria.min_records_per_cohort,
        complete_costs=(not criteria.require_cost_coverage) or len(costs) == len(records),
        complete_risk=(not criteria.require_risk_coverage) or len(risks) == len(records),
        evidence_class=evidence_class,
    )


def _dimension_summary(
    dimension: str,
    cohorts: tuple[RegimeSessionCohort, ...],
    criteria: RegimeSessionStabilityCriteria,
) -> StabilityDimensionSummary:
    missing = sum(1 for item in cohorts if (item.regime if dimension == "regime" else item.session) == MISSING)
    eligible = tuple(
        item for item in cohorts
        if (item.regime if dimension == "regime" else item.session) != MISSING
    )
    profitable = sum(item.profitable is True for item in eligible)
    fraction = profitable / len(eligible) if eligible else None
    sufficient = len(eligible) >= criteria.min_observed_cohorts and all(item.sufficient_sample for item in eligible)
    complete_costs = all(item.complete_costs for item in eligible) if eligible else False
    complete_risk = all(item.complete_risk for item in eligible) if eligible else False
    if not eligible:
        status = INSUFFICIENT_DATA
    elif not sufficient or not complete_costs or not complete_risk:
        status = DESCRIPTIVE_ONLY
    elif fraction is not None and fraction >= criteria.min_profitable_cohort_fraction:
        status = STABLE
    else:
        status = UNSTABLE
    if missing and status == STABLE:
        status = DESCRIPTIVE_ONLY
    return StabilityDimensionSummary(
        dimension=dimension,
        cohort_count=len(cohorts),
        eligible_cohort_count=len(eligible),
        profitable_cohort_count=profitable,
        profitable_cohort_fraction=fraction,
        complete_cost_cohorts=sum(item.complete_costs for item in eligible),
        complete_risk_cohorts=sum(item.complete_risk for item in eligible),
        missing_label_cohorts=missing,
        sufficient_sample=sufficient,
        complete_costs=complete_costs,
        complete_risk=complete_risk,
        status=status,
        cohorts=cohorts,
    )


def evaluate_regime_session_stability(
    records: Iterable[Mapping[str, Any]],
    *,
    criteria: RegimeSessionStabilityCriteria | None = None,
    evidence_class: str | None = None,
) -> RegimeSessionStabilitySummary:
    """Evaluate regime, session and regime×session stability without selection."""
    c = criteria or RegimeSessionStabilityCriteria()
    if not isinstance(c, RegimeSessionStabilityCriteria):
        raise TypeError("criteria must be RegimeSessionStabilityCriteria")
    supplied = [dict(record) for record in records if isinstance(record, Mapping)]
    if evidence_class is not None and (not isinstance(evidence_class, str) or not evidence_class.strip()):
        raise ValueError("evidence_class must be a non-empty string or None")
    requested_class = evidence_class.strip() if evidence_class else None
    classes = {_label(record, "evidence_class") for record in supplied}
    limitations: list[str] = []
    if requested_class is not None:
        supplied = [record for record in supplied if _label(record, "evidence_class") == requested_class]
        classes = {_label(record, "evidence_class") for record in supplied}
    if not supplied:
        fingerprint = _fingerprint([])
        empty = StabilityDimensionSummary("regime", 0, 0, 0, None, 0, 0, 0, False, False, False, INSUFFICIENT_DATA, ())
        empty_session = StabilityDimensionSummary("session", 0, 0, 0, None, 0, 0, 0, False, False, False, INSUFFICIENT_DATA, ())
        return RegimeSessionStabilitySummary(INSUFFICIENT_DATA, requested_class or MISSING, 0, 0, empty, empty_session, (), ("no_evidence",), fingerprint)
    if len(classes) > 1:
        limitations.append("mixed_evidence_classes_not_combined")
    if classes == {MISSING} and c.require_evidence_class:
        limitations.append("evidence_class_missing")
    if len(classes) > 1 or (classes == {MISSING} and c.require_evidence_class):
        invalid = StabilityDimensionSummary("regime", 0, 0, 0, None, 0, 0, 0, False, False, False, INVALID_EVIDENCE, ())
        invalid_session = StabilityDimensionSummary("session", 0, 0, 0, None, 0, 0, 0, False, False, False, INVALID_EVIDENCE, ())
        return RegimeSessionStabilitySummary(INVALID_EVIDENCE, "<mixed>" if len(classes) > 1 else MISSING, len(supplied), 0, invalid, invalid_session, (), tuple(limitations), _fingerprint(supplied))
    evidence_label = next(iter(classes))
    if any(_label(record, "regime") == MISSING for record in supplied):
        limitations.append("regime_label_missing")
    if any(_label(record, "session") == MISSING for record in supplied):
        limitations.append("session_label_missing")
    regime_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    session_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    matrix_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for record in supplied:
        regime = _label(record, "regime")
        session = _label(record, "session")
        regime_groups.setdefault((regime, MISSING), []).append(record)
        session_groups.setdefault((MISSING, session), []).append(record)
        matrix_groups.setdefault((regime, session), []).append(record)
    regime_cohorts = tuple(_cohort(group, key[0], MISSING, c) for key, group in sorted(regime_groups.items()))
    session_cohorts = tuple(_cohort(group, MISSING, key[1], c) for key, group in sorted(session_groups.items()))
    matrix = tuple(_cohort(group, key[0], key[1], c) for key, group in sorted(matrix_groups.items()))
    regime_summary = _dimension_summary("regime", regime_cohorts, c)
    session_summary = _dimension_summary("session", session_cohorts, c)
    eligible_matrix = tuple(item for item in matrix if item.regime != MISSING and item.session != MISSING)
    matrix_sufficient = len(eligible_matrix) >= c.min_observed_cohorts and all(item.sufficient_sample for item in eligible_matrix)
    matrix_complete_costs = bool(eligible_matrix) and all(item.complete_costs for item in eligible_matrix)
    matrix_complete_risk = bool(eligible_matrix) and all(item.complete_risk for item in eligible_matrix)
    if regime_summary.status == STABLE and session_summary.status == STABLE and matrix_sufficient and matrix_complete_costs and matrix_complete_risk and not limitations:
        status = STABLE
    elif regime_summary.status == INSUFFICIENT_DATA or session_summary.status == INSUFFICIENT_DATA:
        status = INSUFFICIENT_DATA
    elif "regime_label_missing" in limitations or "session_label_missing" in limitations:
        status = DESCRIPTIVE_ONLY
    elif regime_summary.status == UNSTABLE or session_summary.status == UNSTABLE:
        status = UNSTABLE
    elif (regime_summary.eligible_cohort_count > 1 or session_summary.eligible_cohort_count > 1) and (
        regime_summary.profitable_cohort_fraction is not None and regime_summary.profitable_cohort_fraction < c.min_profitable_cohort_fraction
        or session_summary.profitable_cohort_fraction is not None and session_summary.profitable_cohort_fraction < c.min_profitable_cohort_fraction
    ):
        status = CONCENTRATED
    else:
        status = DESCRIPTIVE_ONLY
    if not matrix_sufficient:
        limitations.append("regime_session_matrix_sample_incomplete")
    if not matrix_complete_costs and c.require_cost_coverage:
        limitations.append("regime_session_matrix_cost_coverage_incomplete")
    if not matrix_complete_risk and c.require_risk_coverage:
        limitations.append("regime_session_matrix_risk_coverage_incomplete")
    payload = {"evidence_class": evidence_label, "records": sorted(supplied, key=lambda record: (str(record.get("trade_id", "")), json.dumps(record, sort_keys=True, default=str))), "regime": [item.__dict__ for item in regime_cohorts], "session": [item.__dict__ for item in session_cohorts], "matrix": [item.__dict__ for item in matrix], "criteria": c.__dict__}
    return RegimeSessionStabilitySummary(status, evidence_label, len(supplied), sum(item.realized_pnl_records for item in matrix), regime_summary, session_summary, matrix, tuple(dict.fromkeys(limitations)), _fingerprint(payload))


def summarize_trade_evidence_regime_session(
    query: Any,
    filters: Mapping[str, Any] | None = None,
    *,
    criteria: RegimeSessionStabilityCriteria | None = None,
    evidence_class: str | None = None,
) -> RegimeSessionStabilitySummary:
    """Read-only query adapter for MongoDB trade evidence."""
    if filters is not None and not isinstance(filters, Mapping):
        raise TypeError("filters must be a mapping or None")
    if not hasattr(query, "find"):
        raise TypeError("query must provide find(filters)")
    return evaluate_regime_session_stability(query.find(filters), criteria=criteria, evidence_class=evidence_class)
