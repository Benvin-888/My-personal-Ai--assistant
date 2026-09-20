from __future__ import annotations

import pytest

from market.brain_interface import (
    BrainMarketInterface,
    BrainMarketInterfaceError,
    MarketIntelligenceRequest,
)
from market.strategy import StrategyConfig, StrategyFactory, StrategyRegistry
from market.strategy.strategies import MeanReversionStrategy, TrendMomentumStrategy

T = "2026-09-19T10:00:00Z"


def analysis():
    return {
        "success": True,
        "pair": "EURUSD",
        "interval": "5m",
        "latest_timestamp_utc": T,
        "candle_count": 100,
        "indicators": {
            "ema_fast": {"value": 1.161},
            "ema_slow": {"value": 1.160},
            "rsi": {"value": 62.0},
            "macd": {"histogram": 0.0002},
            "bollinger_bands": {"lower": 1.158, "middle": 1.160, "upper": 1.162},
        },
        "classification": {"trend": "BULLISH", "volatility": "LOW"},
        "metadata": {"latest_close": 1.161},
    }


def registry_factory():
    registry = StrategyRegistry()
    registry.register(
        TrendMomentumStrategy(),
        StrategyConfig(strategy_id="trend_momentum", weight=1.0),
    )
    registry.register(
        MeanReversionStrategy(),
        StrategyConfig(strategy_id="mean_reversion", weight=1.0),
    )
    factory = StrategyFactory()
    factory.register("trend_momentum", TrendMomentumStrategy)
    factory.register("mean_reversion", MeanReversionStrategy)
    return registry, factory


def request():
    return MarketIntelligenceRequest(
        analysis=analysis(),
        regime={
            "success": True,
            "analysis": "market_regime",
            "status": "EVALUATED",
            "pair": "EURUSD",
            "interval": "5m",
            "timestamp_utc": T,
            "regime": "BULLISH_TREND",
            "analysis_usable": True,
        },
        session={
            "success": True,
            "analysis": "forex_session",
            "status": "EVALUATED",
            "timestamp_utc": T,
            "phase": "SINGLE_SESSION",
            "active_sessions": ["LONDON"],
        },
        operational_state={
            "success": True,
            "analysis": "market_operational_state",
            "status": "HEALTHY",
            "pair": "EURUSD",
            "interval": "5m",
            "timestamp_utc": T,
            "analysis_usable": True,
        },
        request_id="brain-241-001",
    )


def test_read_only_bridge_returns_market_snapshot():
    registry, factory = registry_factory()
    result = BrainMarketInterface().evaluate(request(), registry=registry, factory=factory)
    assert result.request_id == "brain-241-001"
    assert result.to_dict()["interface"] == "brain_market_read_only"
    assert result.to_dict()["execution_authorized"] is False


def test_bridge_preserves_market_evidence_fingerprint():
    registry, factory = registry_factory()
    result = BrainMarketInterface().evaluate(request(), registry=registry, factory=factory)
    assert result.snapshot.evidence_fingerprint
    assert result.snapshot.to_dict()["evidence_fingerprint"] == result.snapshot.evidence_fingerprint


def test_request_rejects_empty_request_id():
    with pytest.raises(BrainMarketInterfaceError):
        MarketIntelligenceRequest(analysis=analysis(), regime=None, session=None, operational_state=None, request_id=" ")


def test_request_rejects_non_mapping_analysis():
    with pytest.raises(BrainMarketInterfaceError):
        MarketIntelligenceRequest(analysis=[], regime=None, session=None, operational_state=None, request_id="x")


def test_bridge_rejects_wrong_request_type():
    registry, factory = registry_factory()
    with pytest.raises(BrainMarketInterfaceError):
        BrainMarketInterface().evaluate({}, registry=registry, factory=factory)


def test_bridge_cannot_authorize_execution():
    registry, factory = registry_factory()
    result = BrainMarketInterface().evaluate(request(), registry=registry, factory=factory)
    assert result.execution_authorized is False
    assert result.snapshot.execution_authorized is False
    assert "execution" not in {name for name in dir(BrainMarketInterface) if not name.startswith("_")}
