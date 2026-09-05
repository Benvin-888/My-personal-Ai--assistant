"""Deterministic APEX strategy coordinator."""

from .base import Strategy
from .factory import StrategyFactory
from .models import EvaluationStatus, StrategyEvaluation
from .registry import StrategyRegistry


class StrategyEngine:
    """Register and evaluate strategies without execution responsibilities."""

    def __init__(self, strategies=()):
        self._strategies = {}
        for strategy in strategies:
            self.register(strategy)

    def register(self, strategy):
        if not isinstance(strategy, Strategy):
            raise TypeError("strategy must inherit from Strategy")
        key = strategy.definition.strategy_id.strip()
        if not key:
            raise ValueError("strategy_id cannot be empty")
        if key in self._strategies:
            raise ValueError(f"Strategy already registered: {key}")
        self._strategies[key] = strategy
        return strategy

    def get(self, strategy_id):
        return self._strategies.get(str(strategy_id).strip())

    def list_strategies(self):
        return [strategy.describe() for strategy in self._strategies.values()]

    def evaluate_configured(
        self,
        strategy_id,
        analysis,
        registry: StrategyRegistry,
        factory: StrategyFactory,
    ):
        """Evaluate the registry configuration for one strategy.

        The configured strategy instance is created from the registry's
        validated parameters for this evaluation. The ordinary ``evaluate``
        method remains available for directly registered strategy instances.
        """
        if not isinstance(registry, StrategyRegistry):
            raise TypeError("registry must be a StrategyRegistry")
        if not isinstance(factory, StrategyFactory):
            raise TypeError("factory must be a StrategyFactory")

        strategy = None
        try:
            strategy = registry.get_configured(strategy_id, factory)
        except Exception as exc:
            return self._error(
                None,
                str(exc),
            )

        return self._evaluate_strategy(strategy, analysis)

    def evaluate(self, strategy_id, analysis):
        strategy = self.get(strategy_id)
        if strategy is None:
            return self._error(None, f"Unknown strategy: {strategy_id}")
        return self._evaluate_strategy(strategy, analysis)

    @staticmethod
    def _evaluate_strategy(strategy, analysis):
        if not isinstance(analysis, dict):
            return StrategyEngine._error(
                strategy,
                "Technical analysis must be a dictionary.",
            )

        pair = str(analysis.get("pair", "UNKNOWN"))
        interval = str(analysis.get("interval", "UNKNOWN"))
        if not strategy.supports(pair, interval):
            return StrategyEngine._error(
                strategy,
                f"Strategy does not support {pair} on {interval}.",
                pair,
                interval,
            )
        if not analysis.get("success", False):
            return StrategyEngine._error(
                strategy,
                "Cannot evaluate unsuccessful technical analysis.",
                pair,
                interval,
            )

        try:
            result = strategy.evaluate(analysis)
            if not isinstance(result, StrategyEvaluation):
                return StrategyEngine._error(
                    strategy,
                    "Strategy returned an invalid evaluation object.",
                    pair,
                    interval,
                )
            if result.pair != pair or result.interval != interval:
                return StrategyEngine._error(
                    strategy,
                    "Strategy returned mismatched market identity.",
                    pair,
                    interval,
                )
            return result.to_dict()
        except Exception as exc:
            return StrategyEngine._error(
                strategy,
                f"Strategy evaluation error: {exc}",
                pair,
                interval,
                EvaluationStatus.ERROR,
            )

    @staticmethod
    def _error(strategy, message, pair="UNKNOWN", interval="UNKNOWN", status=EvaluationStatus.INVALID_INPUT):
        if strategy is None:
            return {"success": False, "market": "forex", "analysis": "strategy", "status": status.value, "error": message}
        return StrategyEvaluation(
            strategy.definition, status, pair, interval, None, None, 0, 0, 0, error=message
        ).to_dict()
