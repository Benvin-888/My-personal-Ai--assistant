"""Deterministic APEX strategy coordinator."""
from .base import Strategy
from .models import EvaluationStatus, StrategyEvaluation

class StrategyEngine:
    def __init__(self, strategies=()):
        self._strategies = {}
        for strategy in strategies:
            self.register(strategy)

    def register(self, strategy):
        if not isinstance(strategy, Strategy):
            raise TypeError("strategy must inherit from Strategy")
        key = strategy.definition.strategy_id
        if key in self._strategies:
            raise ValueError(f"Strategy already registered: {key}")
        self._strategies[key] = strategy
        return strategy

    def get(self, strategy_id):
        return self._strategies.get(str(strategy_id).strip())

    def list_strategies(self):
        return [s.describe() for s in self._strategies.values()]

    def evaluate(self, strategy_id, analysis):
        strategy = self.get(strategy_id)
        if strategy is None:
            return self._error(None, f"Unknown strategy: {strategy_id}")
        if not isinstance(analysis, dict):
            return self._error(strategy, "Technical analysis must be a dictionary.")
        pair, interval = str(analysis.get("pair", "UNKNOWN")), str(analysis.get("interval", "UNKNOWN"))
        if not strategy.supports(pair, interval):
            return self._error(strategy, f"Strategy does not support {pair} on {interval}.", pair, interval)
        if not analysis.get("success", False):
            return self._error(strategy, "Cannot evaluate unsuccessful technical analysis.", pair, interval)
        try:
            result = strategy.evaluate(analysis)
            if not isinstance(result, StrategyEvaluation):
                return self._error(strategy, "Strategy returned an invalid evaluation object.", pair, interval)
            return result.to_dict()
        except Exception as exc:
            return self._error(strategy, f"Strategy evaluation error: {exc}", pair, interval, EvaluationStatus.ERROR)

    @staticmethod
    def _error(strategy, message, pair="UNKNOWN", interval="UNKNOWN", status=EvaluationStatus.INVALID_INPUT):
        if strategy is None:
            return {"success": False, "market": "forex", "analysis": "strategy", "status": status.value, "error": message}
        return StrategyEvaluation(strategy.definition, status, pair, interval, None, None, 0, 0, 0, error=message).to_dict()
