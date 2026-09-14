"""APEX / BENVIN research cohort and coverage-integrity contracts.

Phase 2.15 - Multi-Market / Multi-Timeframe Research Cohort Integrity

Defines deterministic coverage checks for a pre-assembled set of research
experiment results. It prevents a promotion decision from treating a tiny or
duplicated sample as meaningful cross-market/timeframe evidence. It never
selects candidates, optimizes parameters, fetches data, or executes trades.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Mapping, Sequence

from .experiment import ResearchExperimentResult


class ResearchCohortError(ValueError):
    """Raised when cohort evidence is malformed."""


class CohortStatus(str, Enum):
    PASS = "PASS"
    HOLD = "HOLD"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResearchCohortPolicy:
    """Conservative minimum evidence-coverage requirements."""

    minimum_completed_cases: int = 3
    minimum_distinct_symbols: int = 2
    minimum_distinct_intervals: int = 1
    minimum_cases_per_symbol: int = 1
    minimum_cases_per_interval: int = 1
    minimum_symbol_interval_cells: int = 2
    require_unique_dataset_ids: bool = True
    require_unique_dataset_fingerprints: bool = True
    require_locked_holdout: bool = True

    def __post_init__(self) -> None:
        for name in (
            "minimum_completed_cases", "minimum_distinct_symbols",
            "minimum_distinct_intervals", "minimum_cases_per_symbol",
            "minimum_cases_per_interval", "minimum_symbol_interval_cells",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ResearchCohortError(f"{name} must be a positive integer")
        for name in ("require_unique_dataset_ids", "require_unique_dataset_fingerprints", "require_locked_holdout"):
            if not isinstance(getattr(self, name), bool):
                raise ResearchCohortError(f"{name} must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class CohortCoverageCheck:
    name: str
    passed: bool
    required: bool
    actual: Any
    threshold: Any
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "passed": self.passed, "required": self.required,
            "actual": self.actual, "threshold": self.threshold, "reason": self.reason,
        }


@dataclass(frozen=True)
class ResearchCohortResult:
    """Immutable, auditable assessment of one pre-defined research cohort."""

    cohort_id: str
    status: CohortStatus
    total_cases: int
    completed_cases: int
    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    symbol_case_counts: Mapping[str, int]
    interval_case_counts: Mapping[str, int]
    symbol_interval_cells: tuple[str, ...]
    duplicate_dataset_ids: tuple[str, ...]
    duplicate_dataset_fingerprints: tuple[str, ...]
    checks: tuple[CohortCoverageCheck, ...]
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence_fingerprint: str
    eligible_for_promotion: bool
    policy: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cohort_id": self.cohort_id, "status": self.status.value,
            "total_cases": self.total_cases, "completed_cases": self.completed_cases,
            "symbols": list(self.symbols), "intervals": list(self.intervals),
            "symbol_case_counts": dict(self.symbol_case_counts),
            "interval_case_counts": dict(self.interval_case_counts),
            "symbol_interval_cells": list(self.symbol_interval_cells),
            "duplicate_dataset_ids": list(self.duplicate_dataset_ids),
            "duplicate_dataset_fingerprints": list(self.duplicate_dataset_fingerprints),
            "checks": [x.to_dict() for x in self.checks],
            "failures": list(self.failures), "warnings": list(self.warnings),
            "evidence_fingerprint": self.evidence_fingerprint,
            "eligible_for_promotion": self.eligible_for_promotion,
            "policy": dict(self.policy), "metadata": dict(self.metadata),
        }


class ResearchCohortEngine:
    """Evaluate coverage integrity without choosing or optimizing candidates."""

    def __init__(self, policy: ResearchCohortPolicy | None = None) -> None:
        self.policy = policy or ResearchCohortPolicy()

    def evaluate(
        self,
        cohort_id: str,
        results: Sequence[ResearchExperimentResult],
        *,
        holdout_locked: bool = True,
    ) -> ResearchCohortResult:
        if not isinstance(cohort_id, str) or not cohort_id.strip():
            raise ResearchCohortError("cohort_id must be a non-empty string")
        items = tuple(results)
        if not items:
            raise ResearchCohortError("at least one experiment result is required")
        if any(not isinstance(x, ResearchExperimentResult) for x in items):
            raise ResearchCohortError("all results must be ResearchExperimentResult instances")
        if not isinstance(holdout_locked, bool):
            raise ResearchCohortError("holdout_locked must be a boolean")

        p = self.policy
        completed = tuple(x for x in items if x.performance is not None)
        symbols = tuple(sorted({x.spec.dataset.symbol for x in completed}))
        intervals = tuple(sorted({x.spec.dataset.interval for x in completed}))
        symbol_counts = {s: sum(1 for x in completed if x.spec.dataset.symbol == s) for s in symbols}
        interval_counts = {i: sum(1 for x in completed if x.spec.dataset.interval == i) for i in intervals}
        cells = tuple(sorted({f"{x.spec.dataset.symbol}|{x.spec.dataset.interval}" for x in completed}))

        def duplicates(values: Sequence[str]) -> tuple[str, ...]:
            seen: set[str] = set(); dup: set[str] = set()
            for value in values:
                if value in seen:
                    dup.add(value)
                seen.add(value)
            return tuple(sorted(dup))

        dataset_ids = [x.spec.dataset.dataset_id for x in completed]
        fingerprints = [x.spec.dataset.content_fingerprint for x in completed if x.spec.dataset.content_fingerprint]
        duplicate_ids = duplicates(dataset_ids)
        duplicate_fps = duplicates(fingerprints)
        checks: list[CohortCoverageCheck] = []
        failures: list[str] = []

        def add(name: str, passed: bool, required: bool, actual: Any, threshold: Any, reason: str) -> None:
            checks.append(CohortCoverageCheck(name, bool(passed), bool(required), actual, threshold, reason))
            if required and not passed:
                failures.append(reason)

        add("minimum_completed_cases", len(completed) >= p.minimum_completed_cases, True, len(completed), p.minimum_completed_cases, "too few completed cohort cases")
        add("minimum_distinct_symbols", len(symbols) >= p.minimum_distinct_symbols, True, len(symbols), p.minimum_distinct_symbols, "insufficient distinct-symbol coverage")
        add("minimum_distinct_intervals", len(intervals) >= p.minimum_distinct_intervals, True, len(intervals), p.minimum_distinct_intervals, "insufficient timeframe coverage")
        add("minimum_cases_per_symbol", all(v >= p.minimum_cases_per_symbol for v in symbol_counts.values()), True, dict(symbol_counts), p.minimum_cases_per_symbol, "one or more symbols lack minimum case coverage")
        add("minimum_cases_per_interval", all(v >= p.minimum_cases_per_interval for v in interval_counts.values()), True, dict(interval_counts), p.minimum_cases_per_interval, "one or more intervals lack minimum case coverage")
        add("minimum_symbol_interval_cells", len(cells) >= p.minimum_symbol_interval_cells, True, len(cells), p.minimum_symbol_interval_cells, "insufficient symbol/timeframe coverage cells")
        add("unique_dataset_ids", not duplicate_ids, p.require_unique_dataset_ids, list(duplicate_ids), True, "duplicate dataset IDs detected")
        add("unique_dataset_fingerprints", not duplicate_fps, p.require_unique_dataset_fingerprints, list(duplicate_fps), True, "duplicate dataset fingerprints detected")
        add("holdout_locked", holdout_locked, p.require_locked_holdout, holdout_locked, True, "cohort holdout was not locked")

        status = (CohortStatus.INSUFFICIENT_DATA if len(completed) < p.minimum_completed_cases else (CohortStatus.PASS if not failures else CohortStatus.HOLD))
        payload = {
            "cohort_id": cohort_id, "results": [x.to_dict() for x in items],
            "checks": [x.to_dict() for x in checks], "failures": failures,
        }
        return ResearchCohortResult(
            cohort_id=cohort_id, status=status, total_cases=len(items), completed_cases=len(completed),
            symbols=symbols, intervals=intervals, symbol_case_counts=symbol_counts,
            interval_case_counts=interval_counts, symbol_interval_cells=cells,
            duplicate_dataset_ids=duplicate_ids, duplicate_dataset_fingerprints=duplicate_fps,
            checks=tuple(checks), failures=tuple(failures), warnings=(),
            evidence_fingerprint=_fingerprint(payload), eligible_for_promotion=status == CohortStatus.PASS,
            policy=p.to_dict(), metadata={"candidate_selection": False, "execution_authorization": False, "broker_access": False},
        )


def evaluate_cohort(
    cohort_id: str,
    results: Sequence[ResearchExperimentResult],
    policy: ResearchCohortPolicy | None = None,
    *,
    holdout_locked: bool = True,
) -> ResearchCohortResult:
    return ResearchCohortEngine(policy).evaluate(cohort_id, results, holdout_locked=holdout_locked)
