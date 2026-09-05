from __future__ import annotations

import pytest

from market.strategy import (
    StrategyConfig,
    StrategyRegistry,
    StrategyRegistryError,
    StrategyConfigurationError,
)
from market.strategy.strategies import TrendMomentumStrategy


def test_register_and_list() -> None:
    registry = StrategyRegistry()
    registry.register(TrendMomentumStrategy())
    assert registry.list_ids() == ["trend_momentum"]
    assert registry.list_enabled() == ["trend_momentum"]


def test_configuration_is_serializable() -> None:
    config = StrategyConfig(
        strategy_id="trend_momentum",
        enabled=True,
        parameters={"minimum_score": 0.7},
        pairs=("EURUSD",),
        timeframes=("5m",),
    )
    assert config.to_dict()["parameters"]["minimum_score"] == 0.7
    assert config.to_dict()["pairs"] == ["EURUSD"]


def test_duplicate_strategy_rejected() -> None:
    registry = StrategyRegistry()
    registry.register(TrendMomentumStrategy())
    with pytest.raises(StrategyRegistryError):
        registry.register(TrendMomentumStrategy())


def test_mismatched_config_rejected() -> None:
    registry = StrategyRegistry()
    with pytest.raises(StrategyRegistryError):
        registry.register(
            TrendMomentumStrategy(),
            StrategyConfig(strategy_id="other"),
        )


def test_unsupported_pair_rejected() -> None:
    registry = StrategyRegistry()
    with pytest.raises(StrategyConfigurationError):
        registry.register(
            TrendMomentumStrategy(),
            StrategyConfig(strategy_id="trend_momentum", pairs=("USDJPY",)),
        )


def test_enable_disable() -> None:
    registry = StrategyRegistry()
    registry.register(TrendMomentumStrategy())
    registry.set_enabled("trend_momentum", False)
    assert registry.list_enabled() == []
    registry.set_enabled("trend_momentum", True)
    assert registry.list_enabled() == ["trend_momentum"]


def test_compatible_enabled_strategies() -> None:
    registry = StrategyRegistry()
    registry.register(
        TrendMomentumStrategy(),
        StrategyConfig(
            strategy_id="trend_momentum",
            pairs=("EURUSD",),
            timeframes=("5m",),
        ),
    )
    assert registry.compatible_enabled("EURUSD", "5m") == ["trend_momentum"]
    assert registry.compatible_enabled("EURUSD", "1h") == []
    assert registry.compatible_enabled("USDJPY", "5m") == []


def test_disabled_strategy_is_not_compatible() -> None:
    registry = StrategyRegistry()
    registry.register(
        TrendMomentumStrategy(),
        StrategyConfig(strategy_id="trend_momentum", enabled=False),
    )
    assert registry.compatible_enabled("EURUSD", "5m") == []


def test_unknown_strategy_errors() -> None:
    registry = StrategyRegistry()
    with pytest.raises(StrategyRegistryError):
        registry.get("missing")


def test_invalid_enabled_value_rejected() -> None:
    with pytest.raises(StrategyConfigurationError):
        StrategyConfig(strategy_id="trend_momentum", enabled="yes")  # type: ignore[arg-type]
