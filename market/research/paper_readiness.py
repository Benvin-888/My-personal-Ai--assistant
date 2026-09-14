"""APEX / BENVIN paper-trading readiness contract.

Phase 2.18 - Paper Trading Readiness & Safety Gate

This module converts the final research evidence from Phase 2.17 into an
explicit readiness assessment for a *research-only paper-trading environment*.
It checks that market-data, risk, execution-model, friction, and isolation
prerequisites have been explicitly verified. It does not connect to a broker,
place orders, authorize demo/live execution, or claim that a strategy is
profitable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping

from .final_evidence import FinalEvidenceStatus, FinalResearchEvidenceResult


class PaperReadinessError(ValueError):
    """Raised when a paper-readiness contract is malformed."""


class PaperReadinessStatus(str, Enum):
    READY = "READY"
    HOLD = "HOLD"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PaperReadinessError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise PaperReadinessError(f"{name} must be finite")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PaperReadinessError(f"{name} must be a non-empty string")
    return value.strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PaperReadinessPolicy:
    """Conservative prerequisites for research-only paper trading."""

    maximum_market_data_age_seconds: float = 60.0
    maximum_risk_fraction_per_trade: float = 0.01
    maximum_total_risk_fraction: float = 0.02
    minimum_reward_risk: float = 1.5
    require_final_evidence: bool = True
    require_market_data_ready: bool = True
    require_risk_ready: bool = True
    require_point_in_time_execution: bool = True
    require_no_lookahead_verified: bool = True
    require_friction_model: bool = True
    require_paper_isolation: bool = True
    require_broker_execution_disabled: bool = True

    def __post_init__(self) -> None:
        numeric = {
            "maximum_market_data_age_seconds": self.maximum_market_data_age_seconds,
            "maximum_risk_fraction_per_trade": self.maximum_risk_fraction_per_trade,
            "maximum_total_risk_fraction": self.maximum_total_risk_fraction,
            "minimum_reward_risk": self.minimum_reward_risk,
        }
        for name, value in numeric.items():
            value = _finite(value, name)
            if value < 0:
                raise PaperReadinessError(f"{name} must be non-negative")
        if self.maximum_market_data_age_seconds <= 0:
            raise PaperReadinessError("maximum_market_data_age_seconds must be positive")
        if self.maximum_risk_fraction_per_trade > 1 or self.maximum_total_risk_fraction > 1:
            raise PaperReadinessError("risk fractions must be between 0 and 1")
        if self.minimum_reward_risk <= 0:
            raise PaperReadinessError("minimum_reward_risk must be positive")
        for name in (
            "require_final_evidence", "require_market_data_ready", "require_risk_ready",
            "require_point_in_time_execution", "require_no_lookahead_verified",
            "require_friction_model", "require_paper_isolation",
            "require_broker_execution_disabled",
        ):
            if not isinstance(getattr(self, name), bool):
                raise PaperReadinessError(f"{name} must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class PaperReadinessInput:
    """Explicit operational facts supplied by the paper-trading harness."""

    environment_id: str
    market_data_ready: bool
    market_data_age_seconds: float
    risk_ready: bool
    configured_risk_fraction_per_trade: float
    configured_total_risk_fraction: float
    configured_reward_risk: float
    point_in_time_execution: bool
    no_lookahead_verified: bool
    friction_model_ready: bool
    paper_isolated: bool
    broker_execution_disabled: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.environment_id, "environment_id")
        for name in (
            "market_data_ready", "risk_ready", "point_in_time_execution",
            "no_lookahead_verified", "friction_model_ready", "paper_isolated",
            "broker_execution_disabled",
        ):
            if not isinstance(getattr(self, name), bool):
                raise PaperReadinessError(f"{name} must be boolean")
        for name in (
            "market_data_age_seconds", "configured_risk_fraction_per_trade",
            "configured_total_risk_fraction", "configured_reward_risk",
        ):
            value = _finite(getattr(self, name), name)
            if value < 0:
                raise PaperReadinessError(f"{name} must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "market_data_ready": self.market_data_ready,
            "market_data_age_seconds": self.market_data_age_seconds,
            "risk_ready": self.risk_ready,
            "configured_risk_fraction_per_trade": self.configured_risk_fraction_per_trade,
            "configured_total_risk_fraction": self.configured_total_risk_fraction,
            "configured_reward_risk": self.configured_reward_risk,
            "point_in_time_execution": self.point_in_time_execution,
            "no_lookahead_verified": self.no_lookahead_verified,
            "friction_model_ready": self.friction_model_ready,
            "paper_isolated": self.paper_isolated,
            "broker_execution_disabled": self.broker_execution_disabled,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PaperReadinessCheck:
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
class PaperReadinessResult:
    """Immutable readiness evidence; never an execution authorization."""

    status: PaperReadinessStatus
    ready_for_paper_research: bool
    eligible_for_demo: bool
    environment_id: str
    final_evidence_fingerprint: str
    checks: tuple[PaperReadinessCheck, ...]
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence_fingerprint: str
    policy: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "ready_for_paper_research": self.ready_for_paper_research,
            "eligible_for_demo": self.eligible_for_demo,
            "environment_id": self.environment_id,
            "final_evidence_fingerprint": self.final_evidence_fingerprint,
            "checks": [x.to_dict() for x in self.checks],
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "evidence_fingerprint": self.evidence_fingerprint,
            "policy": dict(self.policy),
            "metadata": dict(self.metadata),
        }


class PaperReadinessEngine:
    """Evaluate readiness for an isolated paper-trading research harness."""

    def __init__(self, policy: PaperReadinessPolicy | None = None) -> None:
        self.policy = policy or PaperReadinessPolicy()

    def evaluate(
        self,
        final_evidence: FinalResearchEvidenceResult,
        readiness: PaperReadinessInput,
    ) -> PaperReadinessResult:
        if not isinstance(final_evidence, FinalResearchEvidenceResult):
            raise PaperReadinessError("final_evidence must be FinalResearchEvidenceResult")
        if not isinstance(readiness, PaperReadinessInput):
            raise PaperReadinessError("readiness must be PaperReadinessInput")

        p = self.policy
        checks: list[PaperReadinessCheck] = []
        failures: list[str] = []
        warnings: list[str] = []

        def add(name: str, passed: bool, required: bool, actual: Any, threshold: Any, reason: str) -> None:
            checks.append(PaperReadinessCheck(name, bool(passed), bool(required), actual, threshold, reason))
            if required and not passed:
                failures.append(reason)

        add(
            "final_research_evidence",
            final_evidence.status == FinalEvidenceStatus.PROMOTE_PAPER
            and final_evidence.eligible_for_paper,
            p.require_final_evidence,
            final_evidence.status.value,
            FinalEvidenceStatus.PROMOTE_PAPER.value,
            "Phase 2.17 final research evidence is not approved for paper research",
        )
        add(
            "market_data_readiness",
            readiness.market_data_ready and readiness.market_data_age_seconds <= p.maximum_market_data_age_seconds,
            p.require_market_data_ready,
            {"ready": readiness.market_data_ready, "age_seconds": readiness.market_data_age_seconds},
            {"ready": True, "max_age_seconds": p.maximum_market_data_age_seconds},
            "market data is not ready or is too stale for paper research",
        )
        add(
            "risk_readiness",
            readiness.risk_ready
            and readiness.configured_risk_fraction_per_trade <= p.maximum_risk_fraction_per_trade
            and readiness.configured_total_risk_fraction <= p.maximum_total_risk_fraction,
            p.require_risk_ready,
            {
                "ready": readiness.risk_ready,
                "per_trade": readiness.configured_risk_fraction_per_trade,
                "total": readiness.configured_total_risk_fraction,
            },
            {
                "ready": True,
                "max_per_trade": p.maximum_risk_fraction_per_trade,
                "max_total": p.maximum_total_risk_fraction,
            },
            "risk configuration is missing or exceeds the readiness ceilings",
        )
        add(
            "reward_risk_configuration",
            readiness.configured_reward_risk >= p.minimum_reward_risk,
            p.require_risk_ready,
            readiness.configured_reward_risk,
            p.minimum_reward_risk,
            "configured reward/risk is below the minimum research readiness threshold",
        )
        add(
            "point_in_time_execution",
            readiness.point_in_time_execution,
            p.require_point_in_time_execution,
            readiness.point_in_time_execution,
            True,
            "point-in-time execution semantics are not verified",
        )
        add(
            "no_lookahead_verified",
            readiness.no_lookahead_verified,
            p.require_no_lookahead_verified,
            readiness.no_lookahead_verified,
            True,
            "no-lookahead verification is missing",
        )
        add(
            "friction_model",
            readiness.friction_model_ready,
            p.require_friction_model,
            readiness.friction_model_ready,
            True,
            "transaction-cost/slippage friction model is not ready",
        )
        add(
            "paper_isolation",
            readiness.paper_isolated,
            p.require_paper_isolation,
            readiness.paper_isolated,
            True,
            "paper environment is not explicitly isolated",
        )
        add(
            "broker_execution_disabled",
            readiness.broker_execution_disabled,
            p.require_broker_execution_disabled,
            readiness.broker_execution_disabled,
            True,
            "broker execution must remain disabled during paper research",
        )

        if readiness.metadata.get("data_source") is None:
            warnings.append("market-data source was not recorded in readiness metadata")
        if readiness.metadata.get("execution_model") is None:
            warnings.append("execution-model identity was not recorded in readiness metadata")

        status = PaperReadinessStatus.READY if not failures else PaperReadinessStatus.HOLD
        if not readiness.market_data_ready and p.require_market_data_ready:
            status = PaperReadinessStatus.INSUFFICIENT_DATA

        payload = {
            "final_evidence_fingerprint": final_evidence.evidence_fingerprint,
            "readiness": readiness.to_dict(),
            "checks": [x.to_dict() for x in checks],
            "failures": failures,
            "warnings": list(dict.fromkeys(warnings)),
            "status": status.value,
        }
        return PaperReadinessResult(
            status=status,
            ready_for_paper_research=status == PaperReadinessStatus.READY,
            eligible_for_demo=False,
            environment_id=readiness.environment_id,
            final_evidence_fingerprint=final_evidence.evidence_fingerprint,
            checks=tuple(checks),
            failures=tuple(failures),
            warnings=tuple(dict.fromkeys(warnings)),
            evidence_fingerprint=_fingerprint(payload),
            policy=p.to_dict(),
            metadata={
                "phase": "2.18",
                "research_only": True,
                "execution_authorization": False,
                "paper_trading_authorization": False,
                "demo_eligibility": False,
                "broker_access": False,
                "order_placement": False,
                "candidate_selection": False,
                "profitability_guarantee": False,
            },
        )


def assess_paper_readiness(
    final_evidence: FinalResearchEvidenceResult,
    readiness: PaperReadinessInput,
    policy: PaperReadinessPolicy | None = None,
) -> PaperReadinessResult:
    """Functional wrapper for the Phase 2.18 readiness gate."""
    return PaperReadinessEngine(policy).evaluate(final_evidence, readiness)
