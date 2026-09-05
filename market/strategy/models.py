"""
APEX / BENVIN Strategy Intelligence Models.

Phase 2.4.2 hardening: deterministic, explainable strategy contracts.
These models describe strategy conclusions only; they never execute orders.
"""

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Any


class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class EvaluationStatus(str, Enum):
    EVALUATED = "EVALUATED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"
    ERROR = "ERROR"


class ConditionStatus(str, Enum):
    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class StrategyCondition:
    condition_id: str
    name: str
    description: str
    status: ConditionStatus
    category: str = "general"
    value: Any = None
    expected: Any = None
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    direction: SignalDirection | None = None

    def __post_init__(self):
        if not isinstance(self.condition_id, str) or not self.condition_id.strip():
            raise ValueError("condition_id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.description, str):
            raise ValueError("description must be a string")
        if not isinstance(self.status, ConditionStatus):
            raise ValueError("status must be a ConditionStatus")
        if not isinstance(self.weight, (int, float)) or isinstance(self.weight, bool):
            raise ValueError("weight must be numeric")
        if not isfinite(float(self.weight)) or self.weight < 0:
            raise ValueError("weight must be finite and non-negative")
        if self.direction is not None and not isinstance(self.direction, SignalDirection):
            raise ValueError("direction must be a SignalDirection or None")

    def to_dict(self):
        return {
            "condition_id": self.condition_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "category": self.category,
            "value": self.value,
            "expected": self.expected,
            "weight": float(self.weight),
            "metadata": dict(self.metadata),
            "direction": self.direction.value if self.direction else None,
        }


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_id: str
    name: str
    version: str
    description: str
    timeframe: str
    market: str = "forex"
    supported_pairs: tuple[str, ...] = ()
    minimum_candles: int = 0
    parameters: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for field_name in ("strategy_id", "name", "version", "timeframe"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.minimum_candles, int) or isinstance(self.minimum_candles, bool):
            raise ValueError("minimum_candles must be an integer")
        if self.minimum_candles < 0:
            raise ValueError("minimum_candles cannot be negative")

    def to_dict(self):
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "timeframe": self.timeframe,
            "market": self.market,
            "supported_pairs": list(self.supported_pairs),
            "minimum_candles": self.minimum_candles,
            "parameters": dict(self.parameters),
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StrategySignal:
    direction: SignalDirection
    score: float
    rationale: str
    conditions: tuple[StrategyCondition, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.direction, SignalDirection):
            raise ValueError("direction must be a SignalDirection")
        if not isinstance(self.score, (int, float)) or isinstance(self.score, bool):
            raise ValueError("score must be numeric")
        if not isfinite(float(self.score)) or not -1.0 <= float(self.score) <= 1.0:
            raise ValueError("score must be finite and between -1 and 1")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("rationale must be a non-empty string")

    def to_dict(self):
        return {
            "direction": self.direction.value,
            "score": float(self.score),
            "rationale": self.rationale,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StrategyEvaluation:
    strategy: StrategyDefinition
    status: EvaluationStatus
    pair: str
    interval: str
    timestamp_utc: str | None
    signal: StrategySignal | None
    condition_count: int
    satisfied_count: int
    unavailable_count: int
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def __post_init__(self):
        if not isinstance(self.status, EvaluationStatus):
            raise ValueError("status must be an EvaluationStatus")
        counts = (self.condition_count, self.satisfied_count, self.unavailable_count)
        if any(not isinstance(value, int) or isinstance(value, bool) for value in counts):
            raise ValueError("strategy condition counts must be integers")
        if any(value < 0 for value in counts):
            raise ValueError("strategy condition counts cannot be negative")
        if self.satisfied_count > self.condition_count:
            raise ValueError("satisfied_count cannot exceed condition_count")
        if self.unavailable_count > self.condition_count:
            raise ValueError("unavailable_count cannot exceed condition_count")
        if self.signal is not None and self.status != EvaluationStatus.EVALUATED:
            raise ValueError("non-evaluated results cannot contain a signal")
        if self.status == EvaluationStatus.EVALUATED and self.signal is None:
            raise ValueError("evaluated results must contain a signal")

    @property
    def timeframe(self):
        """Alias for interval for strategy-facing terminology."""
        return self.interval

    @property
    def completeness_ratio(self):
        if self.condition_count == 0:
            return 0.0
        return (self.condition_count - self.unavailable_count) / self.condition_count

    def to_dict(self):
        result = {
            "success": self.status == EvaluationStatus.EVALUATED,
            "market": self.strategy.market,
            "analysis": "strategy",
            "status": self.status.value,
            "strategy": self.strategy.to_dict(),
            "pair": self.pair,
            "interval": self.interval,
            "timeframe": self.timeframe,
            "strategy_id": self.strategy.strategy_id,
            "strategy_version": self.strategy.version,
            "timestamp_utc": self.timestamp_utc,
            "signal": self.signal.to_dict() if self.signal else None,
            "conditions": {
                "count": self.condition_count,
                "satisfied": self.satisfied_count,
                "unavailable": self.unavailable_count,
                "completeness_ratio": round(self.completeness_ratio, 6),
            },
            "metadata": dict(self.metadata),
        }
        if self.error is not None:
            result["error"] = self.error
        return result
