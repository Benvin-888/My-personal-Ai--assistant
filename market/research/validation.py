"""APEX / BENVIN Research Validation & Promotion Gate.

Phase 2.10 - Research Validation & Promotion Gate

This module turns Phase 2.9 research evidence into an explicit, deterministic
validation decision. It never optimizes a strategy and never authorizes live
or broker execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping

from .engine import StrategyResearchReport


class ResearchValidationError(ValueError):
    """Raised when validation input or policy is invalid."""


class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class ResearchValidationPolicy:
    """Conservative evidence thresholds for a research promotion decision."""

    minimum_trades: int = 30
    require_positive_baseline: bool = True
    require_positive_out_of_sample: bool = True
    minimum_oos_generalization_pct: float = 50.0
    minimum_walk_forward_windows: int = 3
    minimum_positive_walk_forward_fraction: float = 0.50
    require_parameter_stability: bool = True
    minimum_profitable_parameter_fraction: float = 0.50
    require_regime_stability: bool = False
    minimum_profitable_regime_fraction: float = 0.50
    require_session_stability: bool = False
    minimum_profitable_session_fraction: float = 0.50
    require_monte_carlo: bool = True
    minimum_monte_carlo_positive_fraction: float = 0.55
    maximum_monte_carlo_ruin_fraction: float = 0.05
    maximum_baseline_drawdown_pct: float = 20.0
    maximum_transaction_cost_fraction_of_gross_profit: float = 0.50

    def __post_init__(self) -> None:
        integer_fields = ("minimum_trades", "minimum_walk_forward_windows")
        for name in integer_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ResearchValidationError(f"{name} must be a positive integer")
        fraction_fields = (
            "minimum_positive_walk_forward_fraction",
            "minimum_profitable_parameter_fraction",
            "minimum_profitable_regime_fraction",
            "minimum_profitable_session_fraction",
            "minimum_monte_carlo_positive_fraction",
            "maximum_monte_carlo_ruin_fraction",
            "maximum_transaction_cost_fraction_of_gross_profit",
        )
        for name in fraction_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ResearchValidationError(f"{name} must be finite numeric")
            if not 0.0 <= float(value) <= 1.0:
                raise ResearchValidationError(f"{name} must be between 0 and 1")
        for name in ("minimum_oos_generalization_pct", "maximum_baseline_drawdown_pct"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0:
                raise ResearchValidationError(f"{name} must be finite and non-negative")
        bool_fields = (
            "require_positive_baseline", "require_positive_out_of_sample",
            "require_parameter_stability", "require_regime_stability",
            "require_session_stability", "require_monte_carlo",
        )
        for name in bool_fields:
            if not isinstance(getattr(self, name), bool):
                raise ResearchValidationError(f"{name} must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            key: getattr(self, key)
            for key in self.__dataclass_fields__
        }


@dataclass(frozen=True)
class ValidationCheck:
    """One auditable validation check."""

    name: str
    passed: bool
    required: bool
    value: float | int | bool | None
    threshold: float | int | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "required": self.required,
            "value": self.value,
            "threshold": self.threshold,
            "message": self.message,
        }


@dataclass(frozen=True)
class ResearchValidationResult:
    """Immutable promotion-gate result."""

    status: ValidationStatus
    eligible_for_paper: bool
    eligible_for_demo: bool
    checks: tuple[ValidationCheck, ...]
    failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence_fingerprint: str = ""
    policy: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis": "research_validation",
            "status": self.status.value,
            "eligible_for_paper": self.eligible_for_paper,
            "eligible_for_demo": self.eligible_for_demo,
            "checks": [check.to_dict() for check in self.checks],
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "evidence_fingerprint": self.evidence_fingerprint,
            "policy": dict(self.policy),
            "metadata": dict(self.metadata),
        }


def _fingerprint(report: StrategyResearchReport, policy: ResearchValidationPolicy) -> str:
    payload = {"report": report.to_dict(), "policy": policy.to_dict()}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ResearchValidationEngine:
    """Validate whether Phase 2.9 evidence clears explicit promotion gates."""

    def validate(
        self,
        report: StrategyResearchReport,
        policy: ResearchValidationPolicy | None = None,
    ) -> ResearchValidationResult:
        if not isinstance(report, StrategyResearchReport):
            raise ResearchValidationError("report must be a StrategyResearchReport")
        policy = policy or ResearchValidationPolicy()
        checks: list[ValidationCheck] = []
        failures: list[str] = []
        warnings: list[str] = []

        def add(name: str, passed: bool, required: bool, value: Any, threshold: Any, message: str) -> None:
            check = ValidationCheck(name, bool(passed), bool(required), value, threshold, message)
            checks.append(check)
            if required and not passed:
                failures.append(name)

        baseline = report.baseline
        add("minimum_trades", baseline.trade_count >= policy.minimum_trades, True,
            baseline.trade_count, policy.minimum_trades,
            "Baseline trade count meets the minimum research sample size." if baseline.trade_count >= policy.minimum_trades else "Baseline trade count is below the minimum research sample size.")
        add("baseline_positive", baseline.net_pnl > 0, policy.require_positive_baseline,
            baseline.net_pnl, 0.0,
            "Baseline net P&L is positive." if baseline.net_pnl > 0 else "Baseline net P&L is not positive.")
        add("baseline_drawdown", baseline.max_drawdown_pct <= policy.maximum_baseline_drawdown_pct, True,
            baseline.max_drawdown_pct, policy.maximum_baseline_drawdown_pct,
            "Baseline drawdown is within the research ceiling." if baseline.max_drawdown_pct <= policy.maximum_baseline_drawdown_pct else "Baseline drawdown exceeds the research ceiling.")

        oos = report.out_of_sample
        if oos is None:
            add("out_of_sample_present", False, True, None, None, "Out-of-sample evidence is required.")
        else:
            add("out_of_sample_positive", oos.out_of_sample_positive, policy.require_positive_out_of_sample,
                oos.out_of_sample_positive, True,
                "Out-of-sample P&L is positive." if oos.out_of_sample_positive else "Out-of-sample P&L is not positive.")
            add("oos_generalization", oos.generalization_ratio_pct >= policy.minimum_oos_generalization_pct, True,
                oos.generalization_ratio_pct, policy.minimum_oos_generalization_pct,
                "Out-of-sample generalization ratio clears the threshold." if oos.generalization_ratio_pct >= policy.minimum_oos_generalization_pct else "Out-of-sample generalization ratio is below the threshold.")

        wf = report.walk_forward
        if not wf:
            add("walk_forward_present", False, True, 0, policy.minimum_walk_forward_windows, "Walk-forward evidence is required.")
        else:
            positive_fraction = sum(1 for item in wf if item.test.net_pnl > 0) / len(wf)
            add("walk_forward_windows", len(wf) >= policy.minimum_walk_forward_windows, True,
                len(wf), policy.minimum_walk_forward_windows,
                "Enough walk-forward windows are present." if len(wf) >= policy.minimum_walk_forward_windows else "Too few walk-forward windows are present.")
            add("walk_forward_positive_fraction", positive_fraction >= policy.minimum_positive_walk_forward_fraction, True,
                positive_fraction, policy.minimum_positive_walk_forward_fraction,
                "The required fraction of walk-forward test windows is profitable." if positive_fraction >= policy.minimum_positive_walk_forward_fraction else "Too few walk-forward test windows are profitable.")

        ps = report.parameter_stability
        if ps is None:
            add("parameter_stability_present", False, policy.require_parameter_stability, None, None, "Parameter-stability evidence is required by policy." if policy.require_parameter_stability else "Parameter-stability evidence was not supplied.")
        else:
            add("parameter_profitable_fraction", ps.profitable_run_fraction >= policy.minimum_profitable_parameter_fraction, policy.require_parameter_stability,
                ps.profitable_run_fraction, policy.minimum_profitable_parameter_fraction,
                "Parameter configurations show sufficient profitability breadth." if ps.profitable_run_fraction >= policy.minimum_profitable_parameter_fraction else "Parameter profitability is too concentrated.")

        for label, group, required, threshold in (
            ("regime", report.regime_stability, policy.require_regime_stability, policy.minimum_profitable_regime_fraction),
            ("session", report.session_stability, policy.require_session_stability, policy.minimum_profitable_session_fraction),
        ):
            if group is None:
                add(f"{label}_stability_present", False, required, None, None, f"{label.title()} stability evidence is required by policy." if required else f"{label.title()} stability evidence was not supplied.")
                if not required:
                    warnings.append(f"no {label} stability evidence")
            else:
                add(f"{label}_profitable_fraction", group.profitable_group_fraction >= threshold, required,
                    group.profitable_group_fraction, threshold,
                    f"{label.title()} groups meet the profitability breadth threshold." if group.profitable_group_fraction >= threshold else f"{label.title()} profitability is too concentrated.")

        mc = report.monte_carlo
        if mc is None:
            add("monte_carlo_present", False, policy.require_monte_carlo, None, None, "Monte Carlo evidence is required by policy." if policy.require_monte_carlo else "Monte Carlo evidence was not supplied.")
        else:
            add("monte_carlo_positive_fraction", mc.positive_terminal_fraction >= policy.minimum_monte_carlo_positive_fraction, policy.require_monte_carlo,
                mc.positive_terminal_fraction, policy.minimum_monte_carlo_positive_fraction,
                "Monte Carlo positive-terminal fraction clears the threshold." if mc.positive_terminal_fraction >= policy.minimum_monte_carlo_positive_fraction else "Monte Carlo positive-terminal fraction is below the threshold.")
            add("monte_carlo_ruin_fraction", mc.ruin_fraction <= policy.maximum_monte_carlo_ruin_fraction, policy.require_monte_carlo,
                mc.ruin_fraction, policy.maximum_monte_carlo_ruin_fraction,
                "Monte Carlo ruin fraction is within the ceiling." if mc.ruin_fraction <= policy.maximum_monte_carlo_ruin_fraction else "Monte Carlo ruin fraction exceeds the ceiling.")

        if baseline.gross_profit > 0:
            cost_fraction = baseline.total_transaction_costs / baseline.gross_profit
            add("transaction_cost_burden", cost_fraction <= policy.maximum_transaction_cost_fraction_of_gross_profit, True,
                cost_fraction, policy.maximum_transaction_cost_fraction_of_gross_profit,
                "Transaction-cost burden is within the research ceiling." if cost_fraction <= policy.maximum_transaction_cost_fraction_of_gross_profit else "Transaction costs consume too much gross profit.")
        else:
            add("transaction_cost_burden", False, True, None, policy.maximum_transaction_cost_fraction_of_gross_profit, "Gross profit is unavailable for transaction-cost burden analysis.")

        if report.warnings:
            warnings.extend(report.warnings)

        status = ValidationStatus.PASS if not failures else ValidationStatus.FAIL
        eligible_paper = status == ValidationStatus.PASS
        # Demo eligibility is intentionally stricter than research pass: the
        # gate requires all mandatory evidence and a clean validation result.
        eligible_demo = eligible_paper and not any("no regime stability evidence" in w or "no session stability evidence" in w for w in warnings)
        return ResearchValidationResult(
            status=status,
            eligible_for_paper=eligible_paper,
            eligible_for_demo=eligible_demo,
            checks=tuple(checks),
            failures=tuple(failures),
            warnings=tuple(dict.fromkeys(warnings)),
            evidence_fingerprint=_fingerprint(report, policy),
            policy=policy.to_dict(),
            metadata={"execution_authorization": False, "broker_access": False},
        )


def validate_research(
    report: StrategyResearchReport,
    policy: ResearchValidationPolicy | None = None,
) -> ResearchValidationResult:
    """Functional wrapper around :class:`ResearchValidationEngine`."""
    return ResearchValidationEngine().validate(report, policy)
