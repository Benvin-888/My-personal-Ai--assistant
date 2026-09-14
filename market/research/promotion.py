"""APEX / BENVIN research evidence and promotion pipeline.

Phase 2.14 - Research Evidence & Promotion Pipeline

Combines the independent evidence produced by Phases 2.10-2.13 into one
immutable, deterministic promotion decision. It does not optimize candidates,
select winners from raw results, access brokers, place orders, or authorize
execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from .experiment import CrossMarketResearchSummary, ResearchExperimentResult
from .robustness import RobustnessScenarioSummary, TimeWalkForwardResult
from .statistics import StatisticalValidationResult, StatisticalStatus
from .validation import ResearchValidationResult, ValidationStatus


class ResearchPromotionError(ValueError):
    """Raised when promotion evidence is malformed."""


class PromotionStatus(str, Enum):
    PROMOTE_PAPER = "PROMOTE_PAPER"
    HOLD = "HOLD"
    REJECT = "REJECT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ResearchPromotionError(f"{name} must be finite numeric")
    return float(value)


@dataclass(frozen=True)
class PromotionEvidence:
    """Complete evidence bundle for one research candidate/cohort."""

    candidate_id: str
    validation: ResearchValidationResult
    experiments: CrossMarketResearchSummary
    statistical: StatisticalValidationResult
    temporal: TimeWalkForwardResult | None = None
    scenarios: RobustnessScenarioSummary | None = None
    holdout_locked: bool = True
    independent_confirmation: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ResearchPromotionError("candidate_id must be a non-empty string")
        if not isinstance(self.validation, ResearchValidationResult):
            raise ResearchPromotionError("validation must be ResearchValidationResult")
        if not isinstance(self.experiments, CrossMarketResearchSummary):
            raise ResearchPromotionError("experiments must be CrossMarketResearchSummary")
        if not isinstance(self.statistical, StatisticalValidationResult):
            raise ResearchPromotionError("statistical must be StatisticalValidationResult")
        if not isinstance(self.holdout_locked, bool) or not isinstance(self.independent_confirmation, bool):
            raise ResearchPromotionError("holdout_locked and independent_confirmation must be booleans")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "validation": self.validation.to_dict(),
            "experiments": self.experiments.to_dict(),
            "statistical": self.statistical.to_dict(),
            "temporal": self.temporal.to_dict() if self.temporal else None,
            "scenarios": self.scenarios.to_dict() if self.scenarios else None,
            "holdout_locked": self.holdout_locked,
            "independent_confirmation": self.independent_confirmation,
            "metadata": dict(self.metadata),
        }

    @property
    def evidence_fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


@dataclass(frozen=True)
class ResearchPromotionPolicy:
    """Conservative evidence requirements for promotion to paper research."""

    minimum_completed_experiments: int = 3
    minimum_distinct_symbols: int = 2
    minimum_distinct_intervals: int = 1
    minimum_profitable_case_fraction: float = 0.67
    minimum_validation_pass_fraction: float = 0.67
    minimum_temporal_windows: int = 3
    minimum_profitable_temporal_fraction: float = 0.67
    require_temporal_robustness: bool = True
    minimum_completed_scenarios: int = 3
    minimum_profitable_scenario_fraction: float = 0.67
    require_scenario_robustness: bool = True
    require_holdout_locked: bool = True
    require_independent_confirmation: bool = False

    def __post_init__(self) -> None:
        for name in ("minimum_completed_experiments", "minimum_distinct_symbols", "minimum_distinct_intervals", "minimum_temporal_windows", "minimum_completed_scenarios"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ResearchPromotionError(f"{name} must be a positive integer")
        for name in ("minimum_profitable_case_fraction", "minimum_validation_pass_fraction", "minimum_profitable_temporal_fraction", "minimum_profitable_scenario_fraction"):
            value = _finite(getattr(self, name), name)
            if not 0.0 <= value <= 1.0:
                raise ResearchPromotionError(f"{name} must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass(frozen=True)
class PromotionCheck:
    """One auditable promotion-gate check."""

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
class ResearchPromotionResult:
    """Immutable final research promotion decision; never execution authorization."""

    status: PromotionStatus
    eligible_for_paper: bool
    eligible_for_demo: bool
    checks: tuple[PromotionCheck, ...]
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence_fingerprint: str
    policy: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "eligible_for_paper": self.eligible_for_paper,
            "eligible_for_demo": self.eligible_for_demo,
            "checks": [x.to_dict() for x in self.checks],
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "evidence_fingerprint": self.evidence_fingerprint,
            "policy": dict(self.policy),
            "metadata": dict(self.metadata),
        }


class ResearchPromotionEngine:
    """Evaluate a pre-assembled evidence bundle without selecting candidates."""

    def __init__(self, policy: ResearchPromotionPolicy | None = None) -> None:
        self.policy = policy or ResearchPromotionPolicy()

    def evaluate(self, evidence: PromotionEvidence) -> ResearchPromotionResult:
        if not isinstance(evidence, PromotionEvidence):
            raise ResearchPromotionError("evidence must be PromotionEvidence")
        p = self.policy
        checks: list[PromotionCheck] = []
        failures: list[str] = []
        warnings: list[str] = []

        def add(name: str, passed: bool, required: bool, actual: Any, threshold: Any, reason: str) -> None:
            check = PromotionCheck(name, bool(passed), bool(required), actual, threshold, reason)
            checks.append(check)
            if required and not passed:
                failures.append(reason)

        exp = evidence.experiments
        add("minimum_completed_experiments", exp.completed_cases >= p.minimum_completed_experiments, True,
            exp.completed_cases, p.minimum_completed_experiments, "too few completed experiments")
        add("minimum_distinct_symbols", len(exp.symbols) >= p.minimum_distinct_symbols, True,
            len(exp.symbols), p.minimum_distinct_symbols, "insufficient cross-symbol coverage")
        add("minimum_distinct_intervals", len(exp.intervals) >= p.minimum_distinct_intervals, True,
            len(exp.intervals), p.minimum_distinct_intervals, "insufficient timeframe coverage")
        add("profitable_case_fraction", exp.profitable_case_fraction >= p.minimum_profitable_case_fraction, True,
            exp.profitable_case_fraction, p.minimum_profitable_case_fraction, "profitable case breadth is below threshold")
        add("validation_pass_fraction", exp.validation_pass_fraction >= p.minimum_validation_pass_fraction, True,
            exp.validation_pass_fraction, p.minimum_validation_pass_fraction, "research-validation pass fraction is below threshold")

        add("phase_2_10_validation", evidence.validation.status == ValidationStatus.PASS and evidence.validation.eligible_for_paper, True,
            evidence.validation.status.value, ValidationStatus.PASS.value, "Phase 2.10 research validation did not pass")
        add("phase_2_13_statistics", evidence.statistical.status == StatisticalStatus.PASS and evidence.statistical.eligible_for_research_promotion, True,
            evidence.statistical.status.value, StatisticalStatus.PASS.value, "Phase 2.13 statistical validation did not pass")
        add("holdout_locked", evidence.holdout_locked, p.require_holdout_locked,
            evidence.holdout_locked, True, "holdout was not locked before selection")
        add("independent_confirmation", evidence.independent_confirmation, p.require_independent_confirmation,
            evidence.independent_confirmation, True, "independent confirmation is required")

        if evidence.temporal is None:
            add("temporal_robustness_present", False, p.require_temporal_robustness, None, True, "temporal robustness evidence is missing")
        else:
            add("temporal_window_count", len(evidence.temporal.windows) >= p.minimum_temporal_windows, p.require_temporal_robustness,
                len(evidence.temporal.windows), p.minimum_temporal_windows, "too few temporal walk-forward windows")
            add("temporal_profitable_fraction", evidence.temporal.profitable_test_window_fraction >= p.minimum_profitable_temporal_fraction,
                p.require_temporal_robustness, evidence.temporal.profitable_test_window_fraction,
                p.minimum_profitable_temporal_fraction, "temporal walk-forward profitability breadth is below threshold")

        if evidence.scenarios is None:
            add("scenario_robustness_present", False, p.require_scenario_robustness, None, True, "execution/cost scenario evidence is missing")
        else:
            completed = evidence.scenarios.completed_scenarios
            add("scenario_count", completed >= p.minimum_completed_scenarios, p.require_scenario_robustness,
                completed, p.minimum_completed_scenarios, "too few completed robustness scenarios")
            add("scenario_profitable_fraction", evidence.scenarios.profitable_fraction >= p.minimum_profitable_scenario_fraction,
                p.require_scenario_robustness, evidence.scenarios.profitable_fraction,
                p.minimum_profitable_scenario_fraction, "robustness scenario profitability breadth is below threshold")

        if evidence.validation.warnings:
            warnings.extend(evidence.validation.warnings)
        if evidence.statistical.warnings:
            warnings.extend(evidence.statistical.warnings)

        # Promotion is intentionally all-or-nothing for required evidence. A
        # failed gate is a HOLD/REJECT decision, never an automatic execution path.
        if failures:
            status = PromotionStatus.HOLD if exp.completed_cases > 0 else PromotionStatus.INSUFFICIENT_DATA
        else:
            status = PromotionStatus.PROMOTE_PAPER

        eligible_paper = status == PromotionStatus.PROMOTE_PAPER
        eligible_demo = False  # Demo execution requires a later explicit gateway.
        payload = {
            "evidence": evidence.to_dict(), "checks": [x.to_dict() for x in checks],
            "failures": failures, "warnings": list(dict.fromkeys(warnings)), "status": status.value,
        }
        return ResearchPromotionResult(
            status=status,
            eligible_for_paper=eligible_paper,
            eligible_for_demo=eligible_demo,
            checks=tuple(checks),
            failures=tuple(failures),
            warnings=tuple(dict.fromkeys(warnings)),
            evidence_fingerprint=_fingerprint(payload),
            policy=p.to_dict(),
            metadata={"execution_authorization": False, "broker_access": False, "candidate_selection": False},
        )


def promote_research(evidence: PromotionEvidence, policy: ResearchPromotionPolicy | None = None) -> ResearchPromotionResult:
    """Functional wrapper for the deterministic promotion gate."""
    return ResearchPromotionEngine(policy).evaluate(evidence)
