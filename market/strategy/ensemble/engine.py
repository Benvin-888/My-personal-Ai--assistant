"""Deterministic multi-strategy ensemble coordinator for APEX."""

from __future__ import annotations

from ..engine import StrategyEngine
from ..factory import StrategyFactory
from ..models import EvaluationStatus, SignalDirection
from ..registry import StrategyRegistry
from .models import EnsembleConfig, EnsembleEvaluation, EnsembleStatus, StrategyContribution
from .scoring import score_contributions


class EnsembleEngine:
    """Evaluate compatible configured strategies and combine their evidence."""

    def __init__(self, config: EnsembleConfig | None = None) -> None:
        self.config = config or EnsembleConfig()

    def evaluate(
        self,
        analysis,
        registry: StrategyRegistry,
        factory: StrategyFactory,
    ) -> dict:
        if not isinstance(registry, StrategyRegistry):
            return self._error("registry must be a StrategyRegistry")
        if not isinstance(factory, StrategyFactory):
            return self._error("factory must be a StrategyFactory")
        if not isinstance(analysis, dict):
            return self._error("Technical analysis must be a dictionary")

        pair = str(analysis.get("pair", "UNKNOWN"))
        interval = str(analysis.get("interval", "UNKNOWN"))
        timestamp = analysis.get("latest_timestamp_utc")

        if not analysis.get("success", False):
            return self._build(
                pair,
                interval,
                timestamp,
                EnsembleStatus.INVALID_INPUT,
                error="Cannot evaluate unsuccessful technical analysis.",
            ).to_dict()

        compatible = registry.compatible_enabled(pair, interval)
        if not compatible:
            return self._build(
                pair,
                interval,
                timestamp,
                EnsembleStatus.NO_ACTIVE_STRATEGIES,
                error=f"No enabled strategies support {pair} on {interval}.",
            ).to_dict()

        contributions = []
        failed = 0
        failure_details = []
        strategy_engine = StrategyEngine()

        for strategy_id in compatible:
            config = registry.get_config(strategy_id)
            try:
                result = strategy_engine.evaluate_configured(
                    strategy_id,
                    analysis,
                    registry,
                    factory,
                )
            except Exception as exc:
                failed += 1
                failure_details.append({"strategy_id": strategy_id, "error": str(exc)})
                continue

            status_value = result.get("status")
            try:
                status = EvaluationStatus(status_value)
            except (TypeError, ValueError):
                status = EvaluationStatus.ERROR

            if status != EvaluationStatus.EVALUATED:
                failed += 1
                failure_details.append({
                    "strategy_id": strategy_id,
                    "status": status.value,
                    "error": result.get("error"),
                })
                continue

            strategy = result.get("strategy") or {}
            signal = result.get("signal") or {}
            try:
                direction = SignalDirection(signal["direction"])
                score = float(signal["score"])
                version = str(strategy["version"])
            except (KeyError, TypeError, ValueError) as exc:
                failed += 1
                failure_details.append({
                    "strategy_id": strategy_id,
                    "status": EvaluationStatus.ERROR.value,
                    "error": f"Invalid strategy evaluation payload: {exc}",
                })
                continue

            contributions.append(
                StrategyContribution(
                    strategy_id=strategy_id,
                    strategy_version=version,
                    direction=direction,
                    score=score,
                    weight=float(config.weight),
                    weighted_score=float(config.weight) * score,
                    status=status,
                    rationale=signal.get("rationale"),
                    metadata={
                        "strategy_conditions": result.get("conditions"),
                        "strategy_metadata": result.get("metadata"),
                    },
                )
            )

        contributions.sort(key=lambda item: item.strategy_id)
        active_count = len(compatible)
        evaluated_count = len(contributions)

        if evaluated_count == 0:
            return self._build(
                pair,
                interval,
                timestamp,
                EnsembleStatus.ERROR,
                active_count=active_count,
                failed_count=failed,
                error="No configured strategy produced a valid evaluation.",
                metadata={"failures": failure_details},
            ).to_dict()

        scores = score_contributions(contributions)
        decision = scores["decision"]
        ensemble_score = float(scores["ensemble_score"])
        agreement = float(scores["agreement"])
        conflict = float(scores["conflict"])
        confidence = float(scores["confidence"])

        passes_thresholds = (
            evaluated_count >= self.config.minimum_active_strategies
            and abs(ensemble_score) >= self.config.minimum_score
            and agreement >= self.config.minimum_agreement
            and decision != SignalDirection.NEUTRAL
        )
        final_decision = decision if passes_thresholds else SignalDirection.NEUTRAL

        long_count = sum(c.direction == SignalDirection.LONG for c in contributions)
        short_count = sum(c.direction == SignalDirection.SHORT for c in contributions)
        neutral_count = sum(c.direction == SignalDirection.NEUTRAL for c in contributions)

        metadata = {
            "scoring_policy": "weighted_directional_evidence",
            "threshold_policy": self.config.to_dict(),
            "raw_decision": decision.value,
            "thresholds_passed": passes_thresholds,
            "compatible_strategy_ids": list(compatible),
            "failures": failure_details,
        }

        return EnsembleEvaluation(
            pair=pair,
            interval=interval,
            timestamp_utc=timestamp,
            status=EnsembleStatus.EVALUATED,
            decision=final_decision,
            ensemble_score=ensemble_score,
            agreement=agreement,
            conflict=conflict,
            confidence=confidence,
            active_strategy_count=active_count,
            evaluated_strategy_count=evaluated_count,
            failed_strategy_count=failed,
            long_strategy_count=long_count,
            short_strategy_count=short_count,
            neutral_strategy_count=neutral_count,
            contributions=tuple(contributions),
            metadata=metadata,
        ).to_dict()

    def _build(
        self,
        pair,
        interval,
        timestamp,
        status,
        *,
        active_count=0,
        evaluated_count=0,
        failed_count=0,
        error=None,
        metadata=None,
    ):
        return EnsembleEvaluation(
            pair=pair,
            interval=interval,
            timestamp_utc=timestamp,
            status=status,
            decision=SignalDirection.NEUTRAL,
            ensemble_score=0.0,
            agreement=0.0,
            conflict=0.0,
            confidence=0.0,
            active_strategy_count=active_count,
            evaluated_strategy_count=evaluated_count,
            failed_strategy_count=failed_count,
            long_strategy_count=0,
            short_strategy_count=0,
            neutral_strategy_count=0,
            metadata=metadata or {},
            error=error,
        )

    def _error(self, message):
        return self._build(
            "UNKNOWN",
            "UNKNOWN",
            None,
            EnsembleStatus.INVALID_INPUT,
            error=message,
        ).to_dict()
