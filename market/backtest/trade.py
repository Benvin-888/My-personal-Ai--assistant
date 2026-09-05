"""APEX / BENVIN hypothetical trade simulation and P&L accounting.

Phase 2.5.4 / 2.5.10 - Trade Simulation, P&L & Point-in-Time Execution

This module converts the Phase 2.5.3 hypothetical position state into
hypothetical trade records and deterministic mark-to-market accounting.
It contains no broker execution, leverage, spread, slippage, transaction
costs, or real account mutation.

Temporal rule:
    A signal is applied only to the current replay frame and all prices used
    for execution are explicit; production orchestration uses the next-bar open while marking uses the current close. Future candles are
    never inspected.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Callable, Iterable

from market.backtest.models import BacktestFrame
from market.backtest.position import PositionSide
from market.backtest.friction import ExecutionFrictionConfig, ExecutionFrictionError, ExecutionFrictionModel
from market.strategy.models import SignalDirection


class TradeSimulationError(ValueError):
    """Raised when trade simulation receives invalid input."""


class TradeAction(str, Enum):
    OPEN = "OPEN"
    HOLD = "HOLD"
    CLOSE = "CLOSE"
    REVERSE = "REVERSE"


@dataclass(frozen=True)
class TradeRecord:
    """A completed hypothetical trade."""

    trade_id: int
    side: PositionSide
    entry_index: int
    entry_timestamp_utc: str
    entry_price: float
    exit_index: int
    exit_timestamp_utc: str
    exit_price: float
    quantity: float
    realized_pnl: float
    gross_pnl: float | None = None
    transaction_costs: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.trade_id, int) or self.trade_id < 1:
            raise TradeSimulationError("trade_id must be a positive integer.")
        if self.side not in (PositionSide.LONG, PositionSide.SHORT):
            raise TradeSimulationError("TradeRecord side must be LONG or SHORT.")
        if not isinstance(self.entry_index, int) or self.entry_index < 0:
            raise TradeSimulationError("entry_index must be non-negative.")
        if not isinstance(self.exit_index, int) or self.exit_index < self.entry_index:
            raise TradeSimulationError("exit_index must be >= entry_index.")
        if not self.entry_timestamp_utc or not self.exit_timestamp_utc:
            raise TradeSimulationError("Trade timestamps must be non-empty.")
        for name, value in (
            ("entry_price", self.entry_price),
            ("exit_price", self.exit_price),
            ("quantity", self.quantity),
            ("realized_pnl", self.realized_pnl),
            ("transaction_costs", self.transaction_costs),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise TradeSimulationError(f"{name} must be finite.")
        if self.entry_price <= 0 or self.exit_price <= 0:
            raise TradeSimulationError("Trade prices must be positive.")
        if self.quantity <= 0:
            raise TradeSimulationError("quantity must be positive.")
        if self.transaction_costs < 0:
            raise TradeSimulationError("transaction_costs must be non-negative.")
        if self.gross_pnl is not None and (not isinstance(self.gross_pnl, (int, float)) or not math.isfinite(self.gross_pnl)):
            raise TradeSimulationError("gross_pnl must be finite when provided.")
        if self.gross_pnl is not None and not math.isclose(self.realized_pnl, self.gross_pnl - self.transaction_costs, rel_tol=0.0, abs_tol=1e-12):
            raise TradeSimulationError("realized_pnl must equal gross_pnl minus transaction_costs.")

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "side": self.side.value,
            "entry_index": self.entry_index,
            "entry_timestamp_utc": self.entry_timestamp_utc,
            "entry_price": self.entry_price,
            "exit_index": self.exit_index,
            "exit_timestamp_utc": self.exit_timestamp_utc,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "realized_pnl": self.realized_pnl,
            "gross_pnl": self.gross_pnl if self.gross_pnl is not None else self.realized_pnl + self.transaction_costs,
            "transaction_costs": self.transaction_costs,
        }


@dataclass(frozen=True)
class TradeEvent:
    """Auditable accounting event generated at an execution frame."""

    index: int
    timestamp_utc: str
    price: float
    action: TradeAction
    from_side: PositionSide
    to_side: PositionSide
    signal: SignalDirection
    realized_pnl_delta: float
    cumulative_realized_pnl: float
    equity: float
    reason: str
    signal_index: int | None = None
    signal_timestamp_utc: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.index, int) or self.index < 0:
            raise TradeSimulationError("index must be non-negative.")
        if not self.timestamp_utc:
            raise TradeSimulationError("timestamp_utc must be non-empty.")
        if not isinstance(self.price, (int, float)) or not math.isfinite(self.price) or self.price <= 0:
            raise TradeSimulationError("price must be positive and finite.")
        if not isinstance(self.action, TradeAction):
            raise TradeSimulationError("action must be TradeAction.")
        if not isinstance(self.from_side, PositionSide) or not isinstance(self.to_side, PositionSide):
            raise TradeSimulationError("from_side and to_side must be PositionSide.")
        if not isinstance(self.signal, SignalDirection):
            raise TradeSimulationError("signal must be SignalDirection.")
        for name, value in (
            ("realized_pnl_delta", self.realized_pnl_delta),
            ("cumulative_realized_pnl", self.cumulative_realized_pnl),
            ("equity", self.equity),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise TradeSimulationError(f"{name} must be finite.")
        if not self.reason:
            raise TradeSimulationError("reason must be non-empty.")
        if self.signal_index is not None:
            if not isinstance(self.signal_index, int) or self.signal_index < 0:
                raise TradeSimulationError("signal_index must be a non-negative integer or None.")
            if self.signal_index > self.index:
                raise TradeSimulationError("signal_index cannot be after execution index.")
        if self.signal_timestamp_utc is not None and (
            not isinstance(self.signal_timestamp_utc, str) or not self.signal_timestamp_utc.strip()
        ):
            raise TradeSimulationError("signal_timestamp_utc must be a non-empty string or None.")
        if self.signal_index is None and self.signal_timestamp_utc is not None:
            raise TradeSimulationError("signal_timestamp_utc requires signal_index.")

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp_utc": self.timestamp_utc,
            "price": self.price,
            "action": self.action.value,
            "from_side": self.from_side.value,
            "to_side": self.to_side.value,
            "signal": self.signal.value,
            "realized_pnl_delta": self.realized_pnl_delta,
            "cumulative_realized_pnl": self.cumulative_realized_pnl,
            "equity": self.equity,
            "reason": self.reason,
            "signal_index": self.signal_index,
            "signal_timestamp_utc": self.signal_timestamp_utc,
        }


@dataclass(frozen=True)
class TradeAccountState:
    """Current hypothetical account state."""

    initial_capital: float
    realized_pnl: float
    unrealized_pnl: float
    equity: float
    position_side: PositionSide
    quantity: float
    gross_pnl: float | None = None
    transaction_costs: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("initial_capital", self.initial_capital),
            ("realized_pnl", self.realized_pnl),
            ("unrealized_pnl", self.unrealized_pnl),
            ("equity", self.equity),
            ("quantity", self.quantity),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise TradeSimulationError(f"{name} must be finite.")
        if self.initial_capital <= 0:
            raise TradeSimulationError("initial_capital must be positive.")
        if self.position_side is PositionSide.FLAT and self.quantity != 0:
            raise TradeSimulationError("FLAT account state must have zero quantity.")
        if self.position_side is not PositionSide.FLAT and self.quantity <= 0:
            raise TradeSimulationError("Open account state must have positive quantity.")
        expected = self.initial_capital + self.realized_pnl + self.unrealized_pnl
        if not math.isclose(self.equity, expected, rel_tol=0.0, abs_tol=1e-12):
            raise TradeSimulationError("equity must equal capital + realized + unrealized P&L.")

    def to_dict(self) -> dict:
        return {
            "initial_capital": self.initial_capital,
            "realized_pnl": self.realized_pnl,
            "gross_pnl": self.gross_pnl if self.gross_pnl is not None else self.realized_pnl + self.transaction_costs,
            "transaction_costs": self.transaction_costs,
            "unrealized_pnl": self.unrealized_pnl,
            "equity": self.equity,
            "position_side": self.position_side.value,
            "quantity": self.quantity,
        }


@dataclass(frozen=True)
class TradeSimulationResult:
    """Complete deterministic result of a trade simulation."""

    initial_capital: float
    final_account: TradeAccountState
    trades: tuple[TradeRecord, ...]
    events: tuple[TradeEvent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.trades, tuple) or not isinstance(self.events, tuple):
            raise TradeSimulationError("trades and events must be tuples.")
        if self.initial_capital <= 0 or not math.isfinite(self.initial_capital):
            raise TradeSimulationError("initial_capital must be positive and finite.")

    def to_dict(self) -> dict:
        return {
            "initial_capital": self.initial_capital,
            "final_account": self.final_account.to_dict(),
            "trades": [trade.to_dict() for trade in self.trades],
            "events": [event.to_dict() for event in self.events],
        }


class TradeSimulator:
    """Deterministic hypothetical trade and P&L simulator.

    Semantics:
      * LONG/SHORT while FLAT opens a fixed-quantity trade.
      * Repeated same-direction signals HOLD the trade.
      * NEUTRAL does not close the position.
      * An opposite signal closes the current trade at the current close and
        immediately opens the opposite hypothetical trade at that same close.
      * P&L is marked from the current frame close.
      * No costs, spread, slippage, leverage, or broker behavior is modeled.
      * An open trade remains open at the end unless ``close_at_end=True``.
    """

    def __init__(self, initial_capital: float = 10_000.0, quantity: float = 1.0, friction: ExecutionFrictionModel | ExecutionFrictionConfig | None = None) -> None:
        self._validate_money(initial_capital, "initial_capital", positive=True)
        self._validate_money(quantity, "quantity", positive=True)
        self.initial_capital = float(initial_capital)
        self.quantity = float(quantity)
        if friction is None:
            self.friction = ExecutionFrictionModel()
        elif isinstance(friction, ExecutionFrictionModel):
            self.friction = friction
        elif isinstance(friction, ExecutionFrictionConfig):
            self.friction = ExecutionFrictionModel(friction)
        else:
            raise TradeSimulationError("friction must be ExecutionFrictionModel, ExecutionFrictionConfig, or None.")
        self.reset()

    @staticmethod
    def _validate_money(value: float, name: str, positive: bool = False) -> None:
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise TradeSimulationError(f"{name} must be finite.")
        if positive and value <= 0:
            raise TradeSimulationError(f"{name} must be positive.")

    @staticmethod
    def _validate_frame(frame: BacktestFrame) -> None:
        if not isinstance(frame, BacktestFrame):
            raise TradeSimulationError("frame must be a BacktestFrame.")
        if not frame.available_candles or frame.candle != frame.available_candles[-1]:
            raise TradeSimulationError("frame must expose the current candle as its final available candle.")
        price = float(frame.candle.close)
        if not math.isfinite(price) or price <= 0:
            raise TradeSimulationError("Current candle close must be positive and finite.")

    @staticmethod
    def _validate_signal(signal: SignalDirection) -> None:
        if not isinstance(signal, SignalDirection):
            raise TradeSimulationError("signal must be a SignalDirection.")

    def reset(self) -> None:
        self._side = PositionSide.FLAT
        self._entry_index: int | None = None
        self._entry_timestamp: str | None = None
        self._entry_price: float | None = None
        self._entry_market_price: float | None = None
        self._entry_transaction_cost: float = 0.0
        self._realized_pnl = 0.0
        self._trades: list[TradeRecord] = []
        self._events: list[TradeEvent] = []
        self._last_index: int | None = None
        self._last_price: float | None = None

    @property
    def account(self) -> TradeAccountState:
        unrealized = self._unrealized(self._last_price) if self._side is not PositionSide.FLAT else 0.0
        return TradeAccountState(
            initial_capital=self.initial_capital,
            realized_pnl=self._realized_pnl,
            unrealized_pnl=unrealized,
            equity=self.initial_capital + self._realized_pnl + unrealized,
            position_side=self._side,
            quantity=self.quantity if self._side is not PositionSide.FLAT else 0.0,
        )

    @property
    def trades(self) -> tuple[TradeRecord, ...]:
        return tuple(self._trades)

    @property
    def events(self) -> tuple[TradeEvent, ...]:
        return tuple(self._events)

    def _unrealized(self, price: float | None) -> float:
        if self._side is PositionSide.FLAT or price is None or self._entry_price is None:
            return 0.0
        try:
            exit_fill = self.friction.fill(price, self.quantity, self._side, is_entry=False)
        except ExecutionFrictionError as exc:
            raise TradeSimulationError(str(exc)) from exc
        if self._side is PositionSide.LONG:
            gross = (exit_fill.execution_price - self._entry_price) * self.quantity
        else:
            gross = (self._entry_price - exit_fill.execution_price) * self.quantity
        return gross - self._entry_transaction_cost - exit_fill.transaction_cost

    def _open(self, frame: BacktestFrame, side: PositionSide, execution_price: float | None = None) -> None:
        self._side = side
        self._entry_index = frame.index
        self._entry_timestamp = frame.candle.timestamp_utc
        try:
            market_price = float(frame.candle.close) if execution_price is None else float(execution_price)
            fill = self.friction.fill(market_price, self.quantity, side, is_entry=True)
        except ExecutionFrictionError as exc:
            raise TradeSimulationError(str(exc)) from exc
        self._entry_price = fill.execution_price
        self._entry_market_price = fill.market_price
        self._entry_transaction_cost = fill.transaction_cost

    def _close(self, frame: BacktestFrame, execution_price: float | None = None) -> float:
        if self._side is PositionSide.FLAT:
            return 0.0
        assert self._entry_index is not None
        assert self._entry_timestamp is not None
        assert self._entry_price is not None
        exit_market_price = float(frame.candle.close) if execution_price is None else float(execution_price)
        try:
            exit_fill = self.friction.fill(exit_market_price, self.quantity, self._side, is_entry=False)
        except ExecutionFrictionError as exc:
            raise TradeSimulationError(str(exc)) from exc
        exit_price = exit_fill.execution_price
        if self._side is PositionSide.LONG:
            gross_pnl = (exit_price - self._entry_price) * self.quantity
        else:
            gross_pnl = (self._entry_price - exit_price) * self.quantity
        total_costs = self._entry_transaction_cost + exit_fill.transaction_cost
        pnl = gross_pnl - total_costs
        record = TradeRecord(
            trade_id=len(self._trades) + 1,
            side=self._side,
            entry_index=self._entry_index,
            entry_timestamp_utc=self._entry_timestamp,
            entry_price=self._entry_price,
            exit_index=frame.index,
            exit_timestamp_utc=frame.candle.timestamp_utc,
            exit_price=exit_price,
            quantity=self.quantity,
            realized_pnl=pnl,
            gross_pnl=gross_pnl,
            transaction_costs=total_costs,
        )
        self._trades.append(record)
        self._realized_pnl += pnl
        self._side = PositionSide.FLAT
        self._entry_index = None
        self._entry_timestamp = None
        self._entry_price = None
        self._entry_market_price = None
        self._entry_transaction_cost = 0.0
        return pnl

    def apply(
        self,
        frame: BacktestFrame,
        signal: SignalDirection,
        *,
        execution_price: float | None = None,
        signal_frame: BacktestFrame | None = None,
    ) -> TradeEvent:
        """Apply one signal at an explicit execution price.

        Account equity is marked to the execution frame close, while ``price``
        in the emitted event records the market price used for the trade action.

        ``signal_frame`` records when the decision was generated. When omitted,
        the signal is treated as same-frame for backwards-compatible direct
        simulator use. The orchestration layer uses the next-bar execution
        policy and supplies the prior signal frame explicitly.
        """
        self._validate_frame(frame)
        self._validate_signal(signal)
        if self._last_index is not None and frame.index <= self._last_index:
            raise TradeSimulationError("frames must be supplied in strictly increasing index order.")

        price = float(frame.candle.close)
        timestamp = frame.candle.timestamp_utc
        if execution_price is None:
            execution_price = price
        if not isinstance(execution_price, (int, float)) or isinstance(execution_price, bool) or not math.isfinite(float(execution_price)) or float(execution_price) <= 0:
            raise TradeSimulationError("execution_price must be positive and finite.")
        signal_index = frame.index if signal_frame is None else signal_frame.index
        signal_timestamp = timestamp if signal_frame is None else signal_frame.candle.timestamp_utc
        if signal_frame is not None:
            self._validate_frame(signal_frame)
            if signal_frame.index > frame.index:
                raise TradeSimulationError("signal_frame cannot be after execution frame.")
        from_side = self._side
        realized_delta = 0.0

        if signal is SignalDirection.LONG:
            if self._side is PositionSide.FLAT:
                self._open(frame, PositionSide.LONG, execution_price)
                action = TradeAction.OPEN
                reason = "LONG signal opened a hypothetical long trade."
            elif self._side is PositionSide.LONG:
                action = TradeAction.HOLD
                reason = "Repeated LONG signal maintained the hypothetical long trade."
            else:
                realized_delta = self._close(frame, execution_price)
                self._open(frame, PositionSide.LONG, execution_price)
                action = TradeAction.REVERSE
                reason = "Opposite LONG signal closed the short trade and opened a hypothetical long trade."
        elif signal is SignalDirection.SHORT:
            if self._side is PositionSide.FLAT:
                self._open(frame, PositionSide.SHORT, execution_price)
                action = TradeAction.OPEN
                reason = "SHORT signal opened a hypothetical short trade."
            elif self._side is PositionSide.SHORT:
                action = TradeAction.HOLD
                reason = "Repeated SHORT signal maintained the hypothetical short trade."
            else:
                realized_delta = self._close(frame, execution_price)
                self._open(frame, PositionSide.SHORT, execution_price)
                action = TradeAction.REVERSE
                reason = "Opposite SHORT signal closed the long trade and opened a hypothetical short trade."
        else:
            action = TradeAction.HOLD
            reason = "NEUTRAL signal did not close or change the hypothetical trade."

        self._last_index = frame.index
        self._last_price = price
        unrealized = self._unrealized(price)
        equity = self.initial_capital + self._realized_pnl + unrealized
        event = TradeEvent(
            index=frame.index,
            timestamp_utc=timestamp,
            price=float(execution_price),
            action=action,
            from_side=from_side,
            to_side=self._side,
            signal=signal,
            realized_pnl_delta=realized_delta,
            cumulative_realized_pnl=self._realized_pnl,
            equity=equity,
            reason=reason,
            signal_index=signal_index,
            signal_timestamp_utc=signal_timestamp,
        )
        self._events.append(event)
        return event

    def close(self, frame: BacktestFrame) -> TradeEvent:
        """Explicitly liquidate the current hypothetical position at frame close."""
        self._validate_frame(frame)
        if self._last_index is not None and frame.index < self._last_index:
            raise TradeSimulationError("close frame cannot precede the latest processed frame.")
        if self._side is PositionSide.FLAT:
            raise TradeSimulationError("No open position to close.")
        realized_delta = self._close(frame)
        self._last_index = frame.index
        self._last_price = float(frame.candle.close)
        # The previous side is needed for auditability; reconstruct it from the closed trade.
        closed_side = self._trades[-1].side
        event = TradeEvent(
            index=frame.index,
            timestamp_utc=frame.candle.timestamp_utc,
            price=self._last_price,
            action=TradeAction.CLOSE,
            from_side=closed_side,
            to_side=PositionSide.FLAT,
            signal=SignalDirection.NEUTRAL,
            realized_pnl_delta=realized_delta,
            cumulative_realized_pnl=self._realized_pnl,
            equity=self.initial_capital + self._realized_pnl,
            reason="Explicit liquidation closed the hypothetical position at the current frame close.",
        )
        self._events.append(event)
        return event

    def simulate(
        self,
        frames: Iterable[BacktestFrame],
        signal_provider: Callable[[BacktestFrame], SignalDirection],
        *,
        close_at_end: bool = False,
    ) -> TradeSimulationResult:
        """Replay frames and apply one signal per frame using each frame close.

        This low-level API intentionally preserves same-frame semantics for direct
        unit testing. Production backtest orchestration uses the explicit
        next-bar execution policy in ``BacktestConfig``.

        If ``close_at_end`` is true, the final open position is explicitly
        liquidated at the final processed frame close.
        """
        if not callable(signal_provider):
            raise TradeSimulationError("signal_provider must be callable.")
        if not isinstance(close_at_end, bool):
            raise TradeSimulationError("close_at_end must be bool.")

        self.reset()
        last_frame: BacktestFrame | None = None
        for frame in frames:
            self.apply(frame, signal_provider(frame))
            last_frame = frame

        if close_at_end and last_frame is not None and self._side is not PositionSide.FLAT:
            self.close(last_frame)

        return TradeSimulationResult(
            initial_capital=self.initial_capital,
            final_account=self.account,
            trades=self.trades,
            events=self.events,
        )
