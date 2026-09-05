"""
APEX / BENVIN Backtesting Foundation Models.

Phase 2.5.10 - Point-in-Time Backtest Execution Semantics.

These models define the immutable contracts shared by future
backtesting components. They describe historical datasets, replay
configuration, and deterministic run metadata. They do not simulate
orders, calculate P&L, manage positions, or connect to brokers.

Design principles:
    - historical data is treated as chronological, validated input
    - configuration is explicit and reproducible
    - no look-ahead semantics are hidden inside the models
    - models are immutable and serializable
    - execution timing is explicit and future-candle information remains unavailable
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Any

from ..models import Candle


class BacktestStatus(str, Enum):
    """Lifecycle/status values for a backtest run."""

    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"
    ERROR = "ERROR"


class ReplayMode(str, Enum):
    """Historical replay modes supported by the foundation."""

    BAR_BY_BAR = "BAR_BY_BAR"


class ExecutionTiming(str, Enum):
    """Point-in-time signal-to-execution policies for backtests."""

    NEXT_BAR_OPEN = "NEXT_BAR_OPEN"


@dataclass(frozen=True)
class BacktestConfig:
    """
    Immutable configuration for a deterministic historical replay.

    This model intentionally excludes transaction costs, spread,
    slippage, leverage, position sizing, and risk controls. Those are
    separate simulation assumptions that belong to later phases.
    """

    pair: str
    interval: str
    initial_capital: float = 10000.0
    warmup_candles: int = 0
    start_timestamp_utc: str | None = None
    end_timestamp_utc: str | None = None
    max_candles: int | None = None
    replay_mode: ReplayMode = ReplayMode.BAR_BY_BAR
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_timing: ExecutionTiming = ExecutionTiming.NEXT_BAR_OPEN

    def __post_init__(self) -> None:
        if not isinstance(self.pair, str) or not self.pair.strip():
            raise ValueError("pair must be a non-empty string")
        if not isinstance(self.interval, str) or not self.interval.strip():
            raise ValueError("interval must be a non-empty string")
        if (
            not isinstance(self.initial_capital, (int, float))
            or isinstance(self.initial_capital, bool)
        ):
            raise ValueError("initial_capital must be numeric")
        if not isfinite(float(self.initial_capital)) or self.initial_capital <= 0:
            raise ValueError("initial_capital must be finite and greater than zero")
        if (
            not isinstance(self.warmup_candles, int)
            or isinstance(self.warmup_candles, bool)
            or self.warmup_candles < 0
        ):
            raise ValueError("warmup_candles must be a non-negative integer")
        if self.max_candles is not None:
            if (
                not isinstance(self.max_candles, int)
                or isinstance(self.max_candles, bool)
                or self.max_candles < 1
            ):
                raise ValueError("max_candles must be a positive integer or None")
        if not isinstance(self.replay_mode, ReplayMode):
            raise ValueError("replay_mode must be a ReplayMode")
        if not isinstance(self.execution_timing, ExecutionTiming):
            raise ValueError("execution_timing must be an ExecutionTiming")
        if self.start_timestamp_utc is not None and (
            not isinstance(self.start_timestamp_utc, str)
            or not self.start_timestamp_utc.strip()
        ):
            raise ValueError("start_timestamp_utc must be a non-empty string or None")
        if self.end_timestamp_utc is not None and (
            not isinstance(self.end_timestamp_utc, str)
            or not self.end_timestamp_utc.strip()
        ):
            raise ValueError("end_timestamp_utc must be a non-empty string or None")

        if self.start_timestamp_utc and self.end_timestamp_utc:
            if self.start_timestamp_utc > self.end_timestamp_utc:
                raise ValueError("start_timestamp_utc cannot be after end_timestamp_utc")

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "interval": self.interval,
            "initial_capital": float(self.initial_capital),
            "warmup_candles": self.warmup_candles,
            "start_timestamp_utc": self.start_timestamp_utc,
            "end_timestamp_utc": self.end_timestamp_utc,
            "max_candles": self.max_candles,
            "replay_mode": self.replay_mode.value,
            "execution_timing": self.execution_timing.value,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class BacktestDataset:
    """
    Immutable validated historical input for a backtest.

    Candles must already be chronologically ordered. The dataset model
    does not fetch, repair, or reorder provider data; that responsibility
    remains with the historical market-data layer.
    """

    pair: str
    interval: str
    candles: tuple[Candle, ...]
    provider: str | None = None
    provider_symbol: str | None = None
    data_range: str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.pair, str) or not self.pair.strip():
            raise ValueError("pair must be a non-empty string")
        if not isinstance(self.interval, str) or not self.interval.strip():
            raise ValueError("interval must be a non-empty string")
        if not isinstance(self.candles, tuple):
            raise ValueError("candles must be a tuple")
        for index, candle in enumerate(self.candles):
            if not isinstance(candle, Candle):
                raise ValueError(f"candles[{index}] must be a Candle")

        previous = None
        for index, candle in enumerate(self.candles):
            timestamp = candle.timestamp
            if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool):
                raise ValueError(
                    f"candles[{index}].timestamp must be numeric for chronological validation"
                )
            if not isfinite(float(timestamp)):
                raise ValueError(f"candles[{index}].timestamp must be finite")
            if previous is not None and timestamp <= previous:
                raise ValueError("candles must be strictly chronological")
            previous = float(timestamp)

        for field_name in ("provider", "provider_symbol", "data_range"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError(f"{field_name} must be a non-empty string or None")

    @property
    def candle_count(self) -> int:
        return len(self.candles)

    @property
    def first_timestamp_utc(self) -> str | None:
        return self.candles[0].timestamp_utc if self.candles else None

    @property
    def latest_timestamp_utc(self) -> str | None:
        return self.candles[-1].timestamp_utc if self.candles else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "interval": self.interval,
            "candle_count": self.candle_count,
            "first_timestamp_utc": self.first_timestamp_utc,
            "latest_timestamp_utc": self.latest_timestamp_utc,
            "provider": self.provider,
            "provider_symbol": self.provider_symbol,
            "range": self.data_range,
            "source_metadata": dict(self.source_metadata),
            "candles": [candle.to_dict() for candle in self.candles],
        }


@dataclass(frozen=True)
class BacktestFrame:
    """
    One point-in-time replay frame.

    ``available_candles`` contains only information available at the
    frame timestamp. It is intentionally a prefix of the dataset, so a
    future replay engine can enforce no-look-ahead behavior structurally.
    """

    index: int
    candle: Candle
    available_candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.index, int)
            or isinstance(self.index, bool)
            or self.index < 0
        ):
            raise ValueError("index must be a non-negative integer")
        if not isinstance(self.candle, Candle):
            raise ValueError("candle must be a Candle")
        if not isinstance(self.available_candles, tuple) or not self.available_candles:
            raise ValueError("available_candles must be a non-empty tuple")
        if self.index >= len(self.available_candles):
            raise ValueError("index must refer to a candle inside available_candles")
        if self.available_candles[self.index] != self.candle:
            raise ValueError("candle must match available_candles[index]")
        if len(self.available_candles) != self.index + 1:
            raise ValueError(
                "available_candles must contain only candles available through the current frame"
            )

    @property
    def timestamp_utc(self) -> str | None:
        return self.candle.timestamp_utc

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "timestamp_utc": self.timestamp_utc,
            "candle": self.candle.to_dict(),
            "available_candle_count": len(self.available_candles),
        }


@dataclass(frozen=True)
class BacktestRunMetadata:
    """
    Reproducibility metadata for a backtest run.

    This contains configuration identity and dataset boundaries, not
    runtime wall-clock timestamps or performance metrics.
    """

    config: BacktestConfig
    dataset_pair: str
    dataset_interval: str
    dataset_candle_count: int
    strategy_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.config, BacktestConfig):
            raise ValueError("config must be a BacktestConfig")
        if not isinstance(self.dataset_pair, str) or not self.dataset_pair.strip():
            raise ValueError("dataset_pair must be a non-empty string")
        if not isinstance(self.dataset_interval, str) or not self.dataset_interval.strip():
            raise ValueError("dataset_interval must be a non-empty string")
        if (
            not isinstance(self.dataset_candle_count, int)
            or isinstance(self.dataset_candle_count, bool)
            or self.dataset_candle_count < 0
        ):
            raise ValueError("dataset_candle_count must be a non-negative integer")
        if not isinstance(self.strategy_ids, tuple):
            raise ValueError("strategy_ids must be a tuple")
        if len(set(self.strategy_ids)) != len(self.strategy_ids):
            raise ValueError("strategy_ids must not contain duplicates")
        for strategy_id in self.strategy_ids:
            if not isinstance(strategy_id, str) or not strategy_id.strip():
                raise ValueError("strategy_ids must contain non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "dataset_pair": self.dataset_pair,
            "dataset_interval": self.dataset_interval,
            "dataset_candle_count": self.dataset_candle_count,
            "strategy_ids": list(self.strategy_ids),
            "metadata": dict(self.metadata),
        }
