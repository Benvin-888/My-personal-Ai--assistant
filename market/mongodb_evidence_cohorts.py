"""Deterministic cohort and attribution analytics over APEX trade evidence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .mongodb_evidence_analytics import (
    TradeEvidencePerformanceSummary,
    summarize_trade_evidence,
)
from .mongodb_evidence_query import MongoTradeEvidenceQuery

DEFAULT_COHORT_DIMENSIONS: tuple[str, ...] = (
    "strategy_id",
    "strategy_version",
    "symbol",
    "timeframe",
    "regime",
    "session",
)
MISSING_VALUE = "<missing>"


@dataclass(frozen=True)
class TradeEvidenceCohort:
    """A deterministic cohort key and its read-only performance summary."""

    dimensions: tuple[tuple[str, str], ...]
    summary: TradeEvidencePerformanceSummary


def _validate_dimensions(dimensions: Sequence[str] | None) -> tuple[str, ...]:
    values = DEFAULT_COHORT_DIMENSIONS if dimensions is None else tuple(dimensions)
    if not values:
        raise ValueError("at least one cohort dimension is required")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("cohort dimensions must be non-empty strings")
        name = value.strip()
        if name in normalized:
            raise ValueError("cohort dimensions must be unique")
        normalized.append(name)
    return tuple(normalized)


def _dimension_value(document: Mapping[str, Any], dimension: str) -> str:
    value = document.get(dimension)
    if value is None:
        return MISSING_VALUE
    text = str(value).strip()
    return text if text else MISSING_VALUE


def _cohort_key(document: Mapping[str, Any], dimensions: Sequence[str]) -> tuple[tuple[str, str], ...]:
    return tuple((dimension, _dimension_value(document, dimension)) for dimension in dimensions)


def summarize_trade_evidence_by_cohort(
    query: MongoTradeEvidenceQuery,
    filters: Mapping[str, Any] | None = None,
    dimensions: Sequence[str] | None = None,
) -> tuple[TradeEvidenceCohort, ...]:
    """Group evidence by exact contextual dimensions and summarize each cohort.

    Missing dimensions are represented explicitly as ``<missing>`` rather than
    being silently discarded. Results are returned in deterministic key order.
    """
    if filters is not None and not isinstance(filters, Mapping):
        raise TypeError("filters must be a mapping or None")
    fields = _validate_dimensions(dimensions)
    records = query.find(filters)

    grouped: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] = {}
    for record in records:
        key = _cohort_key(record, fields)
        grouped.setdefault(key, []).append(dict(record))

    cohorts: list[TradeEvidenceCohort] = []
    for key in sorted(grouped):
        cohort_query = _StaticEvidenceQuery(grouped[key])
        cohorts.append(
            TradeEvidenceCohort(
                dimensions=key,
                summary=summarize_trade_evidence(cohort_query),
            )
        )
    return tuple(cohorts)


def summarize_trade_evidence_by_dimension(
    query: MongoTradeEvidenceQuery,
    dimension: str,
    filters: Mapping[str, Any] | None = None,
) -> dict[str, TradeEvidencePerformanceSummary]:
    """Attribute performance to one evidence field at a time."""
    cohorts = summarize_trade_evidence_by_cohort(
        query,
        filters=filters,
        dimensions=(dimension,),
    )
    return {cohort.dimensions[0][1]: cohort.summary for cohort in cohorts}


class _StaticEvidenceQuery:
    """Minimal read-only query adapter used to reuse the 2.49 analytics contract."""

    def __init__(self, records: Iterable[Mapping[str, Any]]) -> None:
        self._records = [dict(record) for record in records]

    def find(self, filters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        query = dict(filters or {})
        return [
            dict(record)
            for record in self._records
            if all(record.get(key) == value for key, value in query.items())
        ]
