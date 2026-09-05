"""
APEX / BENVIN Historical Replay Engine.

Phase 2.5.2 - Historical Replay Engine.

Replays validated historical candles chronologically and exposes only
point-in-time history. No trading, P&L, positions, costs, risk, or broker
behavior belongs in this layer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from .models import BacktestConfig, BacktestDataset, BacktestFrame


class HistoricalReplayError(ValueError):
    """Raised when historical replay configuration or execution is invalid."""


ReplayCallback = Callable[[BacktestFrame], Any]


class HistoricalReplayEngine:
    """Deterministic chronological replay of a validated dataset."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        if config is not None and not isinstance(config, BacktestConfig):
            raise HistoricalReplayError("config must be a BacktestConfig or None")
        self.config = config

    def _validate_dataset(self, dataset: BacktestDataset) -> None:
        if not isinstance(dataset, BacktestDataset):
            raise HistoricalReplayError("dataset must be a BacktestDataset")
        if self.config is None:
            return

        if dataset.pair.strip().upper() != self.config.pair.strip().upper():
            raise HistoricalReplayError(
                "dataset pair does not match replay configuration"
            )
        if dataset.interval.strip().lower() != self.config.interval.strip().lower():
            raise HistoricalReplayError(
                "dataset interval does not match replay configuration"
            )

    def _selected_candles(self, dataset: BacktestDataset) -> tuple:
        start = self.config.start_timestamp_utc if self.config else None
        end = self.config.end_timestamp_utc if self.config else None

        selected = tuple(
            candle
            for candle in dataset.candles
            if (start is None or candle.timestamp_utc >= start)
            and (end is None or candle.timestamp_utc <= end)
        )

        maximum = self.config.max_candles if self.config else None
        if maximum is not None:
            selected = selected[:maximum]

        return selected

    def frames(self, dataset: BacktestDataset) -> Iterator[BacktestFrame]:
        """Yield point-in-time frames in chronological order."""
        self._validate_dataset(dataset)
        selected = self._selected_candles(dataset)

        for index, candle in enumerate(selected):
            # Critical invariant: only the historical prefix through the
            # current candle is exposed. Future candles remain inaccessible.
            available = tuple(selected[: index + 1])
            yield BacktestFrame(
                index=index,
                candle=candle,
                available_candles=available,
            )

    def iter_frames(self, dataset: BacktestDataset) -> Iterator[BacktestFrame]:
        """Explicit iterator alias for frames()."""
        yield from self.frames(dataset)

    def is_warmup_complete(self, frame: BacktestFrame) -> bool:
        """Return whether the configured warm-up requirement is satisfied."""
        if not isinstance(frame, BacktestFrame):
            raise HistoricalReplayError("frame must be a BacktestFrame")

        warmup = self.config.warmup_candles if self.config else 0
        return len(frame.available_candles) >= warmup

    def replay(self, dataset: BacktestDataset, callback: ReplayCallback) -> list[Any]:
        """Replay every frame in order and collect callback results."""
        if not callable(callback):
            raise HistoricalReplayError("callback must be callable")

        return [callback(frame) for frame in self.frames(dataset)]

    def count(self, dataset: BacktestDataset) -> int:
        """Return the number of replay frames."""
        return sum(1 for _ in self.frames(dataset))
