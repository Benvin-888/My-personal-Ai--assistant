"""APEX live technical-analysis to strategy-ensemble workflow.

This module is an orchestration boundary for end-to-end verification.
It retrieves validated historical Forex data, calculates deterministic
technical analysis, and evaluates the configured strategy ensemble.

It does NOT:
    - place orders
    - connect to a broker
    - calculate position sizes
    - modify trading accounts
    - execute trades
"""

from __future__ import annotations

from typing import Any, Mapping

from ..service import MarketDataService
from .config import StrategyConfig
from .ensemble import EnsembleConfig, EnsembleEngine
from .factory import StrategyFactory
from .registry import StrategyRegistry
from .strategies import MeanReversionStrategy, TrendMomentumStrategy


class LiveEnsembleWorkflowError(ValueError):
    """Raised when live ensemble workflow configuration is invalid."""


def build_default_strategy_factory() -> StrategyFactory:
    """Build the default Phase 2.4 strategy factory."""

    factory = StrategyFactory()
    factory.register("trend_momentum", TrendMomentumStrategy)
    factory.register("mean_reversion", MeanReversionStrategy)
    return factory


def build_default_strategy_registry() -> StrategyRegistry:
    """Build the default enabled strategy registry."""

    registry = StrategyRegistry()
    registry.register(
        TrendMomentumStrategy(),
        StrategyConfig(strategy_id="trend_momentum", weight=1.0),
    )
    registry.register(
        MeanReversionStrategy(),
        StrategyConfig(
            strategy_id="mean_reversion",
            weight=1.0,
        ),
    )
    return registry


