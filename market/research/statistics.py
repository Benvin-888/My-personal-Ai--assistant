"""APEX / BENVIN statistical research safeguards.

Phase 2.13 - Statistical Validation & Selection-Bias Controls

This module provides deterministic, dependency-free statistical utilities and
selection-audit contracts for research evidence. It does not optimize
strategies, fetch data, access brokers, or authorize execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import random
from statistics import mean, median
from typing import Any, Mapping, Sequence


class ResearchStatisticsError(ValueError):
    """Raised when a statistical research input is invalid."""


class StatisticalStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ResearchStatisticsError(f"{name} must be finite numeric")
    return float(value)


def _values(values: Sequence[float]) -> tuple[float, ...]:
    items = tuple(_finite(v, "values") for v in values)
    if not items:
        raise ResearchStatisticsError("at least one value is required")
    return items


@dataclass(frozen=True)
class BootstrapResult:
    """Deterministic bootstrap confidence interval for a sample mean."""

    sample_size: int
    resamples: int
    seed: int
    confidence_level: float
    sample_mean: float
    bootstrap_mean: float
    lower_bound: float
    upper_bound: float
    positive_fraction: float
    evidence_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size, "resamples": self.resamples,
            "seed": self.seed, "confidence_level": self.confidence_level,
            "sample_mean": self.sample_mean, "bootstrap_mean": self.bootstrap_mean,
            "lower_bound": self.lower_bound, "upper_bound": self.upper_bound,
            "positive_fraction": self.positive_fraction,
            "evidence_fingerprint": self.evidence_fingerprint,
        }


def bootstrap_mean(values: Sequence[float], *, resamples: int = 5000, seed: int = 0, confidence_level: float = 0.95) -> BootstrapResult:
    items = _values(values)
    if resamples < 100:
        raise ResearchStatisticsError("resamples must be at least 100")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ResearchStatisticsError("seed must be an integer")
    level = _finite(confidence_level, "confidence_level")
    if not 0.0 < level < 1.0:
        raise ResearchStatisticsError("confidence_level must be between 0 and 1")
    rng = random.Random(seed)
    samples = [mean(rng.choice(items) for _ in items) for _ in range(resamples)]
    samples.sort()
    alpha = (1.0 - level) / 2.0

    def quantile(q: float) -> float:
        pos = q * (len(samples) - 1)
        lo, hi = math.floor(pos), math.ceil(pos)
        if lo == hi:
            return samples[lo]
        return samples[lo] + (samples[hi] - samples[lo]) * (pos - lo)

    result_data = {
        "sample_size": len(items), "resamples": resamples, "seed": seed,
        "confidence_level": level, "sample_mean": mean(items),
        "bootstrap_mean": mean(samples), "lower_bound": quantile(alpha),
        "upper_bound": quantile(1.0 - alpha),
        "positive_fraction": sum(x > 0 for x in samples) / len(samples),
    }
    return BootstrapResult(**result_data, evidence_fingerprint=_fingerprint(result_data))


@dataclass(frozen=True)
class MultipleTestingResult:
    """Bonferroni and Benjamini-Hochberg adjusted p-values for supplied tests."""

    test_count: int
    alpha: float
    raw_p_values: tuple[float, ...]
    bonferroni_p_values: tuple[float, ...]
    bh_p_values: tuple[float, ...]
    bonferroni_rejections: tuple[bool, ...]
    bh_rejections: tuple[bool, ...]
    evidence_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_count": self.test_count, "alpha": self.alpha,
            "raw_p_values": list(self.raw_p_values),
            "bonferroni_p_values": list(self.bonferroni_p_values),
            "bh_p_values": list(self.bh_p_values),
            "bonferroni_rejections": list(self.bonferroni_rejections),
            "bh_rejections": list(self.bh_rejections),
            "evidence_fingerprint": self.evidence_fingerprint,
        }


def multiple_testing(p_values: Sequence[float], *, alpha: float = 0.05) -> MultipleTestingResult:
    raw = tuple(_finite(p, "p_values") for p in p_values)
    if not raw:
        raise ResearchStatisticsError("at least one p-value is required")
    if any(p < 0.0 or p > 1.0 for p in raw):
        raise ResearchStatisticsError("p-values must be between 0 and 1")
    a = _finite(alpha, "alpha")
    if not 0.0 < a < 1.0:
        raise ResearchStatisticsError("alpha must be between 0 and 1")
    n = len(raw)
    bonf = tuple(min(1.0, p * n) for p in raw)
    order = sorted(range(n), key=lambda i: (raw[i], i))
    bh = [0.0] * n
    running = 1.0
    for rank, idx in reversed(list(enumerate(order, start=1))):
        adjusted = min(running, raw[idx] * n / rank)
        bh[idx] = adjusted
        running = adjusted
    data = {
        "test_count": n, "alpha": a, "raw_p_values": raw,
        "bonferroni_p_values": bonf, "bh_p_values": tuple(bh),
        "bonferroni_rejections": tuple(p <= a for p in bonf),
        "bh_rejections": tuple(p <= a for p in bh),
    }
    return MultipleTestingResult(**data, evidence_fingerprint=_fingerprint(data))


class SelectionAuditStatus(str, Enum):
    CONTROLLED = "CONTROLLED"
    UNCONTROLLED = "UNCONTROLLED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class SelectionBiasAudit:
    """Audit trail describing how a research candidate was selected."""

    candidate_count: int
    selection_metric: str
    selection_direction: str
    holdout_locked_before_selection: bool
    independent_confirmation: bool
    selected_candidate_id: str | None = None
    status: SelectionAuditStatus = SelectionAuditStatus.CONTROLLED
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.candidate_count, bool) or not isinstance(self.candidate_count, int) or self.candidate_count < 1:
            raise ResearchStatisticsError("candidate_count must be a positive integer")
        if not isinstance(self.selection_metric, str) or not self.selection_metric.strip():
            raise ResearchStatisticsError("selection_metric must be non-empty")
        if self.selection_direction not in {"MAXIMIZE", "MINIMIZE"}:
            raise ResearchStatisticsError("selection_direction must be MAXIMIZE or MINIMIZE")
        if self.status == SelectionAuditStatus.CONTROLLED and not self.holdout_locked_before_selection:
            raise ResearchStatisticsError("CONTROLLED selection requires holdout_locked_before_selection")

    @property
    def effective_candidate_burden(self) -> float:
        return math.log2(self.candidate_count + 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "selection_metric": self.selection_metric,
            "selection_direction": self.selection_direction,
            "holdout_locked_before_selection": self.holdout_locked_before_selection,
            "independent_confirmation": self.independent_confirmation,
            "selected_candidate_id": self.selected_candidate_id,
            "status": self.status.value,
            "effective_candidate_burden": self.effective_candidate_burden,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StatisticalValidationPolicy:
    """Conservative evidence policy; thresholds are research gates, not profit guarantees."""

    minimum_sample_size: int = 30
    minimum_positive_bootstrap_fraction: float = 0.55
    confidence_level: float = 0.95
    require_holdout_locked_selection: bool = True
    require_independent_confirmation: bool = False

    def __post_init__(self) -> None:
        if self.minimum_sample_size < 1:
            raise ResearchStatisticsError("minimum_sample_size must be positive")
        if not 0.0 <= self.minimum_positive_bootstrap_fraction <= 1.0:
            raise ResearchStatisticsError("minimum_positive_bootstrap_fraction must be between 0 and 1")
        if not 0.0 < self.confidence_level < 1.0:
            raise ResearchStatisticsError("confidence_level must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_sample_size": self.minimum_sample_size,
            "minimum_positive_bootstrap_fraction": self.minimum_positive_bootstrap_fraction,
            "confidence_level": self.confidence_level,
            "require_holdout_locked_selection": self.require_holdout_locked_selection,
            "require_independent_confirmation": self.require_independent_confirmation,
        }


@dataclass(frozen=True)
class StatisticalValidationResult:
    """Immutable evidence result; it never authorizes trading."""

    status: StatisticalStatus
    sample_size: int
    bootstrap: BootstrapResult | None
    selection_audit: SelectionBiasAudit | None
    checks: tuple[Mapping[str, Any], ...]
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    eligible_for_research_promotion: bool
    evidence_fingerprint: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value, "sample_size": self.sample_size,
            "bootstrap": self.bootstrap.to_dict() if self.bootstrap else None,
            "selection_audit": self.selection_audit.to_dict() if self.selection_audit else None,
            "checks": [dict(x) for x in self.checks],
            "failures": list(self.failures), "warnings": list(self.warnings),
            "eligible_for_research_promotion": self.eligible_for_research_promotion,
            "evidence_fingerprint": self.evidence_fingerprint,
            "metadata": dict(self.metadata),
        }


def validate_statistics(values: Sequence[float], *, policy: StatisticalValidationPolicy | None = None, selection_audit: SelectionBiasAudit | None = None, resamples: int = 5000, seed: int = 0) -> StatisticalValidationResult:
    policy = policy or StatisticalValidationPolicy()
    items = _values(values)
    checks: list[Mapping[str, Any]] = []
    failures: list[str] = []
    warnings: list[str] = []
    checks.append({"name": "minimum_sample_size", "passed": len(items) >= policy.minimum_sample_size, "actual": len(items), "required": policy.minimum_sample_size})
    if len(items) < policy.minimum_sample_size:
        failures.append("sample size is below the minimum research threshold")
    bootstrap = bootstrap_mean(items, resamples=resamples, seed=seed, confidence_level=policy.confidence_level)
    positive_ok = bootstrap.positive_fraction >= policy.minimum_positive_bootstrap_fraction
    checks.append({"name": "bootstrap_positive_fraction", "passed": positive_ok, "actual": bootstrap.positive_fraction, "required": policy.minimum_positive_bootstrap_fraction})
    if not positive_ok:
        failures.append("bootstrap positive fraction is below the research threshold")
    if selection_audit is None:
        if policy.require_holdout_locked_selection:
            failures.append("selection-bias audit is required")
        else:
            warnings.append("selection-bias audit was not supplied")
    else:
        holdout_ok = (not policy.require_holdout_locked_selection) or selection_audit.holdout_locked_before_selection
        checks.append({"name": "holdout_locked_before_selection", "passed": holdout_ok})
        if not holdout_ok:
            failures.append("holdout was not locked before candidate selection")
        if policy.require_independent_confirmation and not selection_audit.independent_confirmation:
            failures.append("independent confirmation is required")
        elif not selection_audit.independent_confirmation:
            warnings.append("independent confirmation was not supplied")
        warnings.extend(selection_audit.warnings)
    status = StatisticalStatus.PASS if not failures else StatisticalStatus.FAIL
    if not items:
        status = StatisticalStatus.INSUFFICIENT_DATA
    data = {
        "status": status.value, "sample_size": len(items),
        "bootstrap": bootstrap.to_dict(),
        "selection_audit": selection_audit.to_dict() if selection_audit else None,
        "checks": checks, "failures": failures, "warnings": warnings,
        "eligible_for_research_promotion": status == StatisticalStatus.PASS,
    }
    return StatisticalValidationResult(
        status=status, sample_size=len(items), bootstrap=bootstrap, selection_audit=selection_audit,
        checks=tuple(checks), failures=tuple(failures), warnings=tuple(warnings),
        eligible_for_research_promotion=status == StatisticalStatus.PASS,
        evidence_fingerprint=_fingerprint(data),
    )
