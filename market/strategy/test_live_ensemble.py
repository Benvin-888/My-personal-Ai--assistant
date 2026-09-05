"""Deterministic tests for the live ensemble orchestration boundary."""

from market.strategy import StrategyConfig, StrategyFactory, StrategyRegistry
from market.strategy.base import Strategy
from market.strategy.models import EvaluationStatus, StrategyDefinition, StrategyEvaluation
from market.strategy.ensemble import EnsembleConfig, EnsembleEngine
from market.strategy.live_ensemble import (
    LiveEnsembleWorkflow,
    LiveEnsembleWorkflowError,
    build_default_strategy_factory,
    build_default_strategy_registry,
)
from market.strategy.strategies import MeanReversionStrategy, TrendMomentumStrategy


def technical_analysis():
    return {
        "success": True,
        "market": "forex",
        "analysis": "technical",
        "pair": "EURUSD",
        "interval": "5m",
        "candle_count": 100,
        "latest_timestamp_utc": "2026-09-04T18:00:00Z",
        "classification": {
            "trend": "BULLISH",
            "momentum": "BULLISH",
            "volatility": "LOW",
        },
        "indicators": {
            "ema_fast": {"value": 1.1620},
            "ema_slow": {"value": 1.1610},
            "rsi": {"value": 60.0},
            "macd": {"histogram": 0.0002},
            "bollinger_bands": {
                "middle": 1.1610,
                "upper": 1.1630,
                "lower": 1.1590,
            },
        },
        "metadata": {"latest_close": 1.1621},
    }


class FakeMarketService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def analyze_forex_history(self, pair, **kwargs):
        self.calls.append((pair, kwargs))
        return self.result


class FailingStrategy(Strategy):
    """Registered strategy whose factory constructor fails for isolation tests."""

    @property
    def definition(self):
        return StrategyDefinition(
            strategy_id="failing_strategy",
            name="Failing Strategy",
            version="1.0.0",
            description="Test-only strategy that never evaluates.",
            timeframe="5m",
            supported_pairs=(),
            minimum_candles=20,
        )

    def evaluate(self, analysis):
        return StrategyEvaluation(
            strategy=self.definition,
            status=EvaluationStatus.ERROR,
            pair=str(analysis.get("pair", "UNKNOWN")),
            interval=str(analysis.get("interval", "UNKNOWN")),
            timestamp_utc=analysis.get("latest_timestamp_utc"),
            signal=None,
            condition_count=0,
            satisfied_count=0,
            unavailable_count=0,
            error="test failure",
        )


def test_default_factory_and_registry_are_compatible():
    factory = build_default_strategy_factory()
    registry = build_default_strategy_registry()

    assert factory.list_ids() == ["mean_reversion", "trend_momentum"]
    assert registry.list_ids() == ["mean_reversion", "trend_momentum"]
    assert registry.compatible_enabled("EURUSD", "5m") == ["mean_reversion", "trend_momentum"]


def test_workflow_runs_analysis_then_ensemble():
    service = FakeMarketService(technical_analysis())
    workflow = LiveEnsembleWorkflow(
        market_service=service,
        ensemble_engine=EnsembleEngine(EnsembleConfig(minimum_active_strategies=1)),
    )

    result = workflow.run("EURUSD", data_range="1d", interval="5m", limit=100)

    assert result["success"] is True
    assert result["workflow"] == "technical_analysis_strategy_ensemble"
    assert result["technical_analysis"]["success"] is True
    assert result["ensemble"]["success"] is True
    assert result["ensemble"]["decision"] == "LONG"
    assert result["ensemble"]["strategies"]["active"] == 2
    assert result["ensemble"]["strategies"]["evaluated"] == 2
    assert service.calls[0][0] == "EURUSD"
    assert service.calls[0][1]["interval"] == "5m"


def test_workflow_skips_ensemble_when_analysis_fails():
    failed = {
        "success": False,
        "market": "forex",
        "analysis": "technical",
        "pair": "EURUSD",
        "interval": "5m",
        "error": "provider unavailable",
    }
    service = FakeMarketService(failed)
    workflow = LiveEnsembleWorkflow(market_service=service)

    result = workflow.run("EURUSD")

    assert result["success"] is False
    assert result["ensemble"] is None
    assert result["technical_analysis"]["error"] == "provider unavailable"


