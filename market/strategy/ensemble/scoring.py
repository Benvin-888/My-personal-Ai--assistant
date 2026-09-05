"""Pure deterministic scoring functions for APEX strategy ensembles."""

from __future__ import annotations

from collections.abc import Iterable

from .models import StrategyContribution
from ..models import SignalDirection


class EnsembleScoringError(ValueError):
    """Raised when ensemble contributions cannot be scored safely."""


def score_contributions(
    contributions: Iterable[StrategyContribution],
) -> dict[str, float | SignalDirection]:
    """Calculate weighted evidence, agreement, conflict, and confidence.

    Neutral strategies contribute to active-strategy coverage but do not count
    as directional evidence. Failed strategies are represented separately by
    the ensemble engine and are therefore not scored here.
    """
    items = tuple(contributions)
    if not items:
        return {
            "decision": SignalDirection.NEUTRAL,
            "ensemble_score": 0.0,
            "agreement": 0.0,
            "conflict": 0.0,
            "confidence": 0.0,
        }

    total_weight = sum(item.weight for item in items)
    if total_weight <= 0:
        return {
            "decision": SignalDirection.NEUTRAL,
            "ensemble_score": 0.0,
            "agreement": 0.0,
            "conflict": 0.0,
            "confidence": 0.0,
        }

    long_support = sum(
        item.weight * max(item.score, 0.0)
        for item in items
        if item.direction == SignalDirection.LONG
    )
    short_support = sum(
        item.weight * max(-item.score, 0.0)
        for item in items
        if item.direction == SignalDirection.SHORT
    )

    directional_support = long_support + short_support
    directional_weight = sum(
        item.weight
        for item in items
        if item.direction != SignalDirection.NEUTRAL
    )

    if directional_support <= 0 or directional_weight <= 0:
        return {
            "decision": SignalDirection.NEUTRAL,
            "ensemble_score": 0.0,
            "agreement": 0.0,
            "conflict": 0.0,
            "confidence": 0.0,
        }

    ensemble_score = (long_support - short_support) / directional_weight
    agreement = max(long_support, short_support) / directional_support
    conflict = min(long_support, short_support) / directional_support
    directional_coverage = directional_weight / total_weight
    mean_strength = directional_support / directional_weight
    confidence = directional_coverage * mean_strength * agreement

    if long_support > short_support:
        decision = SignalDirection.LONG
    elif short_support > long_support:
        decision = SignalDirection.SHORT
    else:
        decision = SignalDirection.NEUTRAL

    return {
        "decision": decision,
        "ensemble_score": max(-1.0, min(1.0, ensemble_score)),
        "agreement": max(0.0, min(1.0, agreement)),
        "conflict": max(0.0, min(1.0, conflict)),
        "confidence": max(0.0, min(1.0, confidence)),
    }
