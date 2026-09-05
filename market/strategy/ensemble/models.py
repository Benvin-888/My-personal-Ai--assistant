"""Structured models for deterministic multi-strategy ensemble evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Any

from ..models import EvaluationStatus, SignalDirection


class EnsembleStatus(str, Enum):
    """Lifecycle status of an ensemble evaluation."""

    EVALUATED = "EVALUATED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"
    NO_ACTIVE_STRATEGIES = "NO_ACTIVE_STRATEGIES"
    ERROR = "ERROR"


@dataclass(frozen=True)
class EnsembleConfig:
    """Validated thresholds controlling ensemble decisions."""

    minimum_score: float = 0.60
    minimum_agreement: float = 0.80
    minimum_active_strategies: int = 2

    def __post_init__(self) -> None:
        for name in ("minimum_score", "minimum_agreement"):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
            ):
                raise ValueError(f"{name} must be finite and between 0 and 1")

        if (
            not isinstance(self.minimum_active_strategies, int)
            or isinstance(self.minimum_active_strategies, bool)
            or self.minimum_active_strategies < 1
        ):
            raise ValueError("minimum_active_strategies must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_score": float(self.minimum_score),
            "minimum_agreement": float(self.minimum_agreement),
            "minimum_active_strategies": self.minimum_active_strategies,
        }


@dataclass(frozen=True)
class StrategyContribution:
    """One strategy's normalized contribution to an ensemble."""

    strategy_id: str
    strategy_version: str
    direction: SignalDirection
    score: float
    weight: float
    weighted_score: float
    status: EvaluationStatus
    rationale: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if not isinstance(self.strategy_version, str) or not self.strategy_version.strip():
            raise ValueError("strategy_version must be a non-empty string")
        if not isinstance(self.direction, SignalDirection):
            raise ValueError("direction must be a SignalDirection")
        if not isinstance(self.status, EvaluationStatus):
            raise ValueError("status must be an EvaluationStatus")
        for name, value in (
            ("score", self.score),
            ("weight", self.weight),
            ("weighted_score", self.weighted_score),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(float(value))
            ):
                raise ValueError(f"{name} must be finite and numeric")
        if not -1.0 <= float(self.score) <= 1.0:
            raise ValueError("score must be between -1 and 1")
        if self.weight < 0:
            raise ValueError("weight cannot be negative")
        expected_weighted_score = float(self.weight) * float(self.score)
        if abs(float(self.weighted_score) - expected_weighted_score) > 1e-9:
            raise ValueError("weighted_score is inconsistent with score and weight")

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "direction": self.direction.value,
            "score": float(self.score),
            "weight": float(self.weight),
            "weighted_score": float(self.weighted_score),
            "status": self.status.value,
            "rationale": self.rationale,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class EnsembleEvaluation:
    """Complete deterministic result of one ensemble evaluation."""

    pair: str
    interval: str
    timestamp_utc: str | None
    status: EnsembleStatus
    decision: SignalDirection
    ensemble_score: float
    agreement: float
    conflict: float
    confidence: float
    active_strategy_count: int
    evaluated_strategy_count: int
    failed_strategy_count: int
    long_strategy_count: int
    short_strategy_count: int
    neutral_strategy_count: int
    contributions: tuple[StrategyContribution, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, EnsembleStatus):
            raise ValueError("status must be an EnsembleStatus")
        if not isinstance(self.decision, SignalDirection):
            raise ValueError("decision must be a SignalDirection")
        for name, value in (
            ("ensemble_score", self.ensemble_score),
            ("agreement", self.agreement),
            ("conflict", self.conflict),
            ("confidence", self.confidence),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(float(value))
            ):
                raise ValueError(f"{name} must be finite and numeric")
        if not -1.0 <= float(self.ensemble_score) <= 1.0:
            raise ValueError("ensemble_score must be between -1 and 1")
        for name in ("agreement", "conflict", "confidence"):
            if not 0.0 <= float(getattr(self, name)) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        counts = (
            self.active_strategy_count,
            self.evaluated_strategy_count,
            self.failed_strategy_count,
            self.long_strategy_count,
            self.short_strategy_count,
            self.neutral_strategy_count,
        )
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in counts):
            raise ValueError("ensemble counts must be non-negative integers")
        if self.evaluated_strategy_count + self.failed_strategy_count != self.active_strategy_count:
            raise ValueError("strategy counts are inconsistent")
        if self.long_strategy_count + self.short_strategy_count + self.neutral_strategy_count != self.evaluated_strategy_count:
            raise ValueError("direction counts are inconsistent")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "success": self.status == EnsembleStatus.EVALUATED,
            "market": "forex",
            "analysis": "strategy_ensemble",
            "status": self.status.value,
            "pair": self.pair,
            "interval": self.interval,
            "timeframe": self.interval,
            "timestamp_utc": self.timestamp_utc,
            "decision": self.decision.value,
            "ensemble_score": round(float(self.ensemble_score), 6),
            "agreement": round(float(self.agreement), 6),
            "conflict": round(float(self.conflict), 6),
            "confidence": round(float(self.confidence), 6),
            "strategies": {
                "active": self.active_strategy_count,
                "evaluated": self.evaluated_strategy_count,
                "failed": self.failed_strategy_count,
                "long": self.long_strategy_count,
                "short": self.short_strategy_count,
                "neutral": self.neutral_strategy_count,
            },
            "contributions": [c.to_dict() for c in self.contributions],
            "metadata": dict(self.metadata),
        }
        if self.error is not None:
            result["error"] = self.error
        return result