def test_workflow_rejects_invalid_limit():
    workflow = LiveEnsembleWorkflow(market_service=FakeMarketService(technical_analysis()))

    try:
        workflow.run("EURUSD", limit=0)
        assert False
    except LiveEnsembleWorkflowError:
        pass


def test_workflow_runs_two_independent_strategies():
    registry = build_default_strategy_registry()
    factory = build_default_strategy_factory()
    workflow = LiveEnsembleWorkflow(
        market_service=FakeMarketService(technical_analysis()),
        registry=registry,
        factory=factory,
        ensemble_engine=EnsembleEngine(
            EnsembleConfig(minimum_active_strategies=2)
        ),
    )

    result = workflow.run("EURUSD")

    assert result["ensemble"]["strategies"]["active"] == 2
    assert result["ensemble"]["strategies"]["evaluated"] == 2
    assert result["ensemble"]["strategies"]["failed"] == 0
    assert [
        item["strategy_id"]
        for item in result["ensemble"]["contributions"]
    ] == ["mean_reversion", "trend_momentum"]


def test_workflow_preserves_independent_strategy_conflict_evidence():
    payload = technical_analysis()
    payload["indicators"]["rsi"]["value"] = 75.0
    payload["metadata"]["latest_close"] = 1.1630
    payload["indicators"]["bollinger_bands"] = {
        "middle": 1.1620,
        "upper": 1.1630,
        "lower": 1.1610,
    }

    # Trend/momentum remains LONG; mean reversion sees an overbought band
    # touch and therefore provides independent SHORT evidence.
    workflow = LiveEnsembleWorkflow(
        market_service=FakeMarketService(payload),
        ensemble_engine=EnsembleEngine(
            EnsembleConfig(
                minimum_active_strategies=2,
                minimum_score=0.60,
                minimum_agreement=0.80,
            )
        ),
    )

    result = workflow.run("EURUSD")
    ensemble = result["ensemble"]

    assert ensemble["strategies"]["evaluated"] == 2
    assert ensemble["strategies"]["long"] == 1
    assert ensemble["strategies"]["short"] == 1
    assert ensemble["conflict"] > 0.0
    assert ensemble["metadata"]["raw_decision"] == "NEUTRAL"
    assert ensemble["decision"] == "NEUTRAL"
    assert ensemble["agreement"] == 0.5


def test_workflow_accepts_custom_configured_registry_and_factory():
    registry = StrategyRegistry()
    registry.register(
        TrendMomentumStrategy(),
        StrategyConfig(
            strategy_id="trend_momentum",
            parameters={"minimum_score": 0.50, "minimum_agreement": 0.80},
        ),
    )

    factory = StrategyFactory()
    factory.register("trend_momentum", TrendMomentumStrategy)

    workflow = LiveEnsembleWorkflow(
        market_service=FakeMarketService(technical_analysis()),
        registry=registry,
        factory=factory,
        ensemble_engine=EnsembleEngine(),
    )

    result = workflow.run("EURUSD")

    assert result["ensemble"]["success"] is True
    assert result["ensemble"]["contributions"][0]["strategy_id"] == "trend_momentum"


def test_workflow_rejects_non_mapping_indicator_options():
    workflow = LiveEnsembleWorkflow(market_service=FakeMarketService(technical_analysis()))

    try:
        workflow.run("EURUSD", indicator_options=[("rsi_period", 14)])
        assert False
    except LiveEnsembleWorkflowError:
        pass


