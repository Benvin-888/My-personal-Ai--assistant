from .version import __release__, __version__
"""APEX / BENVIN backtesting foundation."""

from .friction import ExecutionFill, ExecutionFrictionConfig, ExecutionFrictionError, ExecutionFrictionModel
from .models import BacktestConfig, BacktestDataset, BacktestFrame, BacktestRunMetadata, BacktestStatus, ReplayMode, ExecutionTiming
from .position import PositionAction, PositionEvent, PositionSide, PositionSimulationError, PositionSimulator, PositionState
from .replay import HistoricalReplayEngine, HistoricalReplayError
from .trade import TradeAccountState, TradeAction, TradeEvent, TradeRecord, TradeSimulationError, TradeSimulationResult, TradeSimulator
from .metrics import BacktestMetricsCalculator, BacktestMetricsError, BacktestPerformanceMetrics, calculate_performance
from .reporting import BacktestReport, BacktestReportBuilder, BacktestReportingError, EquityPoint, build_report
from .orchestration import BacktestOrchestrationError, BacktestOrchestrator, SignalProvider, run_backtest

__all__ = [
    '__version__','__release__','ExecutionFill','ExecutionFrictionConfig','ExecutionFrictionError','ExecutionFrictionModel',
    'BacktestConfig','BacktestDataset','BacktestFrame','BacktestRunMetadata','BacktestStatus','ReplayMode','ExecutionTiming',
    'PositionAction','PositionEvent','PositionSide','PositionSimulationError','PositionSimulator','PositionState',
    'HistoricalReplayEngine','HistoricalReplayError','TradeAccountState','TradeAction','TradeEvent','TradeRecord',
    'TradeSimulationError','TradeSimulationResult','TradeSimulator','BacktestMetricsCalculator','BacktestMetricsError',
    'BacktestPerformanceMetrics','calculate_performance','BacktestReport','BacktestReportBuilder','BacktestReportingError',
    'EquityPoint','build_report','BacktestOrchestrationError','BacktestOrchestrator','SignalProvider','run_backtest',
    'BacktestIntegrityValidator','BacktestValidationCheck','BacktestValidationError','BacktestValidationResult','BacktestValidationStatus','validate_backtest',
]
from .validation import BacktestIntegrityValidator, BacktestValidationCheck, BacktestValidationError, BacktestValidationResult, BacktestValidationStatus, validate_backtest
