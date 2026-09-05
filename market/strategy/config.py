"""Configurable strategy settings for APEX."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping


class StrategyConfigurationError(ValueError):
    """Raised when a strategy configuration is invalid."""


@dataclass(frozen=True)
class StrategyConfig:
    """Validated configuration for one registered strategy."""

    strategy_id: str
    enabled: bool = True
    parameters: Mapping[str, Any] = field(default_factory=dict)
    pairs: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ()
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise StrategyConfigurationError("strategy_id must be a non-empty string.")
        if not isinstance(self.enabled, bool):
            raise StrategyConfigurationError("enabled must be a boolean.")
        if not isinstance(self.parameters, Mapping):
            raise StrategyConfigurationError("parameters must be a mapping.")
        if any(not isinstance(p, str) or not p.strip() for p in self.pairs):
            raise StrategyConfigurationError("pairs must contain non-empty strings.")
        if any(not isinstance(t, str) or not t.strip() for t in self.timeframes):
            raise StrategyConfigurationError("timeframes must contain non-empty strings.")
        if (
            not isinstance(self.weight, (int, float))
            or isinstance(self.weight, bool)
            or not isfinite(float(self.weight))
            or self.weight < 0
        ):
            raise StrategyConfigurationError(
                "weight must be finite, numeric, and non-negative."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "enabled": self.enabled,
            "parameters": dict(self.parameters),
            "pairs": list(self.pairs),
            "timeframes": list(self.timeframes),
            "weight": float(self.weight),
        }
