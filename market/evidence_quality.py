"""Deterministic quality assessment for persisted APEX trade evidence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from typing import Any, Iterable, Mapping

from .mongodb_evidence_query import MongoTradeEvidenceQuery

CORE_CONTEXT_FIELDS: tuple[str, ...] = (
    "strategy_id",
    "strategy_version",
    "symbol",
    "timeframe",
    "regime",
    "session",
)
LIFECYCLE_FIELDS: tuple[str, ...] = ("timestamp", "status")
QUALITY_FIELDS: tuple[str, ...] = (
    "trade_id",
    "evidence_fingerprint",
    *CORE_CONTEXT_FIELDS,
    *LIFECYCLE_FIELDS,
)

VALID = "VALID"
INCOMPLETE = "INCOMPLETE"
INVALID = "INVALID"

_INVALID_CODES = frozenset(
    {
        "missing_trade_id",
        "trade_id_mismatch",
        "invalid_fingerprint",
        "invalid_timestamp",
        "invalid_realized_pnl",
    }
)


@dataclass(frozen=True)
class EvidenceQualityAssessment:
    """Quality result for one evidence record; contains no execution authority."""

    trade_id: str
    status: str
    missing_fields: tuple[str, ...]
    issue_codes: tuple[str, ...]
    fingerprint_occurrences: int


@dataclass(frozen=True)
class EvidenceQualitySummary:
    """Aggregate, read-only quality statistics over a query result."""

    total_records: int
    valid_records: int
    incomplete_records: int
    invalid_records: int
    duplicate_fingerprint_records: int
    issue_counts: dict[str, int]
    field_coverage: dict[str, int]
    assessments: tuple[EvidenceQualityAssessment, ...]


def _present(document: Mapping[str, Any], field: str) -> bool:
    value = document.get(field)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _valid_timestamp(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (datetime, date)):
        return True
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    return _finite_number(value)


def _quality_issues(document: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    missing = tuple(field for field in QUALITY_FIELDS if not _present(document, field))
    issues: list[str] = []

    trade_id = str(document.get("trade_id", "")).strip()
    stored_id = document.get("_id")
    if not trade_id:
        issues.append("missing_trade_id")
    if stored_id is not None and str(stored_id).strip() != trade_id:
        issues.append("trade_id_mismatch")

    fingerprint = document.get("evidence_fingerprint")
    if not _present(document, "evidence_fingerprint"):
        issues.append("invalid_fingerprint")

    if "timestamp" in document and document.get("timestamp") is not None and not _valid_timestamp(document.get("timestamp")):
        issues.append("invalid_timestamp")

    if "realized_pnl" in document and document.get("realized_pnl") is not None and not _finite_number(document.get("realized_pnl")):
        issues.append("invalid_realized_pnl")

    return missing, tuple(sorted(set(issues)))


def assess_trade_evidence_record(
    document: Mapping[str, Any],
    fingerprint_occurrences: int = 1,
) -> EvidenceQualityAssessment:
    """Assess one record without changing or inferring trade outcomes."""
    if not isinstance(document, Mapping):
        raise TypeError("document must be a mapping")
    if isinstance(fingerprint_occurrences, bool) or not isinstance(fingerprint_occurrences, int) or fingerprint_occurrences < 1:
        raise ValueError("fingerprint_occurrences must be a positive integer")

    missing, issues = _quality_issues(document)
    hard_invalid = bool(set(issues) & _INVALID_CODES)
    status = INVALID if hard_invalid else INCOMPLETE if missing else VALID
    trade_id = str(document.get("trade_id", "")).strip()
    return EvidenceQualityAssessment(
        trade_id=trade_id,
        status=status,
        missing_fields=missing,
        issue_codes=issues,
        fingerprint_occurrences=fingerprint_occurrences,
    )


def assess_trade_evidence(
    query: MongoTradeEvidenceQuery,
    filters: Mapping[str, Any] | None = None,
) -> EvidenceQualitySummary:
    """Assess persisted evidence deterministically using the read-only query layer.

    Quality is deliberately separate from sample-size sufficiency and profitability.
    A record can be valid yet still be insufficient for statistical conclusions.
    """
    if filters is not None and not isinstance(filters, Mapping):
        raise TypeError("filters must be a mapping or None")

    records = [dict(record) for record in query.find(filters)]
    fingerprint_counts: dict[str, int] = {}
    for record in records:
        fingerprint = str(record.get("evidence_fingerprint", "")).strip()
        if fingerprint:
            fingerprint_counts[fingerprint] = fingerprint_counts.get(fingerprint, 0) + 1

    assessments: list[EvidenceQualityAssessment] = []
    issue_counts: dict[str, int] = {}
    field_coverage: dict[str, int] = {field: 0 for field in QUALITY_FIELDS}
    for record in records:
        for field in QUALITY_FIELDS:
            if _present(record, field):
                field_coverage[field] += 1
        fingerprint = str(record.get("evidence_fingerprint", "")).strip()
        assessment = assess_trade_evidence_record(
            record,
            fingerprint_occurrences=fingerprint_counts.get(fingerprint, 1),
        )
        assessments.append(assessment)
        for code in assessment.issue_codes:
            issue_counts[code] = issue_counts.get(code, 0) + 1

    duplicate_records = sum(
        1 for assessment in assessments if assessment.fingerprint_occurrences > 1
    )
    valid = sum(item.status == VALID for item in assessments)
    incomplete = sum(item.status == INCOMPLETE for item in assessments)
    invalid = sum(item.status == INVALID for item in assessments)

    return EvidenceQualitySummary(
        total_records=len(records),
        valid_records=valid,
        incomplete_records=incomplete,
        invalid_records=invalid,
        duplicate_fingerprint_records=duplicate_records,
        issue_counts=dict(sorted(issue_counts.items())),
        field_coverage=field_coverage,
        assessments=tuple(assessments),
    )
