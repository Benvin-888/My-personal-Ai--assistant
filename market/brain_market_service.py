"""Read-only Brain -> Market query orchestration.

Phase 2.42

This module is the first executable read-only path from BENVIN orchestration
into the deterministic Market stack. It retrieves market history, computes
technical analysis, regime, session and operational state, then passes those
observations through the Phase 2.41 Brain/Market interface.

It does NOT:
    - create an ExecutionRequest
    - authorize a trade
    - read broker credentials
    - place, modify, cancel, or sell a broker contract
    - call the live execution boundary

The returned opportunity is analytical evidence only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .analysis import TechnicalAnalysisEngine
from .brain_interface import (
    BrainMarketInterface,
    BrainMarketResult,
    MarketIntelligenceRequest,
)
from .data_quality import assess_candles
from .regime import MarketRegimeEngine
from .reliability import FreshnessPolicy
from .session import ForexSessionEngine
from .strategy import StrategyConfig, StrategyFactory, StrategyRegistry
from .strategy.strategies import MeanReversionStrategy, TrendMomentumStrategy
from .unified import UnifiedMarketDataService


class BrainMarketQueryError(ValueError):
    """Raised when a read-only Brain -> Market query is invalid."""


@dataclass(frozen=True)
class BrainMarketQuery:
    """Validated read-only request for a point-in-time market analysis."""

    request_id: str
    pair: str
    interval: str = "5m"
    data_range: str = "1d"
    provider: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise BrainMarketQueryError("request_id must be a non-empty string")
        if not isinstance(self.pair, str) or not self.pair.strip():
            raise BrainMarketQueryError("pair must be a non-empty string")
        normalized = self.pair.replace("/", "").replace("-", "").replace(" ", "").upper()
        if len(normalized) != 6 or not normalized.isalpha():
            raise BrainMarketQueryError("pair must be a six-letter Forex pair")
        if not isinstance(self.interval, str) or not self.interval.strip():
            raise BrainMarketQueryError("interval must be a non-empty string")
        if not isinstance(self.data_range, str) or not self.data_range.strip():
            raise BrainMarketQueryError("data_range must be a non-empty string")
        if self.provider is not None and (
            not isinstance(self.provider, str) or not self.provider.strip()
        ):
            raise BrainMarketQueryError("provider must be a non-empty string or None")

    @property
    def normalized_pair(self) -> str:
        return self.pair.replace("/", "").replace("-", "").replace(" ", "").upper()


@dataclass(frozen=True)
class BrainMarketQueryResult:
    """Compact read-only result exposed to Brain/main orchestration."""

    query: BrainMarketQuery
    market: BrainMarketResult | None
    success: bool
    provider: str | None
    history_metadata: Mapping[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "success": self.success,
            "request_id": self.query.request_id,
            "pair": self.query.normalized_pair,
            "interval": self.query.interval,
            "provider": self.provider,
            "history_metadata": dict(self.history_metadata),
            "execution_authorized": False,
            "read_only": True,
        }
        if self.market is not None:
            payload["market_intelligence"] = self.market.to_dict()
        if self.error:
            payload["error"] = self.error
        return payload


class BrainMarketQueryService:
    """Orchestrate one deterministic, read-only market query."""

    def __init__(
        self,
        *,
        market_data: UnifiedMarketDataService | None = None,
        technical: TechnicalAnalysisEngine | None = None,
        regime: MarketRegimeEngine | None = None,
        sessions: ForexSessionEngine | None = None,
        interface: BrainMarketInterface | None = None,
        registry: StrategyRegistry | None = None,
        factory: StrategyFactory | None = None,
    ) -> None:
        self.market_data = market_data or UnifiedMarketDataService.with_defaults()
        self.technical = technical or TechnicalAnalysisEngine()
        self.regime = regime or MarketRegimeEngine()
        self.sessions = sessions or ForexSessionEngine()
        self.interface = interface or BrainMarketInterface()
        self.registry, self.factory = self._build_strategies(registry, factory)

    @staticmethod
    def _build_strategies(
        registry: StrategyRegistry | None,
        factory: StrategyFactory | None,
    ) -> tuple[StrategyRegistry, StrategyFactory]:
        if registry is not None and factory is not None:
            return registry, factory
        if registry is not None or factory is not None:
            raise BrainMarketQueryError("registry and factory must be supplied together")

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

    def evaluate(self, query: BrainMarketQuery) -> BrainMarketQueryResult:
        if not isinstance(query, BrainMarketQuery):
            raise BrainMarketQueryError("query must be a BrainMarketQuery")

        history = self.market_data.get_forex_history(
            query.normalized_pair,
            provider=query.provider,
            data_range=query.data_range,
            interval=query.interval,
        )

        if not isinstance(history, Mapping) or history.get("success") is not True:
            error = (
                history.get("error", "market history retrieval failed")
                if isinstance(history, Mapping)
                else "market history retrieval returned an invalid result"
            )
            return BrainMarketQueryResult(
                query=query,
                market=None,
                success=False,
                provider=history.get("provider") if isinstance(history, Mapping) else None,
                history_metadata={"success": False},
                error=str(error),
            )

        provider = str(history.get("provider") or query.provider or "UNKNOWN")
        quality = assess_candles(history).to_dict()

        candles = history.get("candles")
        if not isinstance(candles, list) or not candles:
            return BrainMarketQueryResult(
                query=query,
                market=None,
                success=False,
                provider=provider,
                history_metadata={"success": False, "data_quality": quality},
                error="market history contains no candles",
            )

        analysis = self.technical.analyze_history(history)
        if not isinstance(analysis, Mapping) or analysis.get("success") is not True:
            return BrainMarketQueryResult(
                query=query,
                market=None,
                success=False,
                provider=provider,
                history_metadata={"success": True, "data_quality": quality},
                error=(analysis.get("error", "technical analysis failed") if isinstance(analysis, Mapping) else "technical analysis returned an invalid result"),
            )

        timestamp = analysis.get("latest_timestamp_utc")
        if not isinstance(timestamp, str) or not timestamp.strip():
            return BrainMarketQueryResult(
                query=query,
                market=None,
                success=False,
                provider=provider,
                history_metadata={"success": True, "data_quality": quality},
                error="technical analysis did not provide a point-in-time timestamp",
            )

        assessed_at = datetime.now(timezone.utc)
        freshness = self.market_data.assess_observation_freshness(
            {"provider": provider, "timestamp_utc": timestamp},
            assessed_at=assessed_at,
        )
        reliability = self.market_data.reliability_snapshot(provider)
        operational_state = self.market_data.assess_operational_state(
            provider=provider,
            pair=query.normalized_pair,
            assessed_at=assessed_at,
            freshness=freshness,
            data_quality={
                "quality": quality.get("quality", "INVALID"),
                "score": quality.get("score", 0.0),
            },
            provider_health=None,
            reliability=reliability,
        )

        regime = self.regime.assess(
            analysis,
            operational_state=operational_state,
        ).to_dict()
        session_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        session = self.sessions.assess(session_timestamp).to_dict()
        session["timestamp_utc"] = timestamp

        request = MarketIntelligenceRequest(
            analysis=analysis,
            regime=regime,
            session=session,
            operational_state=operational_state,
            request_id=query.request_id,
        )
        market_result = self.interface.evaluate(
            request,
            registry=self.registry,
            factory=self.factory,
        )

        metadata = {
            "success": True,
            "provider": provider,
            "range": history.get("range"),
            "retrieved_at": history.get("retrieved_at"),
            "candle_count": len(candles),
            "data_quality": quality,
            "freshness": freshness.get("freshness", {}),
        }
        return BrainMarketQueryResult(
            query=query,
            market=market_result,
            success=True,
            provider=provider,
            history_metadata=metadata,
        )


__all__ = [
    "BrainMarketQuery",
    "BrainMarketQueryError",
    "BrainMarketQueryResult",
    "BrainMarketQueryService",
]
