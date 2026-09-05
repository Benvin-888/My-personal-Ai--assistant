"""APEX / BENVIN deterministic backtest orchestration.

Phase 2.5.8 / 2.5.10 - Backtest Orchestration & Point-in-Time Execution

Connects the existing replay, trade simulation, and reporting layers into one
controlled backtest workflow. The orchestrator does not implement strategy
logic, optimize parameters, place orders, or mutate live accounts.
"""
from __future__ import annotations

from typing import Callable

from market.backtest.models import BacktestDataset, BacktestFrame, BacktestRunMetadata, ExecutionTiming
from market.backtest.replay import HistoricalReplayEngine, HistoricalReplayError
from market.backtest.reporting import BacktestReport, BacktestReportingError, build_report
from market.backtest.trade import TradeSimulationResult, TradeSimulator, TradeSimulationError
from market.strategy.models import SignalDirection


class BacktestOrchestrationError(ValueError):
    """Raised when an orchestration request is invalid."""


SignalProvider = Callable[[BacktestFrame], SignalDirection]


class BacktestOrchestrator:
    """Run the deterministic backtest pipeline without owning strategy logic.

    The caller supplies a signal provider. During configured warmup candles the
    provider is not called. Signals generated from a completed candle are queued
    and executed on the next bar open, preventing same-bar-close look-ahead bias.
    """

    def __init__(self, trade_simulator: TradeSimulator | None = None) -> None:
        if trade_simulator is not None and not isinstance(trade_simulator, TradeSimulator):
            raise BacktestOrchestrationError("trade_simulator must be TradeSimulator or None.")
        self.trade_simulator = trade_simulator

    @staticmethod
    def _validate_inputs(
        dataset: BacktestDataset,
        run_metadata: BacktestRunMetadata,
        signal_provider: SignalProvider,
    ) -> None:
        if not isinstance(dataset, BacktestDataset):
            raise BacktestOrchestrationError("dataset must be a BacktestDataset.")
        if not isinstance(run_metadata, BacktestRunMetadata):
            raise BacktestOrchestrationError("run_metadata must be a BacktestRunMetadata.")
        if not callable(signal_provider):
            raise BacktestOrchestrationError("signal_provider must be callable.")
        if dataset.pair != run_metadata.config.pair:
            raise BacktestOrchestrationError("dataset pair must match run metadata pair.")
        if dataset.interval != run_metadata.config.interval:
            raise BacktestOrchestrationError("dataset interval must match run metadata interval.")

    @staticmethod
    def _validate_signal(signal: SignalDirection) -> None:
        if not isinstance(signal, SignalDirection):
            raise BacktestOrchestrationError("signal_provider must return SignalDirection.")

    def run(
        self,
        dataset: BacktestDataset,
        run_metadata: BacktestRunMetadata,
        signal_provider: SignalProvider,
        *,
        close_at_end: bool = False,
    ) -> BacktestReport:
        """Replay a dataset, simulate signals, and aggregate a final report."""
        self._validate_inputs(dataset, run_metadata, signal_provider)
        if not isinstance(close_at_end, bool):
            raise BacktestOrchestrationError("close_at_end must be a boolean.")

        simulator = self.trade_simulator
        if simulator is None:
            simulator = TradeSimulator(initial_capital=run_metadata.config.initial_capital)
        elif simulator.initial_capital != run_metadata.config.initial_capital:
            raise BacktestOrchestrationError("trade simulator capital must match run metadata capital.")

        replay = HistoricalReplayEngine(run_metadata.config)

        def signal_for_frame(frame: BacktestFrame) -> SignalDirection:
            if not replay.is_warmup_complete(frame):
                return SignalDirection.NEUTRAL
            try:
                signal = signal_provider(frame)
            except Exception as exc:
                raise BacktestOrchestrationError(
                    f"signal_provider failed at frame {frame.index}: {exc}"
                ) from exc
            self._validate_signal(signal)
            return signal

        try:
            frames = iter(replay.frames(dataset))
            previous_frame: BacktestFrame | None = None
            pending_signal: SignalDirection | None = None

            for frame in frames:
                # A completed bar is analyzed first. Its decision can only be
                # executed on a later bar. This is the core point-in-time rule.
                if previous_frame is None:
                    simulator.apply(frame, SignalDirection.NEUTRAL)
                else:
                    assert pending_signal is not None
                    if run_metadata.config.execution_timing is ExecutionTiming.NEXT_BAR_OPEN:
                        simulator.apply(
                            frame,
                            pending_signal,
                            execution_price=float(frame.candle.open),
                            signal_frame=previous_frame,
                        )
                    else:  # pragma: no cover - protected by BacktestConfig validation
                        raise BacktestOrchestrationError(
                            f"Unsupported execution timing: {run_metadata.config.execution_timing}"
                        )

                previous_frame = frame
                pending_signal = signal_for_frame(frame)

            if close_at_end and previous_frame is not None and simulator.account.position_side.value != "FLAT":
                simulator.close(previous_frame)

            simulation = TradeSimulationResult(
                initial_capital=simulator.initial_capital,
                final_account=simulator.account,
                trades=simulator.trades,
                events=simulator.events,
            )
        except (TradeSimulationError, HistoricalReplayError) as exc:
            raise BacktestOrchestrationError(str(exc)) from exc

        try:
            return build_report(run_metadata, simulation)
        except BacktestReportingError as exc:
            raise BacktestOrchestrationError(str(exc)) from exc


def run_backtest(
    dataset: BacktestDataset,
    run_metadata: BacktestRunMetadata,
    signal_provider: SignalProvider,
    *,
    close_at_end: bool = False,
    trade_simulator: TradeSimulator | None = None,
) -> BacktestReport:
    """Convenience API for one deterministic backtest run."""
    return BacktestOrchestrator(trade_simulator).run(
        dataset,
        run_metadata,
        signal_provider,
        close_at_end=close_at_end,
    )
