"""
APEX Strategy interface.

Phase 2.4.1 - Strategy Foundation

Concrete strategies implement evaluate(). The interface deliberately returns
structured results and has no execution/broker responsibilities.
"""

from abc import ABC, abstractmethod
from typing import Any

from .models import StrategyDefinition, StrategyEvaluation


class Strategy(ABC):
    """Base contract for deterministic APEX strategies."""

    @property
    @abstractmethod
    def definition(self) -> StrategyDefinition:
        """Return immutable strategy metadata/configuration."""
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, analysis: dict[str, Any]) -> StrategyEvaluation:
        """Evaluate a technical-analysis result without executing anything."""
        raise NotImplementedError

    def supports(self, pair: str, interval: str) -> bool:
        """Return whether this strategy accepts the pair/timeframe."""
        definition = self.definition
        pair_normalized = str(pair).replace("/", "").replace("-", "").replace(" ", "").upper()

        pair_supported = (
            not definition.supported_pairs
            or pair_normalized in {
                item.replace("/", "").replace("-", "").replace(" ", "").upper()
                for item in definition.supported_pairs
            }
        )
        interval_supported = str(interval).strip().lower() == definition.timeframe.strip().lower()
        return pair_supported and interval_supported

    def describe(self) -> dict[str, Any]:
        """Return a serializable strategy description."""
        return self.definition.to_dict()
