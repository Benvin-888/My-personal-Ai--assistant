"""APEX / BENVIN Phase 2.9 Strategy Research & Robustness."""

from .engine import (
    GroupStabilityResult,
    MonteCarloResult,
    OutOfSampleReport,
    ParameterStabilityResult,
    ResearchPerformance,
    StrategyResearchEngine,
    StrategyResearchError,
    StrategyResearchReport,
    WalkForwardWindow,
    research_backtest,
)

__all__ = [
    "GroupStabilityResult",
    "MonteCarloResult",
    "OutOfSampleReport",
    "ParameterStabilityResult",
    "ResearchPerformance",
    "StrategyResearchEngine",
    "StrategyResearchError",
    "StrategyResearchReport",
    "WalkForwardWindow",
    "research_backtest",
]
