"""Conservative, direction-aware EMA/RSI/MACD strategy."""

from math import isfinite

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


class TrendMomentumStrategy(Strategy):
    """Evaluate directional agreement without producing execution instructions."""

    DEFAULTS = {
        "rsi_bullish_min": 52.0,
        "rsi_bullish_max": 68.0,
        "rsi_bearish_min": 32.0,
        "rsi_bearish_max": 48.0,
        "minimum_score": 0.60,
        "minimum_agreement": 0.85,
        "trend_weight": 0.30,
        "ema_weight": 0.30,
        "rsi_weight": 0.20,
        "macd_weight": 0.20,
    }

    def __init__(self, parameters=None):
        self.parameters = {**self.DEFAULTS, **(parameters or {})}
        self._validate()

        self._definition = StrategyDefinition(
            strategy_id="trend_momentum",
            name="Trend Momentum",
            version="1.1.1",
            description=(
                "Deterministic EMA trend, EMA alignment, RSI and direction-aware "
                "MACD confirmation with conflict-aware conservative scoring."
            ),
            timeframe="5m",
            supported_pairs=("EURUSD",),
            minimum_candles=50,
            parameters=dict(self.parameters),
            tags=("trend", "momentum", "ema", "rsi", "macd", "deterministic"),
            metadata={
                "execution": "none",
                "backtest_ready": True,
                "signal_policy": "conflict_aware_alignment",
                "versioning_policy": "semantic",
            },
        )

    @property
    def definition(self):
        return self._definition

    def evaluate(self, analysis):
        pair = str(analysis.get("pair", "UNKNOWN"))
        interval = str(analysis.get("interval", "UNKNOWN"))
        timestamp = analysis.get("latest_timestamp_utc")
        candle_count = analysis.get("candle_count", 0)

        if (
            not isinstance(candle_count, int)
            or candle_count < self.definition.minimum_candles
        ):
            return self._insufficient(
                pair,
                interval,
                timestamp,
                "Not enough candles for strategy evaluation.",
            )

        indicators = analysis.get("indicators")
        classification = analysis.get("classification")

        if not isinstance(indicators, dict) or not isinstance(classification, dict):
            return self._insufficient(
                pair,
                interval,
                timestamp,
                "Technical-analysis structure is unavailable.",
            )

        try:
            fast = indicators["ema_fast"]["value"]
            slow = indicators["ema_slow"]["value"]
            rsi = indicators["rsi"]["value"]
            histogram = indicators["macd"]["histogram"]
            trend = str(classification.get("trend", "")).upper()
        except (KeyError, TypeError):
            return self._insufficient(
                pair,
                interval,
                timestamp,
                "Required technical indicators are unavailable.",
            )

        values = (fast, slow, rsi, histogram)

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
                "Required technical indicators are unavailable.",
            )

        observed_bias = self._determine_observed_bias(trend, fast, slow)

        if observed_bias is None:
            conditions = self._neutral_conditions(trend, fast, slow)

            signal = StrategySignal(
                SignalDirection.NEUTRAL,
                0.0,
                "Trend and EMA alignment do not establish a directional bias.",
                tuple(conditions),
                self._signal_metadata(0.0, 0.0, None),
            )

            return self._evaluation(
                pair,
                interval,
                timestamp,
                conditions,
                signal,
                classification,
                analysis,
            )

        conditions = [
            self._trend(trend, observed_bias),
            self._alignment(fast, slow, observed_bias),
            self._rsi(rsi, observed_bias),
            self._macd(histogram, observed_bias),
        ]

        score = self._score(conditions)
        agreement = self._agreement(conditions, observed_bias)
        direction = self._direction(score, agreement, observed_bias)

        rationale = self._rationale(
            direction,
            observed_bias,
            score,
            agreement,
            conditions,
        )

        signal = StrategySignal(
            direction,
            score,
            rationale,
            tuple(conditions),
            self._signal_metadata(score, agreement, observed_bias),
        )

        return self._evaluation(
            pair,
            interval,
            timestamp,
            conditions,
            signal,
            classification,
            analysis,
        )

    @staticmethod
    def _determine_observed_bias(trend, fast, slow):
        ema_bias = (
            SignalDirection.LONG
            if fast > slow
            else SignalDirection.SHORT
            if fast < slow
            else None
        )

        trend_bias = (
            SignalDirection.LONG
            if trend == "BULLISH"
            else SignalDirection.SHORT
            if trend == "BEARISH"
            else None
        )

        if ema_bias is None or trend_bias is None or ema_bias != trend_bias:
            return None

        return ema_bias

    def _trend(self, value, bias):
        expected = "BULLISH" if bias == SignalDirection.LONG else "BEARISH"
        actual = str(value).upper()

        status = (
            ConditionStatus.SATISFIED
            if actual == expected
            else ConditionStatus.NOT_SATISFIED
        )

        return StrategyCondition(
            "trend_alignment",
            "Trend alignment",
            f"Technical trend classification is {expected.lower()}.",
            status,
            "trend",
            actual,
            expected,
            self.parameters["trend_weight"],
            direction=bias,
        )

    def _alignment(self, fast, slow, bias):
        if bias == SignalDirection.LONG:
            satisfied = fast > slow
            expected = "fast EMA > slow EMA"
        else:
            satisfied = fast < slow
            expected = "fast EMA < slow EMA"

        return StrategyCondition(
            "ema_alignment",
            "EMA alignment",
            "Fast and slow EMAs are directionally aligned.",
            (
                ConditionStatus.SATISFIED
                if satisfied
                else ConditionStatus.NOT_SATISFIED
            ),
            "trend",
            fast,
            expected,
            self.parameters["ema_weight"],
            direction=bias,
            metadata={
                "fast_ema": fast,
                "slow_ema": slow,
            },
        )

    def _rsi(self, value, bias):
        if (
            self.parameters["rsi_bullish_min"]
            <= value
            <= self.parameters["rsi_bullish_max"]
        ):
            observed = SignalDirection.LONG

            expected = (
                f"{self.parameters['rsi_bullish_min']:.1f} "
                f"<= RSI <= "
                f"{self.parameters['rsi_bullish_max']:.1f}"
            )

        elif (
            self.parameters["rsi_bearish_min"]
            <= value
            <= self.parameters["rsi_bearish_max"]
        ):
            observed = SignalDirection.SHORT

            expected = (
                f"{self.parameters['rsi_bearish_min']:.1f} "
                f"<= RSI <= "
                f"{self.parameters['rsi_bearish_max']:.1f}"
            )

        else:
            observed = None
            expected = "directional RSI confirmation zone"

        status = (
            ConditionStatus.SATISFIED
            if observed == bias
            else ConditionStatus.NOT_SATISFIED
            if observed
            else ConditionStatus.UNAVAILABLE
        )

        return StrategyCondition(
            "rsi_confirmation",
            "RSI confirmation",
            "RSI is inside a configured directional confirmation zone.",
            status,
            "momentum",
            value,
            expected,
            self.parameters["rsi_weight"],
            direction=observed,
        )

    def _macd(self, value, bias):
        if value > 0:
            observed = SignalDirection.LONG
            expected = "MACD histogram > 0"

        elif value < 0:
            observed = SignalDirection.SHORT
            expected = "MACD histogram < 0"

        else:
            observed = None
            expected = "non-zero MACD histogram"

        status = (
            ConditionStatus.SATISFIED
            if observed == bias
            else ConditionStatus.NOT_SATISFIED
            if observed
            else ConditionStatus.UNAVAILABLE
        )

        return StrategyCondition(
            "macd_confirmation",
            "MACD confirmation",
            "MACD histogram direction is compared with the strategy bias.",
            status,
            "momentum",
            value,
            expected,
            self.parameters["macd_weight"],
            direction=observed,
        )

    @staticmethod
    def _neutral_conditions(trend, fast, slow):
        return [
            StrategyCondition(
                "trend_alignment",
                "Trend alignment",
                "Trend does not establish a usable directional bias.",
                ConditionStatus.NOT_SATISFIED,
                "trend",
                trend,
                "BULLISH and EMA-aligned or BEARISH and EMA-aligned",
                0.0,
            ),
            StrategyCondition(
                "ema_alignment",
                "EMA alignment",
                "EMA relationship does not establish a directional bias.",
                ConditionStatus.NOT_SATISFIED,
                "trend",
                fast,
                "directional EMA alignment",
                0.0,
                metadata={
                    "fast_ema": fast,
                    "slow_ema": slow,
                },
            ),
        ]

    @staticmethod
    def _score(conditions):
        total_weight = sum(
            c.weight
            for c in conditions
            if (
                c.status != ConditionStatus.UNAVAILABLE
                and c.direction is not None
                and c.weight > 0
            )
        )

        if total_weight == 0:
            return 0.0

        total = sum(
            c.weight
            * (
                1
                if c.direction == SignalDirection.LONG
                else -1
            )
            for c in conditions
            if (
                c.status != ConditionStatus.UNAVAILABLE
                and c.direction is not None
                and c.weight > 0
            )
        )

        return max(-1.0, min(1.0, total / total_weight))

    @staticmethod
    def _agreement(conditions, bias):
        available = sum(
            c.weight
            for c in conditions
            if (
                c.status != ConditionStatus.UNAVAILABLE
                and c.direction is not None
                and c.weight > 0
            )
        )

        aligned = sum(
            c.weight
            for c in conditions
            if (
                c.status == ConditionStatus.SATISFIED
                and c.direction == bias
                and c.weight > 0
            )
        )

        return aligned / available if available else 0.0

    def _direction(self, score, agreement, bias):
        if (
            abs(score) < self.parameters["minimum_score"]
            or agreement < self.parameters["minimum_agreement"]
        ):
            return SignalDirection.NEUTRAL

        if (
            score > 0
            and bias == SignalDirection.LONG
        ):
            return SignalDirection.LONG

        if (
            score < 0
            and bias == SignalDirection.SHORT
        ):
            return SignalDirection.SHORT

        return SignalDirection.NEUTRAL

    @staticmethod
    def _rationale(direction, bias, score, agreement, conditions):
        satisfied = sum(
            c.status == ConditionStatus.SATISFIED
            for c in conditions
        )

        unavailable = sum(
            c.status == ConditionStatus.UNAVAILABLE
            for c in conditions
        )

        if direction == SignalDirection.NEUTRAL:
            return (
                f"No sufficiently aligned directional conclusion; "
                f"bias={bias.value}, "
                f"score={score:.3f}, "
                f"agreement={agreement:.3f}, "
                f"satisfied={satisfied}/{len(conditions)}, "
                f"unavailable={unavailable}."
            )

        return (
            f"{direction.value} conclusion from directional alignment; "
            f"score={score:.3f}, "
            f"agreement={agreement:.3f}, "
            f"satisfied={satisfied}/{len(conditions)}."
        )

    def _evaluation(
        self,
        pair,
        interval,
        timestamp,
        conditions,
        signal,
        classification,
        analysis,
    ):
        return StrategyEvaluation(
            self.definition,
            EvaluationStatus.EVALUATED,
            pair,
            interval,
            timestamp,
            signal,
            len(conditions),
            sum(
                c.status == ConditionStatus.SATISFIED
                for c in conditions
            ),
            sum(
                c.status == ConditionStatus.UNAVAILABLE
                for c in conditions
            ),
            metadata={
                "latest_close": analysis.get("metadata", {}).get("latest_close"),
                "complete": all(
                    c.status != ConditionStatus.UNAVAILABLE
                    for c in conditions
                ),
                "volatility": classification.get(
                    "volatility",
                    "UNKNOWN",
                ),
                "decision_policy": "bias_then_confirmation",
            },
        )

    def _signal_metadata(self, score, agreement, bias):
        return {
            "scoring": "conflict_aware_weighted_alignment",
            "minimum_score": self.parameters["minimum_score"],
            "minimum_agreement": self.parameters["minimum_agreement"],
            "directional_bias": (
                bias.value
                if bias
                else None
            ),
            "agreement": round(agreement, 6),
        }

    def _insufficient(
        self,
        pair,
        interval,
        timestamp,
        message,
    ):
        return StrategyEvaluation(
            self.definition,
            EvaluationStatus.INSUFFICIENT_DATA,
            pair,
            interval,
            timestamp,
            None,
            0,
            0,
            0,
            error=message,
        )

    def _validate(self):
        numeric = (
            "rsi_bullish_min",
            "rsi_bullish_max",
            "rsi_bearish_min",
            "rsi_bearish_max",
            "minimum_score",
            "minimum_agreement",
            "trend_weight",
            "ema_weight",
            "rsi_weight",
            "macd_weight",
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
            raise ValueError(
                "minimum_score must be between 0 and 1"
            )

        if not 0 <= self.parameters["minimum_agreement"] <= 1:
            raise ValueError(
                "minimum_agreement must be between 0 and 1"
            )

        if not (
            self.parameters["rsi_bearish_min"]
            < self.parameters["rsi_bearish_max"]
            < 50
            < self.parameters["rsi_bullish_min"]
            < self.parameters["rsi_bullish_max"]
            <= 100
        ):
            raise ValueError(
                "RSI zones must be ordered and separated around 50"
            )

        if any(
            self.parameters[key] < 0
            for key in (
                "trend_weight",
                "ema_weight",
                "rsi_weight",
                "macd_weight",
            )
        ):
            raise ValueError(
                "strategy weights cannot be negative"
            )

        if sum(
            self.parameters[key]
            for key in (
                "trend_weight",
                "ema_weight",
                "rsi_weight",
                "macd_weight",
            )
        ) <= 0:
            raise ValueError(
                "strategy weights cannot all be zero"
            )