def test_workflow_produces_directional_consensus_from_two_independent_strategies():
    payload = technical_analysis()
    payload["indicators"]["rsi"]["value"] = 25.0
    payload["indicators"]["bollinger_bands"] = {
        "middle": 1.1610,
        "upper": 1.1630,
        "lower": 1.1605,
    }
    payload["metadata"]["latest_close"] = 1.1604

    workflow = LiveEnsembleWorkflow(
        market_service=FakeMarketService(payload),
        ensemble_engine=EnsembleEngine(
            EnsembleConfig(
                minimum_active_strategies=2,
                minimum_score=0.60,
                minimum_agreement=0.80,
            )
        ),
    )

    result = workflow.run("EURUSD")
    ensemble = result["ensemble"]

    assert ensemble["success"] is True
    assert ensemble["decision"] == "LONG"
    assert ensemble["metadata"]["raw_decision"] == "LONG"
    assert ensemble["metadata"]["thresholds_passed"] is True
    assert ensemble["ensemble_score"] == 1.0
    assert ensemble["agreement"] == 1.0
    assert ensemble["conflict"] == 0.0
    assert ensemble["strategies"]["active"] == 2
    assert ensemble["strategies"]["evaluated"] == 2
    assert ensemble["strategies"]["failed"] == 0
    assert ensemble["strategies"]["long"] == 2
    assert ensemble["strategies"]["short"] == 0


def test_workflow_produces_short_consensus_from_two_independent_strategies():
    payload = technical_analysis()
    payload["classification"]["trend"] = "BEARISH"
    payload["indicators"]["ema_fast"]["value"] = 1.1600
    payload["indicators"]["ema_slow"]["value"] = 1.1610
    payload["indicators"]["rsi"]["value"] = 75.0
    payload["indicators"]["macd"]["histogram"] = -0.0002
    payload["indicators"]["bollinger_bands"] = {
        "middle": 1.1610,
        "upper": 1.1620,
        "lower": 1.1590,
    }
    payload["metadata"]["latest_close"] = 1.1621

    workflow = LiveEnsembleWorkflow(
        market_service=FakeMarketService(payload),
        ensemble_engine=EnsembleEngine(
            EnsembleConfig(
                minimum_active_strategies=2,
                minimum_score=0.60,
                minimum_agreement=0.80,
            )
        ),
    )

    result = workflow.run("EURUSD")
    ensemble = result["ensemble"]

    assert ensemble["success"] is True
    assert ensemble["decision"] == "SHORT"
    assert ensemble["metadata"]["raw_decision"] == "SHORT"
    assert ensemble["metadata"]["thresholds_passed"] is True
    assert ensemble["ensemble_score"] == -1.0
    assert ensemble["agreement"] == 1.0
    assert ensemble["conflict"] == 0.0
    assert ensemble["strategies"]["active"] == 2
    assert ensemble["strategies"]["evaluated"] == 2
    assert ensemble["strategies"]["failed"] == 0
    assert ensemble["strategies"]["short"] == 2
    assert ensemble["strategies"]["long"] == 0


def test_workflow_isolates_one_failed_strategy_and_keeps_valid_evidence():
    registry = StrategyRegistry()
    registry.register(
        TrendMomentumStrategy(),
        StrategyConfig(strategy_id="trend_momentum", weight=1.0),
    )
    registry.register(
        FailingStrategy(),
        StrategyConfig(strategy_id="failing_strategy", weight=1.0),
    )

    factory = StrategyFactory()
    factory.register("trend_momentum", TrendMomentumStrategy)

    def fail_constructor(parameters):
        raise RuntimeError("intentional constructor failure")

    factory.register("failing_strategy", fail_constructor)

    workflow = LiveEnsembleWorkflow(
        market_service=FakeMarketService(technical_analysis()),
        registry=registry,
        factory=factory,
        ensemble_engine=EnsembleEngine(
            EnsembleConfig(
                minimum_active_strategies=1,
                minimum_score=0.60,
                minimum_agreement=0.80,
            )
        ),
    )

    result = workflow.run("EURUSD")
    ensemble = result["ensemble"]

    assert ensemble["success"] is True
    assert ensemble["strategies"]["active"] == 2
    assert ensemble["strategies"]["evaluated"] == 1
    assert ensemble["strategies"]["failed"] == 1
    assert ensemble["strategies"]["long"] == 1
    assert ensemble["decision"] == "LONG"
    assert ensemble["metadata"]["raw_decision"] == "LONG"
    assert ensemble["metadata"]["thresholds_passed"] is True
    assert len(ensemble["metadata"]["failures"]) == 1
    assert ensemble["metadata"]["failures"][0]["strategy_id"] == "failing_strategy"