class LiveEnsembleWorkflow:
    """Run the complete data -> analysis -> ensemble pipeline."""

    def __init__(
        self,
        *,
        market_service: MarketDataService | None = None,
        registry: StrategyRegistry | None = None,
        factory: StrategyFactory | None = None,
        ensemble_engine: EnsembleEngine | None = None,
    ) -> None:
        self.market_service = market_service or MarketDataService()
        self.registry = registry or build_default_strategy_registry()
        self.factory = factory or build_default_strategy_factory()
        self.ensemble_engine = ensemble_engine or EnsembleEngine(
            EnsembleConfig()
        )

    def run(
        self,
        pair: str,
        *,
        data_range: str = "1d",
        interval: str = "5m",
        limit: int = 100,
        indicator_options: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve, analyze, and ensemble-evaluate one market snapshot."""

        if not isinstance(pair, str) or not pair.strip():
            raise LiveEnsembleWorkflowError("pair must be a non-empty string")
        if not isinstance(data_range, str) or not data_range.strip():
            raise LiveEnsembleWorkflowError(
                "data_range must be a non-empty string"
            )
        if not isinstance(interval, str) or not interval.strip():
            raise LiveEnsembleWorkflowError("interval must be a non-empty string")
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
        ):
            raise LiveEnsembleWorkflowError("limit must be a positive integer")
        if indicator_options is not None and not isinstance(
            indicator_options, Mapping
        ):
            raise LiveEnsembleWorkflowError(
                "indicator_options must be a mapping"
            )

        analysis = self.market_service.analyze_forex_history(
            pair,
            data_range=data_range,
            interval=interval,
            limit=limit,
            **dict(indicator_options or {}),
        )

        if not isinstance(analysis, dict):
            return {
                "success": False,
                "market": "forex",
                "workflow": "technical_analysis_strategy_ensemble",
                "pair": pair,
                "interval": interval,
                "error": "Technical analysis returned an invalid payload.",
            }

        if not analysis.get("success", False):
            return {
                "success": False,
                "market": "forex",
                "workflow": "technical_analysis_strategy_ensemble",
                "pair": analysis.get("pair", pair),
                "interval": analysis.get("interval", interval),
                "technical_analysis": analysis,
                "ensemble": None,
                "error": "Technical analysis failed; ensemble evaluation skipped.",
            }

        ensemble = self.ensemble_engine.evaluate(
            analysis,
            self.registry,
            self.factory,
        )

        return {
            "success": bool(ensemble.get("success", False)),
            "market": "forex",
            "workflow": "technical_analysis_strategy_ensemble",
            "pair": analysis.get("pair", pair),
            "interval": analysis.get("interval", interval),
            "technical_analysis": analysis,
            "ensemble": ensemble,
        }


def run_live_ensemble(
    pair: str = "EURUSD",
    *,
    data_range: str = "1d",
    interval: str = "5m",
    limit: int = 100,
) -> dict[str, Any]:
    """Convenience API for a real provider-backed ensemble evaluation."""

    return LiveEnsembleWorkflow().run(
        pair,
        data_range=data_range,
        interval=interval,
        limit=limit,
    )


def _print_result(result: dict[str, Any]) -> None:
    """Print a compact human-readable live verification result."""

    print("=" * 72)
    print("APEX LIVE TECHNICAL ANALYSIS -> STRATEGY ENSEMBLE TEST")
    print("=" * 72)
    print(f"SUCCESS: {result.get('success')}")
    print(f"PAIR: {result.get('pair')}")
    print(f"INTERVAL: {result.get('interval')}")

    analysis = result.get("technical_analysis") or {}
    print(f"ANALYSIS SUCCESS: {analysis.get('success')}")
    print(f"TREND: {(analysis.get('classification') or {}).get('trend')}")
    print(f"MOMENTUM: {(analysis.get('classification') or {}).get('momentum')}")
    print(f"VOLATILITY: {(analysis.get('classification') or {}).get('volatility')}")

    ensemble = result.get("ensemble") or {}
    print(f"ENSEMBLE STATUS: {ensemble.get('status')}")
    print(f"DECISION: {ensemble.get('decision')}")
    print(f"ENSEMBLE SCORE: {ensemble.get('ensemble_score')}")
    print(f"AGREEMENT: {ensemble.get('agreement')}")
    print(f"CONFLICT: {ensemble.get('conflict')}")
    print(f"CONFIDENCE: {ensemble.get('confidence')}")
    ensemble_metadata = ensemble.get("metadata")
    if not isinstance(ensemble_metadata, Mapping):
        ensemble_metadata = {}

    print(f"RAW DECISION: {ensemble_metadata.get('raw_decision')}")
    print(f"THRESHOLDS PASSED: {ensemble_metadata.get('thresholds_passed')}")

    threshold_policy = ensemble_metadata.get("threshold_policy")
    if isinstance(threshold_policy, Mapping):
        print(
            "THRESHOLDS: "
            f"score>={threshold_policy.get('minimum_score')} "
            f"agreement>={threshold_policy.get('minimum_agreement')} "
            f"strategies>={threshold_policy.get('minimum_active_strategies')}"
        )
    strategies = ensemble.get("strategies")
    if not isinstance(strategies, Mapping):
        strategies = {}

    active_strategy_count = ensemble.get("active_strategy_count")
    if active_strategy_count is None:
        active_strategy_count = strategies.get("active")

    evaluated_strategy_count = ensemble.get("evaluated_strategy_count")
    if evaluated_strategy_count is None:
        evaluated_strategy_count = strategies.get("evaluated")

    failed_strategy_count = ensemble.get("failed_strategy_count")
    if failed_strategy_count is None:
        failed_strategy_count = strategies.get("failed")

    print(f"ACTIVE STRATEGIES: {active_strategy_count}")
    print(f"EVALUATED STRATEGIES: {evaluated_strategy_count}")
    print(f"FAILED STRATEGIES: {failed_strategy_count}")
    print("CONTRIBUTIONS:")

    for contribution in ensemble.get("contributions", []):
        print(
            "  - "
            f"{contribution.get('strategy_id')} "
            f"v{contribution.get('strategy_version')}: "
            f"{contribution.get('direction')} "
            f"score={contribution.get('score')} "
            f"weight={contribution.get('weight')}"
        )

    print("=" * 72)


if __name__ == "__main__":
    _print_result(run_live_ensemble())
