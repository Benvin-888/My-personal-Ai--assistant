"""APEX / BENVIN Strategy Research, Robustness, Validation & Experiments."""

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
from .validation import (
    ResearchValidationEngine,
    ResearchValidationError,
    ResearchValidationPolicy,
    ResearchValidationResult,
    ValidationCheck,
    ValidationStatus,
    validate_research,
)
from .experiment import (
    CrossMarketResearchSummary,
    ExperimentStatus,
    ResearchDatasetSpec,
    ResearchExperimentEngine,
    ResearchExperimentError,
    ResearchExperimentResult,
    ResearchExperimentSpec,
    run_experiments,
    summarize_experiments,
)

__all__ = [
    "GroupStabilityResult", "MonteCarloResult", "OutOfSampleReport",
    "ParameterStabilityResult", "ResearchPerformance", "StrategyResearchEngine",
    "StrategyResearchError", "StrategyResearchReport", "WalkForwardWindow",
    "research_backtest", "ResearchValidationEngine", "ResearchValidationError",
    "ResearchValidationPolicy", "ResearchValidationResult", "ValidationCheck",
    "ValidationStatus", "validate_research", "CrossMarketResearchSummary",
    "ExperimentStatus", "ResearchDatasetSpec", "ResearchExperimentEngine",
    "ResearchExperimentError", "ResearchExperimentResult", "ResearchExperimentSpec",
    "run_experiments", "summarize_experiments",
]

from .robustness import (
    ResearchRobustnessEngine,
    ResearchRobustnessError,
    RobustnessScenarioResult,
    RobustnessScenarioSpec,
    RobustnessScenarioSummary,
    RobustnessStatus,
    TimeWalkForwardResult,
    TimeWalkForwardWindow,
    summarize_scenarios,
    time_walk_forward,
)

__all__ += [
    "ResearchRobustnessEngine", "ResearchRobustnessError", "RobustnessScenarioResult",
    "RobustnessScenarioSpec", "RobustnessScenarioSummary", "RobustnessStatus",
    "TimeWalkForwardResult", "TimeWalkForwardWindow", "summarize_scenarios",
    "time_walk_forward",
]
