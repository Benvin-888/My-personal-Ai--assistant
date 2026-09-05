"""APEX / BENVIN deterministic backtest integrity validation.

Phase 2.5.9 - Backtest Validation & Integrity Engine

Audits a completed BacktestReport for internal consistency, chronology,
point-in-time integrity, and deterministic serialization. This layer is
measurement/audit only. It does not modify results, change strategy behavior,
optimize parameters, or execute orders.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any

from market.backtest.metrics import calculate_performance
from market.backtest.position import PositionSide
from market.backtest.reporting import BacktestReport
from market.strategy.models import SignalDirection


class BacktestValidationError(ValueError):
    """Raised when validation receives an object that cannot be audited."""


class BacktestValidationStatus(str, Enum):
    """Stable validation outcome."""

    PASSED = "PASSED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class BacktestValidationCheck:
    """One deterministic integrity check result."""

    name: str
    passed: bool
    details: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise BacktestValidationError("check name must be non-empty.")
        if not isinstance(self.passed, bool):
            raise BacktestValidationError("check passed must be boolean.")
        if not isinstance(self.details, str) or not self.details.strip():
            raise BacktestValidationError("check details must be non-empty.")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "details": self.details}


@dataclass(frozen=True)
class BacktestValidationResult:
    """Immutable audit result for one completed backtest report."""

    status: BacktestValidationStatus
    checks: tuple[BacktestValidationCheck, ...]
    passed_checks: int
    failed_checks: int
    errors: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.status, BacktestValidationStatus):
            raise BacktestValidationError("status must be BacktestValidationStatus.")
        if not isinstance(self.checks, tuple):
            raise BacktestValidationError("checks must be a tuple.")
        if not isinstance(self.errors, tuple):
            raise BacktestValidationError("errors must be a tuple.")
        if any(not isinstance(check, BacktestValidationCheck) for check in self.checks):
            raise BacktestValidationError("checks must contain BacktestValidationCheck values.")
        if any(not isinstance(error, str) or not error.strip() for error in self.errors):
            raise BacktestValidationError("errors must contain non-empty strings.")
        if not isinstance(self.passed_checks, int) or self.passed_checks < 0:
            raise BacktestValidationError("passed_checks must be a non-negative integer.")
        if not isinstance(self.failed_checks, int) or self.failed_checks < 0:
            raise BacktestValidationError("failed_checks must be a non-negative integer.")
        if self.passed_checks + self.failed_checks != len(self.checks):
            raise BacktestValidationError("check counts must match checks length.")
        expected_status = (
            BacktestValidationStatus.PASSED
            if self.failed_checks == 0 and not self.errors
            else BacktestValidationStatus.FAILED
        )
        if self.status is not expected_status:
            raise BacktestValidationError("status does not match validation outcome.")

    @property
    def passed(self) -> bool:
        """Return True only when the complete audit passed."""
        return self.status is BacktestValidationStatus.PASSED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "errors": list(self.errors),
        }


class BacktestIntegrityValidator:
    """Audit a BacktestReport without changing it."""

    @staticmethod
    def _check(name: str, passed: bool, details: str) -> BacktestValidationCheck:
        return BacktestValidationCheck(name=name, passed=bool(passed), details=details)

    def validate(self, report: BacktestReport) -> BacktestValidationResult:
        if not isinstance(report, BacktestReport):
            raise BacktestValidationError("report must be a BacktestReport.")

        checks: list[BacktestValidationCheck] = []
        errors: list[str] = []

        def add(name: str, passed: bool, details: str) -> None:
            checks.append(self._check(name, passed, details))

        simulation = report.simulation
        metadata = report.run_metadata
        config = metadata.config

        add(
            "capital_identity",
            math.isclose(
                float(config.initial_capital),
                float(simulation.initial_capital),
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            "Run configuration capital matches simulation capital.",
        )

        event_indices = [event.index for event in simulation.events]
        event_index_set = set(event_indices)
        chronological = all(
            current >= previous
            for previous, current in zip(event_indices, event_indices[1:])
        )
        add(
            "event_chronology",
            chronological,
            "Simulation event indices are non-decreasing.",
        )

        add(
            "dataset_coverage",
            len(event_index_set) <= metadata.dataset_candle_count,
            "Distinct simulated frame indices do not exceed the declared dataset candle count.",
        )

        final_equity_matches = True
        if simulation.events:
            final_equity_matches = math.isclose(
                float(simulation.final_account.equity),
                float(simulation.events[-1].equity),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        add(
            "final_equity_consistency",
            final_equity_matches,
            "Final account equity matches the last simulation event when events exist.",
        )

        performance_matches = False
        try:
            performance_matches = report.performance == calculate_performance(simulation)
        except Exception as exc:  # pragma: no cover - defensive boundary
            errors.append(f"performance recalculation failed: {exc}")
        add(
            "performance_consistency",
            performance_matches,
            "Reported performance exactly matches a fresh deterministic calculation.",
        )

        equity_curve_matches = len(report.equity_curve) == len(simulation.events)
        if equity_curve_matches:
            for point, event in zip(report.equity_curve, simulation.events):
                if (
                    point.index != event.index
                    or point.timestamp_utc != event.timestamp_utc
                    or not math.isclose(point.equity, event.equity, rel_tol=0.0, abs_tol=1e-12)
                    or not math.isclose(
                        point.cumulative_realized_pnl,
                        event.cumulative_realized_pnl,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                    or point.position_side is not event.to_side
                ):
                    equity_curve_matches = False
                    break
        add(
            "equity_curve_consistency",
            equity_curve_matches,
            "Equity curve points exactly match the simulation event timeline.",
        )

        trade_ids = [trade.trade_id for trade in simulation.trades]
        unique_trade_ids = len(trade_ids) == len(set(trade_ids))
        add(
            "trade_id_uniqueness",
            unique_trade_ids,
            "Trade identifiers are unique.",
        )

        trades_chronological = True
        previous_exit = -1
        for trade in simulation.trades:
            if trade.entry_index < previous_exit or trade.exit_index < trade.entry_index:
                trades_chronological = False
                break
            if trade.entry_index not in event_index_set or trade.exit_index not in event_index_set:
                trades_chronological = False
                break
            previous_exit = trade.exit_index
        add(
            "trade_point_in_time_integrity",
            trades_chronological,
            "Trade entry/exit indices are chronological and reference replayed frames only.",
        )

        signal_timing_consistent = True
        timing_details = "Signal metadata is point-in-time consistent with execution frames."
        for event in simulation.events:
            if event.signal_index is not None and event.signal_index > event.index:
                signal_timing_consistent = False
                timing_details = "An event references a signal generated after its execution frame."
                break
            if event.signal_index is not None and event.signal_timestamp_utc is None:
                signal_timing_consistent = False
                timing_details = "An event has signal_index without signal_timestamp_utc."
                break
            if (
                config.execution_timing.value == "NEXT_BAR_OPEN"
                and event.signal not in (SignalDirection.NEUTRAL,)
                and event.signal_index != event.index - 1
            ):
                signal_timing_consistent = False
                timing_details = "A directional signal was executed without the required one-bar delay."
                break
        add("signal_execution_timing", signal_timing_consistent, timing_details)

        pnl_consistent = True
        for trade in simulation.trades:
            if trade.gross_pnl is not None and not math.isclose(
                float(trade.realized_pnl),
                float(trade.gross_pnl) - float(trade.transaction_costs),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                pnl_consistent = False
                break
        add(
            "trade_pnl_consistency",
            pnl_consistent,
            "Trade realized P&L is consistent with gross P&L and transaction costs.",
        )

        exposure_consistent = (
            report.performance.exposure_events
            == report.performance.long_exposure_events + report.performance.short_exposure_events
            and report.performance.exposure_events
            + report.performance.neutral_or_flat_events
            == len(simulation.events)
        )
        add(
            "exposure_accounting",
            exposure_consistent,
            "Performance exposure counts reconcile to the simulation event count.",
        )

        serialization_deterministic = report.to_dict() == report.to_dict()
        add(
            "serialization_determinism",
            serialization_deterministic,
            "Repeated report serialization produces identical output.",
        )

        passed_checks = sum(1 for check in checks if check.passed)
        failed_checks = len(checks) - passed_checks
        status = (
            BacktestValidationStatus.PASSED
            if failed_checks == 0 and not errors
            else BacktestValidationStatus.FAILED
        )

        return BacktestValidationResult(
            status=status,
            checks=tuple(checks),
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            errors=tuple(errors),
        )


def validate_backtest(report: BacktestReport) -> BacktestValidationResult:
    """Convenience API for deterministic backtest integrity validation."""
    return BacktestIntegrityValidator().validate(report)
