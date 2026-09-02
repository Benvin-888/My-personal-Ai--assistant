"""Conservative EMA/RSI/MACD directional strategy."""
from ..base import Strategy
from ..models import ConditionStatus, EvaluationStatus, SignalDirection, StrategyCondition, StrategyDefinition, StrategyEvaluation, StrategySignal

class TrendMomentumStrategy(Strategy):
    DEFAULTS = {"rsi_bullish_min": 50.0, "rsi_bullish_max": 70.0, "rsi_bearish_min": 30.0, "rsi_bearish_max": 50.0, "minimum_score": 0.60, "trend_weight": 0.35, "slope_weight": 0.20, "rsi_weight": 0.20, "macd_weight": 0.25}

    def __init__(self, parameters=None):
        self.parameters = {**self.DEFAULTS, **(parameters or {})}
        self._validate()
        self._definition = StrategyDefinition(
            strategy_id="trend_momentum", name="Trend Momentum", version="1.0.0",
            description="Deterministic EMA trend, RSI and MACD alignment with conservative neutral fallback.",
            timeframe="5m", supported_pairs=(), minimum_candles=50,
            parameters=dict(self.parameters), tags=("trend", "momentum", "ema", "rsi", "macd"),
            metadata={"execution": "none", "backtest_ready": True, "signal_policy": "conservative_alignment"})

    @property
    def definition(self): return self._definition

    def evaluate(self, analysis):
        pair, interval = str(analysis.get("pair", "UNKNOWN")), str(analysis.get("interval", "UNKNOWN"))
        ts, count = analysis.get("latest_timestamp_utc"), analysis.get("candle_count", 0)
        if not isinstance(count, int) or count < self.definition.minimum_candles:
            return self._insufficient(pair, interval, ts, "Not enough candles for strategy evaluation.")
        ind = analysis.get("indicators", {})
        try:
            fast, slow = ind["ema_fast"]["value"], ind["ema_slow"]["value"]
            rsi, hist = ind["rsi"]["value"], ind["macd"]["histogram"]
        except (KeyError, TypeError):
            return self._insufficient(pair, interval, ts, "Required technical indicators are unavailable.")
        vals = (fast, slow, rsi, hist)
        if not all(isinstance(v, (int, float)) for v in vals):
            return self._insufficient(pair, interval, ts, "Required technical indicators are unavailable.")

        conditions = [
            self._trend(analysis.get("classification", {}).get("trend"), fast, slow),
            self._alignment(fast, slow),
            self._rsi(rsi),
            self._macd(hist),
        ]
        score = self._score(conditions)
        direction = self._direction(conditions, score)
        signal = StrategySignal(direction, score, self._rationale(direction, score, conditions), tuple(conditions), {"scoring": "weighted_directional_alignment", "minimum_score": self.parameters["minimum_score"]})
        return StrategyEvaluation(
            self.definition, EvaluationStatus.EVALUATED, pair, interval, ts, signal,
            len(conditions), sum(c.status == ConditionStatus.SATISFIED for c in conditions),
            sum(c.status == ConditionStatus.UNAVAILABLE for c in conditions),
            metadata={"latest_close": analysis.get("metadata", {}).get("latest_close"), "score": score, "complete": True, "volatility": analysis.get("classification", {}).get("volatility", "UNKNOWN")})

    def _trend(self, value, fast, slow):
        value = str(value or "").upper()
        if value == "BULLISH":
            return StrategyCondition("trend_alignment", "Trend alignment", "Technical trend classification is bullish.", ConditionStatus.SATISFIED, "trend", value, "BULLISH", self.parameters["trend_weight"])
        if value == "BEARISH":
            return StrategyCondition("trend_alignment", "Trend alignment", "Technical trend classification is bearish.", ConditionStatus.SATISFIED, "trend", value, "BEARISH", self.parameters["trend_weight"])
        if value == "INSUFFICIENT_DATA":
            return StrategyCondition("trend_alignment", "Trend alignment", "Trend classification is unavailable.", ConditionStatus.UNAVAILABLE, "trend", value, "BULLISH or BEARISH", self.parameters["trend_weight"])
        return StrategyCondition("trend_alignment", "Trend alignment", "Trend classification does not establish direction.", ConditionStatus.NOT_SATISFIED, "trend", value, "BULLISH or BEARISH", self.parameters["trend_weight"])

    def _alignment(self, fast, slow):
        if fast > slow:
            return StrategyCondition("ema_alignment", "EMA alignment", "Fast EMA is above slow EMA.", ConditionStatus.SATISFIED, "trend", fast, "fast EMA > slow EMA", self.parameters["trend_weight"])
        if fast < slow:
            return StrategyCondition("ema_alignment", "EMA alignment", "Fast EMA is below slow EMA.", ConditionStatus.SATISFIED, "trend", fast, "fast EMA < slow EMA", self.parameters["trend_weight"])
        return StrategyCondition("ema_alignment", "EMA alignment", "EMAs are equal.", ConditionStatus.NOT_SATISFIED, "trend", fast, "directional alignment", self.parameters["trend_weight"])

    def _rsi(self, value):
        bullish = self.parameters["rsi_bullish_min"] <= value <= self.parameters["rsi_bullish_max"]
        bearish = self.parameters["rsi_bearish_min"] <= value <= self.parameters["rsi_bearish_max"]
        if bullish or bearish:
            expected = "bullish confirmation zone" if value > 50 else "bearish confirmation zone"
            return StrategyCondition("rsi_confirmation", "RSI confirmation", "RSI is inside a configured confirmation zone.", ConditionStatus.SATISFIED, "momentum", value, expected, self.parameters["rsi_weight"])
        return StrategyCondition("rsi_confirmation", "RSI confirmation", "RSI is outside the configured confirmation zones.", ConditionStatus.NOT_SATISFIED, "momentum", value, "confirmation zone", self.parameters["rsi_weight"])

    def _macd(self, value):
        if value == 0:
            status = ConditionStatus.NOT_SATISFIED
        else:
            status = ConditionStatus.SATISFIED
        return StrategyCondition("macd_confirmation", "MACD confirmation", "MACD histogram provides directional momentum.", status, "momentum", value, "non-zero histogram", self.parameters["macd_weight"])

    def _score(self, conditions):
        total = weight = 0.0
        for c in conditions:
            if c.status == ConditionStatus.UNAVAILABLE: continue
            if c.condition_id == "trend_alignment": d = 1 if c.value == "BULLISH" else -1 if c.value == "BEARISH" else 0
            elif c.condition_id == "ema_alignment": d = 1 if "above" in str(c.expected) else -1 if "below" in str(c.expected) else 0
            elif c.condition_id == "rsi_confirmation": d = 1 if isinstance(c.value, (int,float)) and c.value > 50 else -1 if isinstance(c.value, (int,float)) and c.value < 50 else 0
            else: d = 1 if c.value > 0 else -1 if c.value < 0 else 0
            total += d * c.weight; weight += c.weight
        return max(-1.0, min(1.0, total / weight if weight else 0.0))

    def _direction(self, conditions, score):
        if abs(score) < self.parameters["minimum_score"]: return SignalDirection.NEUTRAL
        align = next(c for c in conditions if c.condition_id == "ema_alignment")
        if score > 0 and ">" in str(align.expected): return SignalDirection.LONG
        if score < 0 and "<" in str(align.expected): return SignalDirection.SHORT
        return SignalDirection.NEUTRAL

    @staticmethod
    def _rationale(direction, score, conditions):
        names = ", ".join(c.name for c in conditions if c.status == ConditionStatus.SATISFIED)
        if direction == SignalDirection.NEUTRAL: return f"No sufficiently aligned directional conclusion; weighted score={score:.3f}."
        return f"{direction.value} conclusion from {names}; weighted score={score:.3f}."

    def _insufficient(self, pair, interval, ts, message):
        return StrategyEvaluation(self.definition, EvaluationStatus.INSUFFICIENT_DATA, pair, interval, ts, None, 0, 0, 0, error=message)

    def _validate(self):
        numeric = ("rsi_bullish_min", "rsi_bullish_max", "rsi_bearish_min", "rsi_bearish_max", "minimum_score", "trend_weight", "slope_weight", "rsi_weight", "macd_weight")
        if any(not isinstance(self.parameters[k], (int,float)) or isinstance(self.parameters[k], bool) for k in numeric): raise ValueError("strategy parameters must be numeric")
        if not 0 <= self.parameters["minimum_score"] <= 1: raise ValueError("minimum_score must be between 0 and 1")
        if sum(self.parameters[k] for k in ("trend_weight","slope_weight","rsi_weight","macd_weight")) <= 0: raise ValueError("strategy weights cannot all be zero")
