"""APEX / BENVIN reproducible research experiment framework.

Phase 2.11 - Research Experiment & Cross-Market Validation Foundation

This module defines deterministic, immutable research specifications and result
aggregation for running the existing backtest/research/validation pipeline
across multiple Forex datasets. It deliberately does not fetch market data,
optimize parameters, access brokers, place orders, or authorize execution.

The framework is a coordination contract: an external runner supplies the
actual backtest result for each experiment case. This keeps data access,
strategy execution, and research bookkeeping cleanly separated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Any, Callable, Mapping, Sequence

from .engine import ResearchPerformance, StrategyResearchReport
from .validation import ResearchValidationPolicy, ResearchValidationResult, ValidationStatus, validate_research


class ResearchExperimentError(ValueError):
    """Raised when an experiment specification or result is invalid."""


class ExperimentStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ERROR = "ERROR"


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchExperimentError(f"{name} must be a non-empty string")
    return value.strip()


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ResearchExperimentError(f"{name} must be finite numeric")
    return float(value)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResearchDatasetSpec:
    """Identity and provenance contract for one research dataset."""

    dataset_id: str
    symbol: str
    interval: str
    start_utc: str
    end_utc: str
    source: str
    row_count: int
    content_fingerprint: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, name in (
            (self.dataset_id, "dataset_id"), (self.symbol, "symbol"),
            (self.interval, "interval"), (self.start_utc, "start_utc"),
            (self.end_utc, "end_utc"), (self.source, "source"),
        ):
            _text(value, name)
        if isinstance(self.row_count, bool) or not isinstance(self.row_count, int) or self.row_count < 1:
            raise ResearchExperimentError("row_count must be a positive integer")
        if self.content_fingerprint is not None:
            _text(self.content_fingerprint, "content_fingerprint")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "symbol": self.symbol,
            "interval": self.interval,
            "start_utc": self.start_utc,
            "end_utc": self.end_utc,
            "source": self.source,
            "row_count": self.row_count,
            "content_fingerprint": self.content_fingerprint,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ResearchExperimentSpec:
    """Immutable definition of one reproducible research case."""

    experiment_id: str
    strategy_id: str
    dataset: ResearchDatasetSpec
    strategy_parameters: Mapping[str, Any] = field(default_factory=dict)
    risk_parameters: Mapping[str, Any] = field(default_factory=dict)
    execution_parameters: Mapping[str, Any] = field(default_factory=dict)
    seed: int = 0
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.experiment_id, "experiment_id")
        _text(self.strategy_id, "strategy_id")
        if not isinstance(self.dataset, ResearchDatasetSpec):
            raise ResearchExperimentError("dataset must be a ResearchDatasetSpec")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ResearchExperimentError("seed must be an integer")
        if any(not isinstance(tag, str) or not tag.strip() for tag in self.tags):
            raise ResearchExperimentError("tags must contain non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "strategy_id": self.strategy_id,
            "dataset": self.dataset.to_dict(),
            "strategy_parameters": dict(self.strategy_parameters),
            "risk_parameters": dict(self.risk_parameters),
            "execution_parameters": dict(self.execution_parameters),
            "seed": self.seed,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


@dataclass(frozen=True)
class ResearchExperimentResult:
    """Auditable result for one completed experiment case."""

    spec: ResearchExperimentSpec
    status: ExperimentStatus
    performance: ResearchPerformance | None = None
    validation: ResearchValidationResult | None = None
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.spec, ResearchExperimentSpec):
            raise ResearchExperimentError("spec must be a ResearchExperimentSpec")
        if self.status == ExperimentStatus.PASS and self.performance is None:
            raise ResearchExperimentError("PASS result requires performance")
        if self.status == ExperimentStatus.ERROR and not self.error:
            raise ResearchExperimentError("ERROR result requires error text")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.spec.experiment_id,
            "spec_fingerprint": self.spec.fingerprint,
            "status": self.status.value,
            "performance": self.performance.to_dict() if self.performance else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CrossMarketResearchSummary:
    """Aggregate evidence across completed experiment cases."""

    total_cases: int
    completed_cases: int
    passed_cases: int
    failed_cases: int
    validation_pass_fraction: float
    profitable_case_fraction: float
    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    by_symbol: Mapping[str, Mapping[str, Any]]
    by_interval: Mapping[str, Mapping[str, Any]]
    evidence_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "completed_cases": self.completed_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "validation_pass_fraction": self.validation_pass_fraction,
            "profitable_case_fraction": self.profitable_case_fraction,
            "symbols": list(self.symbols),
            "intervals": list(self.intervals),
            "by_symbol": {k: dict(v) for k, v in self.by_symbol.items()},
            "by_interval": {k: dict(v) for k, v in self.by_interval.items()},
            "evidence_fingerprint": self.evidence_fingerprint,
        }


BacktestRunner = Callable[[ResearchExperimentSpec], StrategyResearchReport]


class ResearchExperimentEngine:
    """Run supplied research cases and aggregate cross-market evidence."""

    def __init__(self, validation_policy: ResearchValidationPolicy | None = None) -> None:
        self.validation_policy = validation_policy or ResearchValidationPolicy()

    def validate_specs(self, specs: Sequence[ResearchExperimentSpec]) -> tuple[ResearchExperimentSpec, ...]:
        items = tuple(specs)
        if not items:
            raise ResearchExperimentError("at least one experiment specification is required")
        ids: set[str] = set()
        for spec in items:
            if not isinstance(spec, ResearchExperimentSpec):
                raise ResearchExperimentError("all specs must be ResearchExperimentSpec instances")
            if spec.experiment_id in ids:
                raise ResearchExperimentError(f"duplicate experiment_id: {spec.experiment_id}")
            ids.add(spec.experiment_id)
        return items

    def run_case(self, spec: ResearchExperimentSpec, runner: BacktestRunner) -> ResearchExperimentResult:
        if not isinstance(spec, ResearchExperimentSpec):
            raise ResearchExperimentError("spec must be a ResearchExperimentSpec")
        if not callable(runner):
            raise ResearchExperimentError("runner must be callable")
        try:
            report = runner(spec)
            if not isinstance(report, StrategyResearchReport):
                raise ResearchExperimentError("runner must return StrategyResearchReport")
            validation = validate_research(report, self.validation_policy)
            status = ExperimentStatus.PASS if validation.status == ValidationStatus.PASS else ExperimentStatus.FAIL
            return ResearchExperimentResult(
                spec=spec,
                status=status,
                performance=report.baseline,
                validation=validation,
            )
        except Exception as exc:
            return ResearchExperimentResult(
                spec=spec,
                status=ExperimentStatus.ERROR,
                error=f"{type(exc).__name__}: {exc}",
            )

    def run(self, specs: Sequence[ResearchExperimentSpec], runner: BacktestRunner) -> tuple[ResearchExperimentResult, ...]:
        items = self.validate_specs(specs)
        return tuple(self.run_case(spec, runner) for spec in items)

    @staticmethod
    def summarize(results: Sequence[ResearchExperimentResult]) -> CrossMarketResearchSummary:
        items = tuple(results)
        if not items:
            raise ResearchExperimentError("at least one experiment result is required")
        if any(not isinstance(item, ResearchExperimentResult) for item in items):
            raise ResearchExperimentError("all results must be ResearchExperimentResult instances")

        completed = [item for item in items if item.performance is not None]
        passed = [item for item in items if item.status == ExperimentStatus.PASS]
        failed = [item for item in items if item.status == ExperimentStatus.FAIL]
        profitable = [item for item in completed if item.performance and item.performance.net_pnl > 0]

        def group_stats(key_fn: Callable[[ResearchExperimentResult], str]) -> dict[str, Mapping[str, Any]]:
            groups: dict[str, list[ResearchExperimentResult]] = {}
            for item in items:
                groups.setdefault(key_fn(item), []).append(item)
            output: dict[str, Mapping[str, Any]] = {}
            for key, group in sorted(groups.items()):
                finished = [x for x in group if x.performance is not None]
                positive = [x for x in finished if x.performance and x.performance.net_pnl > 0]
                validations = [x for x in finished if x.validation is not None]
                output[key] = {
                    "cases": len(group),
                    "completed": len(finished),
                    "profitable": len(positive),
                    "profitable_fraction": len(positive) / len(finished) if finished else 0.0,
                    "validation_passed": sum(1 for x in validations if x.validation and x.validation.status == ValidationStatus.PASS),
                    "validation_pass_fraction": (
                        sum(1 for x in validations if x.validation and x.validation.status == ValidationStatus.PASS) / len(validations)
                        if validations else 0.0
                    ),
                    "net_pnl": sum(x.performance.net_pnl for x in finished if x.performance),
                }
            return output

        symbols = tuple(sorted({item.spec.dataset.symbol for item in items}))
        intervals = tuple(sorted({item.spec.dataset.interval for item in items}))
        payload = {
            "results": [item.to_dict() for item in items],
            "symbols": symbols,
            "intervals": intervals,
        }
        return CrossMarketResearchSummary(
            total_cases=len(items),
            completed_cases=len(completed),
            passed_cases=len(passed),
            failed_cases=len(failed),
            validation_pass_fraction=len(passed) / len(completed) if completed else 0.0,
            profitable_case_fraction=len(profitable) / len(completed) if completed else 0.0,
            symbols=symbols,
            intervals=intervals,
            by_symbol=group_stats(lambda x: x.spec.dataset.symbol),
            by_interval=group_stats(lambda x: x.spec.dataset.interval),
            evidence_fingerprint=_fingerprint(payload),
        )


def run_experiments(
    specs: Sequence[ResearchExperimentSpec],
    runner: BacktestRunner,
    validation_policy: ResearchValidationPolicy | None = None,
) -> tuple[ResearchExperimentResult, ...]:
    """Convenience wrapper for deterministic experiment coordination."""
    return ResearchExperimentEngine(validation_policy).run(specs, runner)


def summarize_experiments(results: Sequence[ResearchExperimentResult]) -> CrossMarketResearchSummary:
    """Convenience wrapper for cross-market result aggregation."""
    return ResearchExperimentEngine.summarize(results)
