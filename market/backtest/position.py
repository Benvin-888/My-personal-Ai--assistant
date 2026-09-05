"""APEX / BENVIN hypothetical signal-to-position simulation.

Phase 2.5.3 - Signal & Position Simulation

This module converts a deterministic strategy/ensemble signal into a
hypothetical position state. It deliberately contains no broker execution,
orders, position sizing, leverage, transaction costs, spread, slippage, P&L,
or account mutation.

Temporal rule:
    A signal is applied only to the current replay frame. The simulator
    never reads future candles.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Callable, Iterable, Iterator

from market.backtest.models import BacktestFrame
from market.strategy.models import SignalDirection


class PositionSimulationError(ValueError):
    """Raised when position simulation receives invalid input."""


class PositionSide(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


class PositionAction(str, Enum):
    HOLD = "HOLD"
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    REVERSE = "REVERSE"


@dataclass(frozen=True)
class PositionState:
    """Current hypothetical position state.

    No quantity, leverage, P&L, or account information is represented.
    """

    side: PositionSide = PositionSide.FLAT
    entry_timestamp_utc: str | None = None
    entry_price: float | None = None
    last_signal: SignalDirection = SignalDirection.NEUTRAL
    last_signal_timestamp_utc: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.side, PositionSide):
            raise PositionSimulationError("side must be PositionSide.")
        if not isinstance(self.last_signal, SignalDirection):
            raise PositionSimulationError("last_signal must be SignalDirection.")

        if self.side is PositionSide.FLAT:
            if self.entry_timestamp_utc is not None or self.entry_price is not None:
                raise PositionSimulationError(
                    "A FLAT position cannot contain entry information."
                )
        else:
            if not self.entry_timestamp_utc:
                raise PositionSimulationError(
                    "An active position requires entry_timestamp_utc."
                )
            if self.entry_price is None or not math.isfinite(self.entry_price):
                raise PositionSimulationError(
                    "An active position requires a finite entry_price."
                )
            if self.entry_price <= 0:
                raise PositionSimulationError("entry_price must be positive.")

    @property
    def is_open(self) -> bool:
        return self.side is not PositionSide.FLAT

    def to_dict(self) -> dict:
        return {
            "side": self.side.value,
            "entry_timestamp_utc": self.entry_timestamp_utc,
            "entry_price": self.entry_price,
            "last_signal": self.last_signal.value,
            "last_signal_timestamp_utc": self.last_signal_timestamp_utc,
        }


@dataclass(frozen=True)
class PositionEvent:
    """Auditable state transition caused by one current-frame signal."""

    index: int
    timestamp_utc: str
    price: float
    action: PositionAction
    from_side: PositionSide
    to_side: PositionSide
    signal: SignalDirection
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.index, int) or self.index < 0:
            raise PositionSimulationError("index must be a non-negative integer.")
        if not self.timestamp_utc:
            raise PositionSimulationError("timestamp_utc must be non-empty.")
        if not isinstance(self.price, (int, float)) or not math.isfinite(self.price):
            raise PositionSimulationError("price must be finite.")
        if self.price <= 0:
            raise PositionSimulationError("price must be positive.")
        if not isinstance(self.action, PositionAction):
            raise PositionSimulationError("action must be PositionAction.")
        if not isinstance(self.from_side, PositionSide):
            raise PositionSimulationError("from_side must be PositionSide.")
        if not isinstance(self.to_side, PositionSide):
            raise PositionSimulationError("to_side must be PositionSide.")
        if not isinstance(self.signal, SignalDirection):
            raise PositionSimulationError("signal must be SignalDirection.")
        if not self.reason:
            raise PositionSimulationError("reason must be non-empty.")

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp_utc": self.timestamp_utc,
            "price": self.price,
            "action": self.action.value,
            "from_side": self.from_side.value,
            "to_side": self.to_side.value,
            "signal": self.signal.value,
            "reason": self.reason,
        }


class PositionSimulator:
    """Deterministic hypothetical position state machine.

    Semantics:
      * LONG opens a long position when FLAT.
      * SHORT opens a short position when FLAT.
      * Repeated same-direction signals HOLD.
      * NEUTRAL never closes an existing position.
      * An opposite directional signal REVERSES the position at the
        current frame's price.
      * Every transition uses only the supplied current frame.
    """

    def __init__(self) -> None:
        self._state = PositionState()
        self._events: list[PositionEvent] = []

    @property
    def state(self) -> PositionState:
        return self._state

    @property
    def events(self) -> tuple[PositionEvent, ...]:
        return tuple(self._events)

    def reset(self) -> None:
        self._state = PositionState()
        self._events.clear()

    @staticmethod
    def _validate_frame(frame: BacktestFrame) -> None:
        if not isinstance(frame, BacktestFrame):
            raise PositionSimulationError("frame must be a BacktestFrame.")
        if not frame.available_candles:
            raise PositionSimulationError("frame must contain available candles.")
        if frame.candle != frame.available_candles[-1]:
            raise PositionSimulationError(
                "frame must expose the current candle as its final available candle."
            )

    @staticmethod
    def _validate_signal(signal: SignalDirection) -> None:
        if not isinstance(signal, SignalDirection):
            raise PositionSimulationError(
                "signal must be a SignalDirection."
            )

    def apply(self, frame: BacktestFrame, signal: SignalDirection) -> PositionEvent:
        """Apply one signal using only the current replay frame's close price."""
        self._validate_frame(frame)
        self._validate_signal(signal)

        candle = frame.candle
        price = float(candle.close)
        if not math.isfinite(price) or price <= 0:
            raise PositionSimulationError("Current candle close must be positive and finite.")

        current = self._state
        timestamp = candle.timestamp_utc

        if signal is SignalDirection.LONG:
            if current.side is PositionSide.FLAT:
                new_state = PositionState(
                    side=PositionSide.LONG,
                    entry_timestamp_utc=timestamp,
                    entry_price=price,
                    last_signal=signal,
                    last_signal_timestamp_utc=timestamp,
                )
                event = PositionEvent(
                    frame.index, timestamp, price, PositionAction.OPEN,
                    PositionSide.FLAT, PositionSide.LONG, signal,
                    "LONG signal opened a hypothetical long position.",
                )
            elif current.side is PositionSide.LONG:
                new_state = PositionState(
                    side=PositionSide.LONG,
                    entry_timestamp_utc=current.entry_timestamp_utc,
                    entry_price=current.entry_price,
                    last_signal=signal,
                    last_signal_timestamp_utc=timestamp,
                )
                event = PositionEvent(
                    frame.index, timestamp, price, PositionAction.HOLD,
                    PositionSide.LONG, PositionSide.LONG, signal,
                    "Repeated LONG signal maintained the hypothetical long position.",
                )
            else:
                new_state = PositionState(
                    side=PositionSide.LONG,
                    entry_timestamp_utc=timestamp,
                    entry_price=price,
                    last_signal=signal,
                    last_signal_timestamp_utc=timestamp,
                )
                event = PositionEvent(
                    frame.index, timestamp, price, PositionAction.REVERSE,
                    PositionSide.SHORT, PositionSide.LONG, signal,
                    "Opposite LONG signal reversed the hypothetical short position.",
                )
        elif signal is SignalDirection.SHORT:
            if current.side is PositionSide.FLAT:
                new_state = PositionState(
                    side=PositionSide.SHORT,
                    entry_timestamp_utc=timestamp,
                    entry_price=price,
                    last_signal=signal,
                    last_signal_timestamp_utc=timestamp,
                )
                event = PositionEvent(
                    frame.index, timestamp, price, PositionAction.OPEN,
                    PositionSide.FLAT, PositionSide.SHORT, signal,
                    "SHORT signal opened a hypothetical short position.",
                )
            elif current.side is PositionSide.SHORT:
                new_state = PositionState(
                    side=PositionSide.SHORT,
                    entry_timestamp_utc=current.entry_timestamp_utc,
                    entry_price=current.entry_price,
                    last_signal=signal,
                    last_signal_timestamp_utc=timestamp,
                )
                event = PositionEvent(
                    frame.index, timestamp, price, PositionAction.HOLD,
                    PositionSide.SHORT, PositionSide.SHORT, signal,
                    "Repeated SHORT signal maintained the hypothetical short position.",
                )
            else:
                new_state = PositionState(
                    side=PositionSide.SHORT,
                    entry_timestamp_utc=timestamp,
                    entry_price=price,
                    last_signal=signal,
                    last_signal_timestamp_utc=timestamp,
                )
                event = PositionEvent(
                    frame.index, timestamp, price, PositionAction.REVERSE,
                    PositionSide.LONG, PositionSide.SHORT, signal,
                    "Opposite SHORT signal reversed the hypothetical long position.",
                )
        else:
            new_state = PositionState(
                side=current.side,
                entry_timestamp_utc=current.entry_timestamp_utc,
                entry_price=current.entry_price,
                last_signal=signal,
                last_signal_timestamp_utc=timestamp,
            )
            event = PositionEvent(
                frame.index, timestamp, price, PositionAction.HOLD,
                current.side, current.side, signal,
                "NEUTRAL signal did not change the hypothetical position.",
            )

        self._state = new_state
        self._events.append(event)
        return event

    def simulate(
        self,
        frames: Iterable[BacktestFrame],
        signal_provider: Callable[[BacktestFrame], SignalDirection],
    ) -> tuple[PositionEvent, ...]:
        """Replay frames once and apply one signal returned for each frame."""
        if not callable(signal_provider):
            raise PositionSimulationError("signal_provider must be callable.")

        self.reset()
        previous_index: int | None = None

        for frame in frames:
            self._validate_frame(frame)
            if previous_index is not None and frame.index <= previous_index:
                raise PositionSimulationError(
                    "frames must be supplied in strictly increasing index order."
                )

            signal = signal_provider(frame)
            self.apply(frame, signal)
            previous_index = frame.index

        return self.events
