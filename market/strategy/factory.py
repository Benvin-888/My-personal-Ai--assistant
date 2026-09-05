"""Factory for constructing configured APEX strategy instances."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .base import Strategy


class StrategyFactoryError(ValueError):
    """Raised when strategy construction is invalid."""


StrategyConstructor = Callable[[Mapping[str, Any]], Strategy]


class StrategyFactory:
    """Map stable strategy IDs to constructors without embedding strategy logic."""

    def __init__(self) -> None:
        self._constructors: dict[str, StrategyConstructor] = {}

    def register(
        self,
        strategy_id: str,
        constructor: StrategyConstructor,
    ) -> None:
        if not isinstance(strategy_id, str) or not strategy_id.strip():
            raise StrategyFactoryError("strategy_id must be a non-empty string.")
        if not callable(constructor):
            raise StrategyFactoryError("constructor must be callable.")

        key = strategy_id.strip()
        if key in self._constructors:
            raise StrategyFactoryError(
                f"Strategy constructor already registered: {key}"
            )

        self._constructors[key] = constructor

    def create(
        self,
        strategy_id: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> Strategy:
        key = str(strategy_id).strip()
        if not key:
            raise StrategyFactoryError("strategy_id must be a non-empty string.")

        constructor = self._constructors.get(key)
        if constructor is None:
            raise StrategyFactoryError(
                f"Unknown strategy constructor: {key}"
            )

        effective_parameters = dict(parameters or {})

        try:
            strategy = constructor(effective_parameters)
        except StrategyFactoryError:
            raise
        except Exception as exc:
            raise StrategyFactoryError(
                f"Failed to construct strategy {key}: {exc}"
            ) from exc

        if not isinstance(strategy, Strategy):
            raise StrategyFactoryError(
                f"Constructor for {key} returned an invalid strategy object."
            )

        actual_id = strategy.definition.strategy_id
        if actual_id != key:
            raise StrategyFactoryError(
                f"Constructor identity mismatch: expected {key}, got {actual_id}."
            )

        return strategy

    def list_ids(self) -> list[str]:
        return sorted(self._constructors)
