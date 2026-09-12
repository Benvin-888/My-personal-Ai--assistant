"""APEX / BENVIN temporal and scenario robustness research foundation.

Phase 2.12 - Temporal & Execution Robustness Foundation

Adds time-based walk-forward evaluation and explicit robustness scenario
contracts. The module coordinates already-computed backtest/research results;
it does not fetch data, optimize parameters, access brokers, or authorize
execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any, Callable, Mapping, Sequence

from .engine import ResearchPerformance, StrategyResearchEngine, StrategyResearchReport
from .experiment import ResearchExperimentSpec


class ResearchRobustnessError(ValueError):
    """Raised when a robustness specification or result is invalid."""


class RobustnessStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _timestamp(value: str | None) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ResearchRobustnessError("trade opportunity timestamps are required for time-based walk-forward")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ResearchRobustnessError(f"invalid ISO timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ResearchRobustnessError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class TimeWalkForwardWindow:
    """One chronological time-based train/test window."""

    window_id: int
    train_start_utc: str
    train_end_utc: str
    test_start_utc: str
    test_end_utc: str
    train_trade_count: int
    test_trade_count: int
    train: ResearchPerformance
    test: ResearchPerformance

    def __post_init__(self) -> None:
        if self.window_id < 1:
            raise ResearchRobustnessError("window_id must be positive")
        if self.train_trade_count < 1 or self.test_trade_count < 1:
            raise ResearchRobustnessError("train and test trade counts must be positive")

    @property
    def test_profitable(self) -> bool:
        return self.test.net_pnl > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "train_start_utc": self.train_start_utc,
            "train_end_utc": self.train_end_utc,
            "test_start_utc": self.test_start_utc,
            "test_end_utc": self.test_end_utc,
            "train_trade_count": self.train_trade_count,
            "test_trade_count": self.test_trade_count,
            "train": self.train.to_dict(),
            "test": self.test.to_dict(),
        }


@dataclass(frozen=True)
class TimeWalkForwardResult:
    """Aggregate result for chronological time-based walk-forward analysis."""

    train_days: int
    test_days: int
    step_days: int
    windows: tuple[TimeWalkForwardWindow, ...]
    profitable_test_window_fraction: float
    mean_test_return_pct: float
    median_test_return_pct: float
    evidence_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "train_days": self.train_days,
            "test_days": self.test_days,
            "step_days": self.step_days,
            "windows": [window.to_dict() for window in self.windows],
            "profitable_test_window_fraction": self.profitable_test_window_fraction,
            "mean_test_return_pct": self.mean_test_return_pct,
            "median_test_return_pct": self.median_test_return_pct,
            "evidence_fingerprint": self.evidence_fingerprint,
        }


@dataclass(frozen=True)
class RobustnessScenarioSpec:
    """Explicit economic/execution perturbation applied by an external runner."""

    scenario_id: str
    description: str
    transaction_cost_multiplier: float = 1.0
    slippage_multiplier: float = 1.0
    risk_fraction_multiplier: float = 1.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ResearchRobustnessError("scenario_id must be a non-empty string")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ResearchRobustnessError("description must be a non-empty string")
        for name in ("transaction_cost_multiplier", "slippage_multiplier", "risk_fraction_multiplier"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
                raise ResearchRobustnessError(f"{name} must be finite and non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "description": self.description,
            "transaction_cost_multiplier": self.transaction_cost_multiplier,
            "slippage_multiplier": self.slippage_multiplier,
            "risk_fraction_multiplier": self.risk_fraction_multiplier,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RobustnessScenarioResult:
    """Auditable result for one externally executed robustness scenario."""

    spec: RobustnessScenarioSpec
    status: RobustnessStatus
    performance: ResearchPerformance | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status == RobustnessStatus.PASS and self.performance is None:
            raise ResearchRobustnessError("PASS scenario requires performance")
        if self.status == RobustnessStatus.ERROR and not self.error:
            raise ResearchRobustnessError("ERROR scenario requires error text")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.spec.to_dict(),
            "status": self.status.value,
            "performance": self.performance.to_dict() if self.performance else None,
            "error": self.error,
        }

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


@dataclass(frozen=True)
class RobustnessScenarioSummary:
    """Summary of supplied scenario outcomes without choosing a winner."""

    total_scenarios: int
    completed_scenarios: int
    profitable_scenarios: int
    profitable_fraction: float
    baseline_net_pnl: float | None
    worst_net_pnl: float | None
    best_net_pnl: float | None
    net_pnl_range: float | None
    scenarios: tuple[RobustnessScenarioResult, ...]
    evidence_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_scenarios": self.total_scenarios,
            "completed_scenarios": self.completed_scenarios,
            "profitable_scenarios": self.profitable_scenarios,
            "profitable_fraction": self.profitable_fraction,
            "baseline_net_pnl": self.baseline_net_pnl,
            "worst_net_pnl": self.worst_net_pnl,
            "best_net_pnl": self.best_net_pnl,
            "net_pnl_range": self.net_pnl_range,
            "scenarios": [item.to_dict() for item in self.scenarios],
            "evidence_fingerprint": self.evidence_fingerprint,
        }


ScenarioRunner = Callable[[ResearchExperimentSpec, RobustnessScenarioSpec], ResearchPerformance]


class ResearchRobustnessEngine:
    """Perform temporal robustness analysis and coordinate scenario runs."""

    def __init__(self) -> None:
        self._research = StrategyResearchEngine()

    def time_walk_forward(
        self,
        result: Any,
        *,
        train_days: int = 90,
        test_days: int = 30,
        step_days: int | None = None,
    ) -> TimeWalkForwardResult:
        """Evaluate chronological windows using calendar time, not trade count."""
        if train_days < 1 or test_days < 1:
            raise ResearchRobustnessError("train_days and test_days must be positive")
        step = test_days if step_days is None else step_days
        if step < 1:
            raise ResearchRobustnessError("step_days must be positive")
        trades = tuple(result.trades)
        if not trades:
            raise ResearchRobustnessError("at least one trade is required")
        stamped = [(trade, _timestamp(trade.opportunity_timestamp_utc)) for trade in trades]
        stamped.sort(key=lambda item: (item[1], item[0].trade_id))
        first = stamped[0][1]
        last = stamped[-1][1]
        windows: list[TimeWalkForwardWindow] = []
        cursor = first
        window_id = 1
        while cursor + timedelta(days=train_days + test_days) <= last:
            train_end = cursor + timedelta(days=train_days)
            test_end = train_end + timedelta(days=test_days)
            train_trades = tuple(trade for trade, ts in stamped if cursor <= ts < train_end)
            test_trades = tuple(trade for trade, ts in stamped if train_end <= ts < test_end)
            if train_trades and test_trades:
                train_result = self._research._subset_result(result, train_trades)
                test_result = self._research._subset_result(result, test_trades, initial_capital=train_result.final_equity)
                windows.append(TimeWalkForwardWindow(
                    window_id=window_id,
                    train_start_utc=cursor.isoformat(),
                    train_end_utc=train_end.isoformat(),
                    test_start_utc=train_end.isoformat(),
                    test_end_utc=test_end.isoformat(),
                    train_trade_count=len(train_trades),
                    test_trade_count=len(test_trades),
                    train=self._research.performance(train_result),
                    test=self._research.performance(test_result),
                ))
                window_id += 1
            cursor += timedelta(days=step)
        if not windows:
            raise ResearchRobustnessError("insufficient timestamp coverage for requested time-based windows")
        returns = sorted(window.test.total_return_pct for window in windows)
        midpoint = len(returns) // 2
        median = returns[midpoint] if len(returns) % 2 else (returns[midpoint - 1] + returns[midpoint]) / 2.0
        payload = {
            "train_days": train_days,
            "test_days": test_days,
            "step_days": step,
            "windows": [window.to_dict() for window in windows],
        }
        return TimeWalkForwardResult(
            train_days=train_days,
            test_days=test_days,
            step_days=step,
            windows=tuple(windows),
            profitable_test_window_fraction=sum(window.test_profitable for window in windows) / len(windows),
            mean_test_return_pct=sum(returns) / len(returns),
            median_test_return_pct=median,
            evidence_fingerprint=_fingerprint(payload),
        )

    def run_scenarios(
        self,
        spec: ResearchExperimentSpec,
        scenarios: Sequence[RobustnessScenarioSpec],
        runner: ScenarioRunner,
    ) -> tuple[RobustnessScenarioResult, ...]:
        if not isinstance(spec, ResearchExperimentSpec):
            raise ResearchRobustnessError("spec must be a ResearchExperimentSpec")
        items = tuple(scenarios)
        if not items:
            raise ResearchRobustnessError("at least one scenario is required")
        if not callable(runner):
            raise ResearchRobustnessError("runner must be callable")
        ids: set[str] = set()
        results: list[RobustnessScenarioResult] = []
        for scenario in items:
            if scenario.scenario_id in ids:
                raise ResearchRobustnessError(f"duplicate scenario_id: {scenario.scenario_id}")
            ids.add(scenario.scenario_id)
            try:
                performance = runner(spec, scenario)
                if not isinstance(performance, ResearchPerformance):
                    raise ResearchRobustnessError("scenario runner must return ResearchPerformance")
                results.append(RobustnessScenarioResult(scenario, RobustnessStatus.PASS, performance=performance))
            except Exception as exc:
                results.append(RobustnessScenarioResult(scenario, RobustnessStatus.ERROR, error=f"{type(exc).__name__}: {exc}"))
        return tuple(results)

    @staticmethod
    def summarize_scenarios(results: Sequence[RobustnessScenarioResult]) -> RobustnessScenarioSummary:
        items = tuple(results)
        if not items:
            raise ResearchRobustnessError("at least one scenario result is required")
        if any(not isinstance(item, RobustnessScenarioResult) for item in items):
            raise ResearchRobustnessError("all results must be RobustnessScenarioResult instances")
        completed = [item for item in items if item.performance is not None]
        pnl = [item.performance.net_pnl for item in completed if item.performance]
        profitable = sum(value > 0 for value in pnl)
        baseline = next((item.performance.net_pnl for item in completed if item.spec.scenario_id.lower() == "baseline"), None)
        payload = [item.to_dict() for item in items]
        return RobustnessScenarioSummary(
            total_scenarios=len(items),
            completed_scenarios=len(completed),
            profitable_scenarios=profitable,
            profitable_fraction=profitable / len(completed) if completed else 0.0,
            baseline_net_pnl=baseline,
            worst_net_pnl=min(pnl) if pnl else None,
            best_net_pnl=max(pnl) if pnl else None,
            net_pnl_range=(max(pnl) - min(pnl)) if pnl else None,
            scenarios=items,
            evidence_fingerprint=_fingerprint(payload),
        )


def time_walk_forward(result: Any, **kwargs: Any) -> TimeWalkForwardResult:
    return ResearchRobustnessEngine().time_walk_forward(result, **kwargs)


def summarize_scenarios(results: Sequence[RobustnessScenarioResult]) -> RobustnessScenarioSummary:
    return ResearchRobustnessEngine.summarize_scenarios(results)
