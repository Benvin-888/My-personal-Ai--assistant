"""Validated registry for configured APEX strategies."""

from __future__ import annotations

from .base import Strategy
from .config import StrategyConfig, StrategyConfigurationError
from .factory import StrategyFactory


class StrategyRegistryError(ValueError):
    """Raised when registry operations are invalid."""


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, Strategy] = {}
        self._configs: dict[str, StrategyConfig] = {}

    def register(
        self,
        strategy: Strategy,
        config: StrategyConfig | None = None,
    ) -> None:
        strategy_id = strategy.definition.strategy_id

        if strategy_id in self._strategies:
            raise StrategyRegistryError(
                f"Strategy already registered: {strategy_id}"
            )

        config = config or StrategyConfig(strategy_id=strategy_id)

        if config.strategy_id != strategy_id:
            raise StrategyRegistryError(
                "Configuration strategy_id must match the strategy definition."
            )

        self._validate_config(strategy, config)

        self._strategies[strategy_id] = strategy
        self._configs[strategy_id] = config

    def get(self, strategy_id: str) -> Strategy:
        try:
            return self._strategies[strategy_id]
        except KeyError as exc:
            raise StrategyRegistryError(
                f"Unknown strategy: {strategy_id}"
            ) from exc

    def get_configured(
        self,
        strategy_id: str,
        factory: StrategyFactory,
    ) -> Strategy:
        """Create a fresh strategy instance using the registered configuration."""
        if not isinstance(factory, StrategyFactory):
            raise StrategyRegistryError("factory must be a StrategyFactory.")

        config = self.get_config(strategy_id)
        if not config.enabled:
            raise StrategyRegistryError(
                f"Strategy is disabled: {config.strategy_id}"
            )

        try:
            strategy = factory.create(
                config.strategy_id,
                config.parameters,
            )
        except Exception as exc:
            if isinstance(exc, StrategyRegistryError):
                raise
            raise StrategyRegistryError(
                f"Unable to create configured strategy {config.strategy_id}: {exc}"
            ) from exc

        if strategy.definition.strategy_id != config.strategy_id:
            raise StrategyRegistryError(
                "Configured strategy identity does not match its registry configuration."
            )

        self._validate_config(strategy, config)
        return strategy

    def get_config(self, strategy_id: str) -> StrategyConfig:
        try:
            return self._configs[strategy_id]
        except KeyError as exc:
            raise StrategyRegistryError(
                f"Unknown strategy: {strategy_id}"
            ) from exc

    def list_ids(self) -> list[str]:
        return sorted(self._strategies)

    def list_enabled(self) -> list[str]:
        return [
            strategy_id
            for strategy_id in self.list_ids()
            if self._configs[strategy_id].enabled
        ]

    def set_enabled(self, strategy_id: str, enabled: bool) -> None:
        config = self.get_config(strategy_id)

        if not isinstance(enabled, bool):
            raise StrategyRegistryError("enabled must be a boolean.")

        self._configs[strategy_id] = StrategyConfig(
            strategy_id=config.strategy_id,
            enabled=enabled,
            parameters=config.parameters,
            pairs=config.pairs,
            timeframes=config.timeframes,
            weight=config.weight,
        )

    def compatible_enabled(
        self,
        pair: str,
        timeframe: str,
    ) -> list[str]:
        result: list[str] = []

        for strategy_id in self.list_enabled():
            config = self._configs[strategy_id]
            strategy = self._strategies[strategy_id]

            pair_allowed = (
                not config.pairs
                or self._pair_matches_any(pair, config.pairs)
            )
            timeframe_allowed = (
                not config.timeframes
                or self._timeframe_matches_any(timeframe, config.timeframes)
            )

            if (
                pair_allowed
                and timeframe_allowed
                and strategy.supports(pair, timeframe)
            ):
                result.append(strategy_id)

        return result

    @staticmethod
    def _pair_normalize(pair: str) -> str:
        return (
            str(pair)
            .replace("/", "")
            .replace("-", "")
            .replace(" ", "")
            .upper()
        )

    @classmethod
    def _pair_matches_any(
        cls,
        pair: str,
        configured_pairs: tuple[str, ...],
    ) -> bool:
        normalized = cls._pair_normalize(pair)
        return any(
            normalized == cls._pair_normalize(item)
            for item in configured_pairs
        )

    @staticmethod
    def _timeframe_matches_any(
        timeframe: str,
        configured_timeframes: tuple[str, ...],
    ) -> bool:
        normalized = str(timeframe).strip().lower()
        return any(
            normalized == str(item).strip().lower()
            for item in configured_timeframes
        )

    @classmethod
    def _validate_config(
        cls,
        strategy: Strategy,
        config: StrategyConfig,
    ) -> None:
        definition = strategy.definition

        # An empty supported_pairs tuple means the strategy accepts all
        # pairs. When pairs are explicitly configured, validate them against
        # the strategy's public supports() contract using the strategy's
        # declared timeframe.
        if config.pairs and definition.supported_pairs:
            supported = {
                cls._pair_normalize(pair)
                for pair in definition.supported_pairs
            }
            unsupported = [
                pair
                for pair in config.pairs
                if cls._pair_normalize(pair) not in supported
            ]
            if unsupported:
                raise StrategyConfigurationError(
                    f"Unsupported configured pairs: {sorted(unsupported)}"
                )

        # StrategyDefinition has a single timeframe field, not a
        # supported_timeframes collection. Configuration may narrow that
        # timeframe, but may not introduce another timeframe.
        if config.timeframes:
            expected = definition.timeframe.strip().lower()
            unsupported = [
                timeframe
                for timeframe in config.timeframes
                if str(timeframe).strip().lower() != expected
            ]
            if unsupported:
                raise StrategyConfigurationError(
                    f"Unsupported configured timeframes: {sorted(unsupported)}"
                )

        # Finally validate the configured pair/timeframe combinations through
        # the strategy's public compatibility contract. This catches strategy-
        # specific compatibility rules without assuming internal metadata.
        candidate_pairs = config.pairs or (
            definition.supported_pairs
            if definition.supported_pairs
            else ()
        )
        candidate_timeframes = config.timeframes or (definition.timeframe,)

        if candidate_pairs:
            invalid_pairs: set[str] = set()
            for pair in candidate_pairs:
                if not any(
                    strategy.supports(pair, timeframe)
                    for timeframe in candidate_timeframes
                ):
                    invalid_pairs.add(pair)

            if invalid_pairs:
                raise StrategyConfigurationError(
                    f"Unsupported configured pairs: {sorted(invalid_pairs)}"
                )
