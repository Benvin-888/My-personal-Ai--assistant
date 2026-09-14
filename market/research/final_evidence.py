"""APEX / BENVIN final research-evidence integration.

Phase 2.17 - Final Research Evidence Integration & Promotion Integrity

This module is the final deterministic research gate before paper-trading
infrastructure. It combines the existing Phase 2.14 promotion decision with
Phase 2.15 cohort-integrity evidence and Phase 2.16 portfolio/correlation
evidence. It never selects a candidate, optimizes parameters, fetches market
data, accesses a broker, places an order, or authorizes execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from .cohort import CohortStatus, ResearchCohortResult
from .portfolio import PortfolioRobustnessStatus, PortfolioRobustnessResult
from .promotion import PromotionStatus, ResearchPromotionResult


class FinalEvidenceError(ValueError):
    """Raised when final research evidence is malformed."""


class FinalEvidenceStatus(str, Enum):
    """Final evidence disposition; never an execution authorization."""

    PROMOTE_PAPER = "PROMOTE_PAPER"
    HOLD = "HOLD"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _non_empty_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FinalEvidenceError(f"{name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class FinalResearchEvidence:
    """Immutable bundle containing every evidence gate required by Phase 2.17."""

    candidate_id: str
    promotion: ResearchPromotionResult
    cohort: ResearchCohortResult
    portfolio: PortfolioRobustnessResult
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _non_empty_text(self.candidate_id, "candidate_id")
        if not isinstance(self.promotion, ResearchPromotionResult):
            raise FinalEvidenceError("promotion must be ResearchPromotionResult")
        if not isinstance(self.cohort, ResearchCohortResult):
            raise FinalEvidenceError("cohort must be ResearchCohortResult")
        if not isinstance(self.portfolio, PortfolioRobustnessResult):
            raise FinalEvidenceError("portfolio must be PortfolioRobustnessResult")

        if self.portfolio.cohort_id != self.cohort.cohort_id:
            raise FinalEvidenceError("portfolio cohort_id must match cohort cohort_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "promotion": self.promotion.to_dict(),
            "cohort": self.cohort.to_dict(),
            "portfolio": self.portfolio.to_dict(),
            "metadata": dict(self.metadata),
        }

    @property
    def evidence_fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


@dataclass(frozen=True)
class FinalEvidencePolicy:
    """Required integrity gates for final research promotion."""

    require_promotion_pass: bool = True
    require_cohort_pass: bool = True
    require_portfolio_pass: bool = True
    require_candidate_cohort_match: bool = True
    require_symbol_set_match: bool = True
    require_non_empty_evidence_fingerprints: bool = True

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if not isinstance(getattr(self, name), bool):
                raise FinalEvidenceError(f"{name} must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class FinalEvidenceCheck:
    """One auditable final-evidence integrity check."""

    name: str
    passed: bool
    required: bool
    actual: Any
    threshold: Any
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "required": self.required,
            "actual": self.actual,
            "threshold": self.threshold,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FinalResearchEvidenceResult:
    """Immutable final research decision with a complete evidence fingerprint."""

    status: FinalEvidenceStatus
    eligible_for_paper: bool
    eligible_for_demo: bool
    candidate_id: str
    cohort_id: str
    checks: tuple[FinalEvidenceCheck, ...]
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence_fingerprint: str
    nested_fingerprints: Mapping[str, str]
    policy: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "eligible_for_paper": self.eligible_for_paper,
            "eligible_for_demo": self.eligible_for_demo,
            "candidate_id": self.candidate_id,
            "cohort_id": self.cohort_id,
            "checks": [check.to_dict() for check in self.checks],
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "evidence_fingerprint": self.evidence_fingerprint,
            "nested_fingerprints": dict(self.nested_fingerprints),
            "policy": dict(self.policy),
            "metadata": dict(self.metadata),
        }


class FinalResearchEvidenceEngine:
    """Finalize research evidence without selecting or executing a strategy."""

    def __init__(self, policy: FinalEvidencePolicy | None = None) -> None:
        self.policy = policy or FinalEvidencePolicy()

    def evaluate(self, evidence: FinalResearchEvidence) -> FinalResearchEvidenceResult:
        if not isinstance(evidence, FinalResearchEvidence):
            raise FinalEvidenceError("evidence must be FinalResearchEvidence")

        p = self.policy
        checks: list[FinalEvidenceCheck] = []
        failures: list[str] = []
        warnings: list[str] = []

        def add(
            name: str,
            passed: bool,
            required: bool,
            actual: Any,
            threshold: Any,
            reason: str,
        ) -> None:
            check = FinalEvidenceCheck(
                name=name,
                passed=bool(passed),
                required=bool(required),
                actual=actual,
                threshold=threshold,
                reason=reason,
            )
            checks.append(check)
            if required and not passed:
                failures.append(reason)

        add(
            "phase_2_14_promotion",
            evidence.promotion.status == PromotionStatus.PROMOTE_PAPER
            and evidence.promotion.eligible_for_paper,
            p.require_promotion_pass,
            evidence.promotion.status.value,
            PromotionStatus.PROMOTE_PAPER.value,
            "Phase 2.14 promotion evidence did not pass",
        )
        add(
            "phase_2_15_cohort",
            evidence.cohort.status == CohortStatus.PASS
            and evidence.cohort.eligible_for_promotion,
            p.require_cohort_pass,
            evidence.cohort.status.value,
            CohortStatus.PASS.value,
            "Phase 2.15 research cohort integrity did not pass",
        )
        add(
            "phase_2_16_portfolio",
            evidence.portfolio.status == PortfolioRobustnessStatus.PASS
            and evidence.portfolio.eligible_for_promotion,
            p.require_portfolio_pass,
            evidence.portfolio.status.value,
            PortfolioRobustnessStatus.PASS.value,
            "Phase 2.16 portfolio/correlation robustness did not pass",
        )

        cohort_match = evidence.candidate_id == evidence.cohort.cohort_id
        add(
            "candidate_cohort_identity",
            cohort_match,
            p.require_candidate_cohort_match,
            {"candidate_id": evidence.candidate_id, "cohort_id": evidence.cohort.cohort_id},
            "candidate_id == cohort_id",
            "candidate and cohort identities do not match",
        )

        cohort_symbols = tuple(sorted(evidence.cohort.symbols))
        portfolio_symbols = tuple(sorted(evidence.portfolio.symbols))
        symbols_match = cohort_symbols == portfolio_symbols
        add(
            "cohort_portfolio_symbol_set",
            symbols_match,
            p.require_symbol_set_match,
            list(portfolio_symbols),
            list(cohort_symbols),
            "portfolio symbol coverage does not match the research cohort",
        )

        nested = {
            "promotion": _non_empty_text(evidence.promotion.evidence_fingerprint, "promotion evidence_fingerprint"),
            "cohort": _non_empty_text(evidence.cohort.evidence_fingerprint, "cohort evidence_fingerprint"),
            "portfolio": _non_empty_text(evidence.portfolio.evidence_fingerprint, "portfolio evidence_fingerprint"),
        }
        fingerprints_ok = all(len(value) == 64 for value in nested.values())
        add(
            "nested_evidence_fingerprints",
            fingerprints_ok,
            p.require_non_empty_evidence_fingerprints,
            {key: len(value) for key, value in nested.items()},
            64,
            "one or more nested evidence fingerprints are missing or malformed",
        )

        warnings.extend(evidence.promotion.warnings)
        warnings.extend(evidence.cohort.warnings)
        warnings.extend(evidence.portfolio.warnings)

        if failures:
            status = (
                FinalEvidenceStatus.INSUFFICIENT_DATA
                if any(
                    check.name in {"phase_2_14_promotion", "phase_2_15_cohort", "phase_2_16_portfolio"}
                    and check.actual in {
                        PromotionStatus.INSUFFICIENT_DATA.value,
                        CohortStatus.INSUFFICIENT_DATA.value,
                        PortfolioRobustnessStatus.INSUFFICIENT_DATA.value,
                    }
                    for check in checks
                    if not check.passed
                )
                else FinalEvidenceStatus.HOLD
            )
        else:
            status = FinalEvidenceStatus.PROMOTE_PAPER

        payload = {
            "evidence": evidence.to_dict(),
            "checks": [check.to_dict() for check in checks],
            "failures": failures,
            "warnings": list(dict.fromkeys(warnings)),
            "nested_fingerprints": nested,
            "status": status.value,
        }
        fingerprint = _fingerprint(payload)

        return FinalResearchEvidenceResult(
            status=status,
            eligible_for_paper=status == FinalEvidenceStatus.PROMOTE_PAPER,
            eligible_for_demo=False,
            candidate_id=evidence.candidate_id,
            cohort_id=evidence.cohort.cohort_id,
            checks=tuple(checks),
            failures=tuple(failures),
            warnings=tuple(dict.fromkeys(warnings)),
            evidence_fingerprint=fingerprint,
            nested_fingerprints=nested,
            policy=p.to_dict(),
            metadata={
                "phase": "2.17",
                "execution_authorization": False,
                "broker_access": False,
                "candidate_selection": False,
                "order_placement": False,
                "paper_trading_authorization": False,
                "demo_eligibility": False,
            },
        )


def finalize_research_evidence(
    evidence: FinalResearchEvidence,
    policy: FinalEvidencePolicy | None = None,
) -> FinalResearchEvidenceResult:
    """Functional wrapper for the Phase 2.17 final evidence gate."""

    return FinalResearchEvidenceEngine(policy).evaluate(evidence)
