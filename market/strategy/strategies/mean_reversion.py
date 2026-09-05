"""Deterministic RSI/Bollinger mean-reversion strategy for APEX."""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping

from ..base import Strategy
from ..models import (
    ConditionStatus,
    EvaluationStatus,
    SignalDirection,
    StrategyCondition,
    StrategyDefinition,
    StrategyEvaluation,
    StrategySignal,
)


class MeanReversionStrategy(Strategy):
    """Evaluate oversold/overbought evidence without execution semantics.

    The strategy intentionally uses evidence that is complementary to the
    trend/momentum strategy: it looks for stretched conditions rather than
    requiring trend continuation.
    """

    DEFAULTS = {
        "rsi_oversold_max": 30.0,
        "rsi_overbought_min": 70.0,
        "minimum_score": 0.60,
        "minimum_agreement": 0.80,
        "rsi_weight": 0.55,
        "bollinger_weight": 0.45,
    }

    def __init__(self, parameters: Mapping[str, Any] | None = None):
        if parameters is not None and not isinstance(parameters, Mapping):
            raise ValueError("parameters must be a mapping")

        self.parameters = {**self.DEFAULTS, **dict(parameters or {})}
        self._validate()
        self._definition = StrategyDefinition(
            strategy_id="mean_reversion",
            name="Mean Reversion",
            version="1.0.0",
            description=(
                "Deterministic RSI extreme and Bollinger Band stretch analysis "
                "with conflict-aware weighted scoring."
            ),
            timeframe="5m",
            supported_pairs=(),
            minimum_candles=20,
            parameters=dict(self.parameters),
            tags=(
                "mean_reversion",
                "rsi",
                "bollinger",
                "deterministic",
            ),
            metadata={
                "execution": "none",
                "backtest_ready": True,
                "signal_policy": "extreme_reversion_confirmation",
                "versioning_policy": "semantic",
            },
        )

    @property
    def definition(self) -> StrategyDefinition:
        return self._definition

    def evaluate(self, analysis: dict[str, Any]) -> StrategyEvaluation:
        if not isinstance(analysis, dict):
            return self._insufficient(
                "UNKNOWN", "UNKNOWN", None,
                "Technical-analysis input must be a dictionary.",
            )

        pair = str(analysis.get("pair", "UNKNOWN"))
        interval = str(analysis.get("interval", "UNKNOWN"))
        timestamp = analysis.get("latest_timestamp_utc")
        candle_count = analysis.get("candle_count", 0)

        if (
            not isinstance(candle_count, int)
            or isinstance(candle_count, bool)
            or candle_count < self.definition.minimum_candles
        ):
            return self._insufficient(
                pair,
                interval,
                timestamp,
                "Not enough candles for strategy evaluation.",
            )

        indicators = analysis.get("indicators")
        metadata = analysis.get("metadata")
        if not isinstance(indicators, dict) or not isinstance(metadata, dict):
            return self._insufficient(
                pair,
                interval,
                timestamp,
                "Technical-analysis structure is unavailable.",
            )

        try:
            rsi = indicators["rsi"]["value"]
            bands = indicators["bollinger_bands"]
            close = metadata["latest_close"]
            middle = bands["middle"]
            upper = bands["upper"]
            lower = bands["lower"]
        except (KeyError, TypeError):
            return self._insufficient(
                pair,
                interval,
                timestamp,
                "Required RSI, Bollinger Band, or latest-close data is unavailable.",
            )

        values = (rsi, close, middle, upper, lower)
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(float(value))
            for value in values
        ):
            return self._insufficient(
                pair,
                interval,
                timestamp,
                "Required RSI, Bollinger Band, or latest-close data is unavailable.",
            )

        if not (lower <= middle <= upper):
            return self._insufficient(
                pair,
                interval,
                timestamp,
                "Bollinger Band relationships are invalid.",
            )

        conditions = (
            self._rsi_condition(rsi),
            self._bollinger_condition(close, middle, upper, lower),
        )

        score = self._score(conditions)
        agreement = self._agreement(conditions)
        direction = self._direction(score, agreement)
        rationale = self._rationale(direction, score, agreement, conditions)

        signal = StrategySignal(
            direction=direction,
            score=score,
            rationale=rationale,
            conditions=conditions,
            metadata={
                "scoring": "conflict_aware_weighted_extremes",
                "minimum_score": self.parameters["minimum_score"],
                "minimum_agreement": self.parameters["minimum_agreement"],
                "agreement": round(agreement, 6),
                "latest_close": close,
                "bollinger_middle": middle,
                "bollinger_upper": upper,
                "bollinger_lower": lower,
            },
        )

        return StrategyEvaluation(
            strategy=self.definition,
            status=EvaluationStatus.EVALUATED,
            pair=pair,
            interval=interval,
            timestamp_utc=timestamp,
            signal=signal,
            condition_count=len(conditions),
            satisfied_count=sum(
                condition.status == ConditionStatus.SATISFIED
                for condition in conditions
            ),
            unavailable_count=sum(
                condition.status == ConditionStatus.UNAVAILABLE
                for condition in conditions
            ),
            metadata={
                "latest_close": close,
                "rsi": rsi,
                "bollinger_middle": middle,
                "bollinger_upper": upper,
                "bollinger_lower": lower,
                "complete": all(
                    condition.status != ConditionStatus.UNAVAILABLE
                    for condition in conditions
                ),
                "decision_policy": "extreme_reversion_confirmation",
            },
        )

    def _rsi_condition(self, value: float) -> StrategyCondition:
        if value <= self.parameters["rsi_oversold_max"]:
            direction = SignalDirection.LONG
            status = ConditionStatus.SATISFIED
            expected = f"RSI <= {self.parameters['rsi_oversold_max']:.1f}"
        elif value >= self.parameters["rsi_overbought_min"]:
            direction = SignalDirection.SHORT
            status = ConditionStatus.SATISFIED
            expected = f"RSI >= {self.parameters['rsi_overbought_min']:.1f}"
        else:
            direction = None
            status = ConditionStatus.UNAVAILABLE
            expected = (
                f"RSI <= {self.parameters['rsi_oversold_max']:.1f} or "
                f"RSI >= {self.parameters['rsi_overbought_min']:.1f}"
            )

        return StrategyCondition(
            condition_id="rsi_extreme",
            name="RSI extreme",
            description="RSI identifies an oversold or overbought condition.",
            status=status,
            category="mean_reversion",
            value=value,
            expected=expected,
            weight=self.parameters["rsi_weight"],
            direction=direction,
        )

    def _bollinger_condition(
        self,
        close: float,
        middle: float,
        upper: float,
        lower: float,
    ) -> StrategyCondition:
        if close <= lower:
            direction = SignalDirection.LONG
            status = ConditionStatus.SATISFIED
            expected = "close <= lower Bollinger Band"
        elif close >= upper:
            direction = SignalDirection.SHORT
            status = ConditionStatus.SATISFIED
            expected = "close >= upper Bollinger Band"
        else:
            direction = None
            status = ConditionStatus.UNAVAILABLE
            expected = "close at/beyond a Bollinger Band"

        return StrategyCondition(
            condition_id="bollinger_extreme",
            name="Bollinger extreme",
            description="Price is stretched to or beyond a Bollinger Band.",
            status=status,
            category="mean_reversion",
            value=close,
            expected=expected,
            weight=self.parameters["bollinger_weight"],
            direction=direction,
            metadata={
                "middle": middle,
                "upper": upper,
                "lower": lower,
            },
        )

    @staticmethod
    def _score(conditions: tuple[StrategyCondition, ...]) -> float:
        available = [
            condition
            for condition in conditions
            if condition.status != ConditionStatus.UNAVAILABLE
            and condition.direction is not None
            and condition.weight > 0
        ]
        total_weight = sum(condition.weight for condition in available)
        if total_weight == 0:
            return 0.0

        total = sum(
            condition.weight
            * (1.0 if condition.direction == SignalDirection.LONG else -1.0)
            for condition in available
        )
        return max(-1.0, min(1.0, total / total_weight))

    @staticmethod
    def _agreement(conditions: tuple[StrategyCondition, ...]) -> float:
        available = [
            condition
            for condition in conditions
            if condition.status != ConditionStatus.UNAVAILABLE
            and condition.direction is not None
            and condition.weight > 0
        ]
        total_weight = sum(condition.weight for condition in available)
        if total_weight == 0:
            return 0.0

        long_weight = sum(
            condition.weight
            for condition in available
            if condition.direction == SignalDirection.LONG
        )
        short_weight = sum(
            condition.weight
            for condition in available
            if condition.direction == SignalDirection.SHORT
        )
        return max(long_weight, short_weight) / total_weight

    def _direction(self, score: float, agreement: float) -> SignalDirection:
        if abs(score) < self.parameters["minimum_score"]:
            return SignalDirection.NEUTRAL
        if agreement < self.parameters["minimum_agreement"]:
            return SignalDirection.NEUTRAL
        if score > 0:
            return SignalDirection.LONG
        if score < 0:
            return SignalDirection.SHORT
        return SignalDirection.NEUTRAL

    @staticmethod
    def _rationale(
        direction: SignalDirection,
        score: float,
        agreement: float,
        conditions: tuple[StrategyCondition, ...],
    ) -> str:
        satisfied = sum(
            condition.status == ConditionStatus.SATISFIED
            for condition in conditions
        )
        unavailable = sum(
            condition.status == ConditionStatus.UNAVAILABLE
            for condition in conditions
        )
        if direction == SignalDirection.NEUTRAL:
            return (
                "No sufficiently aligned mean-reversion conclusion; "
                f"score={score:.3f}, agreement={agreement:.3f}, "
                f"satisfied={satisfied}/{len(conditions)}, unavailable={unavailable}."
            )
        return (
            f"{direction.value} mean-reversion conclusion from extreme-price "
            f"evidence; score={score:.3f}, agreement={agreement:.3f}, "
            f"satisfied={satisfied}/{len(conditions)}."
        )

    def _insufficient(
        self,
        pair: str,
        interval: str,
        timestamp: str | None,
        message: str,
    ) -> StrategyEvaluation:
        return StrategyEvaluation(
            strategy=self.definition,
            status=EvaluationStatus.INSUFFICIENT_DATA,
            pair=pair,
            interval=interval,
            timestamp_utc=timestamp,
            signal=None,
            condition_count=0,
            satisfied_count=0,
            unavailable_count=0,
            error=message,
        )

    def _validate(self) -> None:
        numeric = (
            "rsi_oversold_max",
            "rsi_overbought_min",
            "minimum_score",
            "minimum_agreement",
            "rsi_weight",
            "bollinger_weight",
        )
        for key in numeric:
            value = self.parameters[key]
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(float(value))
            ):
                raise ValueError(
                    f"strategy parameter {key} must be finite and numeric"
                )

        if not 0 <= self.parameters["minimum_score"] <= 1:
            raise ValueError("minimum_score must be between 0 and 1")
        if not 0 <= self.parameters["minimum_agreement"] <= 1:
            raise ValueError("minimum_agreement must be between 0 and 1")
        if not (
            0 < self.parameters["rsi_oversold_max"] < 50
            < self.parameters["rsi_overbought_min"] <= 100
        ):
            raise ValueError(
                "RSI extreme thresholds must be ordered around 50"
            )
        if any(
            self.parameters[key] < 0
            for key in ("rsi_weight", "bollinger_weight")
        ):
            raise ValueError("strategy weights cannot be negative")
        if (
            self.parameters["rsi_weight"]
            + self.parameters["bollinger_weight"]
            <= 0
        ):
            raise ValueError("strategy weights cannot all be zero")
