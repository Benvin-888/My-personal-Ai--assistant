from market.strategy import (
    EvaluationStatus,
    StrategyConfig,
    StrategyEngine,
    StrategyFactory,
    StrategyFactoryError,
    StrategyRegistry,
    StrategyRegistryError,
)
from market.strategy.strategies import TrendMomentumStrategy


def analysis(ema_fast=1.161, ema_slow=1.160, rsi=60, hist=.0002, candles=100, interval="5m"):
    return {
        "success": True,
        "pair": "EURUSD",
        "interval": interval,
        "candle_count": candles,
        "latest_timestamp_utc": "2026-09-03T07:33:49Z",
        "indicators": {
            "ema_fast": {"value": ema_fast},
            "ema_slow": {"value": ema_slow},
            "rsi": {"value": rsi},
            "macd": {"histogram": hist},
        },
        "classification": {
            "trend": "BULLISH" if ema_fast > ema_slow else "BEARISH" if ema_fast < ema_slow else "NEUTRAL",
            "volatility": "LOW",
        },
        "metadata": {"latest_close": 1.1611},
    }


def factory():
    f = StrategyFactory()
    f.register("trend_momentum", TrendMomentumStrategy)
    return f


def test_factory_registers_and_creates_strategy():
    f = factory()
    strategy = f.create("trend_momentum", {"minimum_score": .7})
    assert isinstance(strategy, TrendMomentumStrategy)
    assert strategy.definition.parameters["minimum_score"] == .7


def test_factory_rejects_unknown_constructor():
    f = factory()
    try:
        f.create("missing")
        assert False
    except StrategyFactoryError:
        pass


def test_factory_rejects_identity_mismatch():
    f = StrategyFactory()
    f.register("other", TrendMomentumStrategy)
    try:
        f.create("other")
        assert False
    except StrategyFactoryError:
        pass


def test_registry_creates_configured_strategy():
    registry = StrategyRegistry()
    registry.register(
        TrendMomentumStrategy(),
        StrategyConfig(
            strategy_id="trend_momentum",
            parameters={"minimum_score": .7},
        ),
    )
    strategy = registry.get_configured("trend_momentum", factory())
    assert strategy.definition.parameters["minimum_score"] == .7


def test_registry_rejects_disabled_configuration_resolution():
    registry = StrategyRegistry()
    registry.register(
        TrendMomentumStrategy(),
        StrategyConfig(strategy_id="trend_momentum", enabled=False),
    )
    try:
        registry.get_configured("trend_momentum", factory())
        assert False
    except StrategyRegistryError:
        pass


def test_configured_evaluation_uses_registry_parameters():
    registry = StrategyRegistry()
    registry.register(
        TrendMomentumStrategy(),
        StrategyConfig(
            strategy_id="trend_momentum",
            parameters={"minimum_score": .50, "minimum_agreement": .80},
        ),
    )
    result = StrategyEngine().evaluate_configured(
        "trend_momentum", analysis(rsi=40), registry, factory()
    )
    assert result["status"] == EvaluationStatus.EVALUATED.value
    assert result["strategy"]["parameters"]["minimum_score"] == .50
    assert result["strategy"]["parameters"]["minimum_agreement"] == .80
    assert result["signal"]["direction"] == "LONG"


def test_configured_evaluation_preserves_defaults_for_unconfigured_values():
    registry = StrategyRegistry()
    registry.register(
        TrendMomentumStrategy(),
        StrategyConfig(
            strategy_id="trend_momentum",
            parameters={"minimum_score": .7},
        ),
    )
    result = StrategyEngine().evaluate_configured(
        "trend_momentum", analysis(), registry, factory()
    )
    params = result["strategy"]["parameters"]
    assert params["minimum_score"] == .7
    assert params["minimum_agreement"] == .85
    assert params["rsi_bullish_min"] == 52.0


def test_configured_evaluation_rejects_incompatible_analysis():
    registry = StrategyRegistry()
    registry.register(
        TrendMomentumStrategy(),
        StrategyConfig(
            strategy_id="trend_momentum",
            pairs=("EURUSD",),
            timeframes=("5m",),
        ),
    )
    result = StrategyEngine().evaluate_configured(
        "trend_momentum", analysis(interval="1h"), registry, factory()
    )
    assert result["status"] == EvaluationStatus.INVALID_INPUT.value


def test_factory_does_not_mutate_parameter_mapping():
    parameters = {"minimum_score": .7}
    strategy = factory().create("trend_momentum", parameters)
    parameters["minimum_score"] = .9
    assert strategy.definition.parameters["minimum_score"] == .7
