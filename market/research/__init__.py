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


from .statistics import (
    BootstrapResult,
    MultipleTestingResult,
    ResearchStatisticsError,
    SelectionAuditStatus,
    SelectionBiasAudit,
    StatisticalStatus,
    StatisticalValidationPolicy,
    StatisticalValidationResult,
    bootstrap_mean,
    multiple_testing,
    validate_statistics,
)

__all__ += [
    "BootstrapResult", "MultipleTestingResult", "ResearchStatisticsError",
    "SelectionAuditStatus", "SelectionBiasAudit", "StatisticalStatus",
    "StatisticalValidationPolicy", "StatisticalValidationResult",
    "bootstrap_mean", "multiple_testing", "validate_statistics",
]

from .cohort import (
    CohortCoverageCheck,
    CohortStatus,
    ResearchCohortEngine,
    ResearchCohortError,
    ResearchCohortPolicy,
    ResearchCohortResult,
    evaluate_cohort,
)

__all__ += [
    "CohortCoverageCheck", "CohortStatus", "ResearchCohortEngine",
    "ResearchCohortError", "ResearchCohortPolicy", "ResearchCohortResult",
    "evaluate_cohort",
]

from .portfolio import PairCorrelationObservation, PortfolioRobustnessCheck, PortfolioRobustnessError, PortfolioRobustnessPolicy, PortfolioRobustnessResult, PortfolioRobustnessStatus, ResearchPortfolioRobustnessEngine, assess_portfolio_robustness
__all__ += ["PairCorrelationObservation","PortfolioRobustnessCheck","PortfolioRobustnessError","PortfolioRobustnessPolicy","PortfolioRobustnessResult","PortfolioRobustnessStatus","ResearchPortfolioRobustnessEngine","assess_portfolio_robustness"]

from .final_evidence import (
    FinalEvidenceCheck,
    FinalEvidenceError,
    FinalEvidencePolicy,
    FinalEvidenceStatus,
    FinalResearchEvidence,
    FinalResearchEvidenceEngine,
    FinalResearchEvidenceResult,
    finalize_research_evidence,
)

__all__ += [
    "FinalEvidenceCheck",
    "FinalEvidenceError",
    "FinalEvidencePolicy",
    "FinalEvidenceStatus",
    "FinalResearchEvidence",
    "FinalResearchEvidenceEngine",
    "FinalResearchEvidenceResult",
    "finalize_research_evidence",
]

from .paper_readiness import (
    PaperReadinessEngine,
    PaperReadinessError,
    PaperReadinessInput,
    PaperReadinessPolicy,
    PaperReadinessResult,
    PaperReadinessCheck,
    PaperReadinessStatus,
    assess_paper_readiness,
)

__all__ += [
    "PaperReadinessEngine", "PaperReadinessError", "PaperReadinessInput",
    "PaperReadinessPolicy", "PaperReadinessResult", "PaperReadinessCheck",
    "PaperReadinessStatus", "assess_paper_readiness",
]
