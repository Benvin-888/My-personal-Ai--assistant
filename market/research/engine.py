"""APEX / BENVIN Strategy Research & Robustness Engine.

Phase 2.9 - Strategy Research & Robustness

This module measures whether a completed risk-aware backtest is stable enough
for further research. It deliberately does not optimize parameters, place
orders, access brokers, or make profitability guarantees.

Design goals:
    * chronological in-sample / out-of-sample separation;
    * deterministic walk-forward summaries from supplied backtest runs;
    * parameter stability measurement without parameter selection;
    * regime/session stability measurement when trade metadata contains labels;
    * seeded Monte Carlo bootstrap of trade risk multiples;
    * auditable, immutable outputs suitable for later research reporting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from statistics import mean, pstdev
from typing import Any, Mapping, Sequence

from market.backtest.risk_aware import RiskAwareBacktestResult, RiskAwareTrade


class StrategyResearchError(ValueError):
    """Raised when research inputs are invalid."""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise StrategyResearchError(f"{name} must be finite numeric")
    return float(value)


def _pct(value: float, base: float) -> float:
    return value / base * 100.0 if base else 0.0


@dataclass(frozen=True)
class ResearchPerformance:
    """Comparable performance summary derived from one backtest result."""

    initial_capital: float
    final_equity: float
    net_pnl: float
    total_return_pct: float
    trade_count: int
    win_rate_pct: float
    profit_factor: float | None
    expectancy: float
    average_risk_multiple: float
    max_drawdown: float
    max_drawdown_pct: float
    total_transaction_costs: float
    recovery_factor: float | None
    calmar_like_ratio: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_capital": self.initial_capital,
            "final_equity": self.final_equity,
            "net_pnl": self.net_pnl,
            "total_return_pct": self.total_return_pct,
            "trade_count": self.trade_count,
            "win_rate_pct": self.win_rate_pct,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "average_risk_multiple": self.average_risk_multiple,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "total_transaction_costs": self.total_transaction_costs,
            "recovery_factor": self.recovery_factor,
            "calmar_like_ratio": self.calmar_like_ratio,
        }


@dataclass(frozen=True)
class OutOfSampleReport:
    """Chronological train/test performance split."""

    in_sample: ResearchPerformance
    out_of_sample: ResearchPerformance
    split_trade_index: int
    generalization_ratio_pct: float
    out_of_sample_positive: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "in_sample": self.in_sample.to_dict(),
            "out_of_sample": self.out_of_sample.to_dict(),
            "split_trade_index": self.split_trade_index,
            "generalization_ratio_pct": self.generalization_ratio_pct,
            "out_of_sample_positive": self.out_of_sample_positive,
        }


@dataclass(frozen=True)
class WalkForwardWindow:
    """One chronological walk-forward evaluation window."""

    window_id: int
    train_start_trade: int
    train_end_trade: int
    test_start_trade: int
    test_end_trade: int
    train: ResearchPerformance
    test: ResearchPerformance

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "train_start_trade": self.train_start_trade,
            "train_end_trade": self.train_end_trade,
            "test_start_trade": self.test_start_trade,
            "test_end_trade": self.test_end_trade,
            "train": self.train.to_dict(),
            "test": self.test.to_dict(),
        }


@dataclass(frozen=True)
class ParameterStabilityResult:
    """Distribution of performance across supplied parameter configurations."""

    run_count: int
    returns_mean_pct: float
    returns_std_pct: float
    returns_min_pct: float
    returns_max_pct: float
    profit_factor_mean: float | None
    max_drawdown_pct_mean: float
    profitable_run_count: int
    profitable_run_fraction: float
    return_stability_score: float
    runs: tuple[tuple[str, ResearchPerformance], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_count": self.run_count,
            "returns_mean_pct": self.returns_mean_pct,
            "returns_std_pct": self.returns_std_pct,
            "returns_min_pct": self.returns_min_pct,
            "returns_max_pct": self.returns_max_pct,
            "profit_factor_mean": self.profit_factor_mean,
            "max_drawdown_pct_mean": self.max_drawdown_pct_mean,
            "profitable_run_count": self.profitable_run_count,
            "profitable_run_fraction": self.profitable_run_fraction,
            "return_stability_score": self.return_stability_score,
            "runs": [{"configuration": key, "performance": value.to_dict()} for key, value in self.runs],
        }


@dataclass(frozen=True)
class GroupStabilityResult:
    """Performance comparison for regime/session/strategy groups."""

    group_field: str
    groups: tuple[tuple[str, ResearchPerformance], ...]
    profitable_group_fraction: float
    return_dispersion_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_field": self.group_field,
            "groups": [{"group": key, "performance": value.to_dict()} for key, value in self.groups],
            "profitable_group_fraction": self.profitable_group_fraction,
            "return_dispersion_pct": self.return_dispersion_pct,
        }


@dataclass(frozen=True)
class MonteCarloResult:
    """Seeded bootstrap distribution over historical trade risk multiples."""

    seed: int
    simulations: int
    trades_per_simulation: int
    starting_capital: float
    terminal_equity_mean: float
    terminal_equity_median: float
    terminal_equity_p05: float
    terminal_equity_p95: float
    drawdown_p95: float
    positive_terminal_fraction: float
    ruin_fraction: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "simulations": self.simulations,
            "trades_per_simulation": self.trades_per_simulation,
            "starting_capital": self.starting_capital,
            "terminal_equity_mean": self.terminal_equity_mean,
            "terminal_equity_median": self.terminal_equity_median,
            "terminal_equity_p05": self.terminal_equity_p05,
            "terminal_equity_p95": self.terminal_equity_p95,
            "drawdown_p95": self.drawdown_p95,
            "positive_terminal_fraction": self.positive_terminal_fraction,
            "ruin_fraction": self.ruin_fraction,
        }


@dataclass(frozen=True)
class StrategyResearchReport:
    """Complete Phase 2.9 research output."""

    baseline: ResearchPerformance
    out_of_sample: OutOfSampleReport | None = None
    walk_forward: tuple[WalkForwardWindow, ...] = ()
    parameter_stability: ParameterStabilityResult | None = None
    regime_stability: GroupStabilityResult | None = None
    session_stability: GroupStabilityResult | None = None
    monte_carlo: MonteCarloResult | None = None
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis": "strategy_research_robustness",
            "baseline": self.baseline.to_dict(),
            "out_of_sample": self.out_of_sample.to_dict() if self.out_of_sample else None,
            "walk_forward": [item.to_dict() for item in self.walk_forward],
            "parameter_stability": self.parameter_stability.to_dict() if self.parameter_stability else None,
            "regime_stability": self.regime_stability.to_dict() if self.regime_stability else None,
            "session_stability": self.session_stability.to_dict() if self.session_stability else None,
            "monte_carlo": self.monte_carlo.to_dict() if self.monte_carlo else None,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


class StrategyResearchEngine:
    """Measure robustness without optimizing or selecting a strategy."""

    @staticmethod
    def performance(result: RiskAwareBacktestResult) -> ResearchPerformance:
        if not isinstance(result, RiskAwareBacktestResult):
            raise StrategyResearchError("result must be a RiskAwareBacktestResult")
        trades = tuple(result.trades)
        returns = [trade.realized_pnl for trade in trades]
        wins = [value for value in returns if value > 0]
        losses = [-value for value in returns if value < 0]
        gross_profit = sum(wins)
        gross_loss = sum(losses)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else None)
        average_r = mean(trade.risk_multiple for trade in trades) if trades else 0.0
        recovery = result.net_pnl / result.max_drawdown if result.max_drawdown > 0 else None
        calmar = (result.total_return_pct / result.max_drawdown_pct) if result.max_drawdown_pct > 0 else None
        return ResearchPerformance(
            initial_capital=float(result.initial_capital),
            final_equity=float(result.final_equity),
            net_pnl=float(result.net_pnl),
            total_return_pct=float(result.total_return_pct),
            trade_count=len(trades),
            win_rate_pct=(len(wins) / len(trades) * 100.0) if trades else 0.0,
            profit_factor=profit_factor,
            expectancy=(mean(returns) if returns else 0.0),
            average_risk_multiple=average_r,
            max_drawdown=float(result.max_drawdown),
            max_drawdown_pct=float(result.max_drawdown_pct),
            total_transaction_costs=float(result.total_transaction_costs),
            recovery_factor=recovery,
            calmar_like_ratio=calmar,
        )

    @staticmethod
    def _subset_result(result: RiskAwareBacktestResult, trades: Sequence[RiskAwareTrade], initial_capital: float | None = None) -> RiskAwareBacktestResult:
        """Build a lightweight result view for a trade subset.

        Equity is reconstructed from the subset's realized P&L. Drawdown is
        recomputed from the sequential subset equity curve. This is intended
        for research comparison, not replacement of the authoritative replay.
        """
        if not trades:
            capital = float(result.initial_capital if initial_capital is None else initial_capital)
            return RiskAwareBacktestResult(
                pair=result.pair, interval=result.interval, initial_capital=capital,
                final_equity=capital, net_pnl=0.0, total_return_pct=0.0,
                peak_equity=capital, max_drawdown=0.0, max_drawdown_pct=0.0,
                trades=(), events=(), rejected_opportunities=0, risk_rejections=0,
                candidate_opportunities=0, stop_losses=0, take_profits=0,
                end_of_test_closures=0, winning_trades=0, losing_trades=0,
                breakeven_trades=0, gross_profit=0.0, gross_loss=0.0,
                profit_factor=None, average_win=0.0, average_loss=0.0,
                average_risk_multiple=0.0, total_transaction_costs=0.0,
                risk_budget_breaches=0, config=dict(result.config), metadata=dict(result.metadata),
            )
        capital = float(result.initial_capital if initial_capital is None else initial_capital)
        equity = capital
        peak = capital
        max_dd = 0.0
        for trade in trades:
            equity += float(trade.realized_pnl)
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        winners = sum(1 for trade in trades if trade.realized_pnl > 0)
        losers = sum(1 for trade in trades if trade.realized_pnl < 0)
        gross_profit = sum(max(0.0, trade.realized_pnl) for trade in trades)
        gross_loss = -sum(min(0.0, trade.realized_pnl) for trade in trades)
        return RiskAwareBacktestResult(
            pair=result.pair, interval=result.interval, initial_capital=capital,
            final_equity=equity, net_pnl=equity - capital,
            total_return_pct=_pct(equity - capital, capital), peak_equity=peak,
            max_drawdown=max_dd, max_drawdown_pct=_pct(max_dd, peak),
            trades=tuple(trades), events=(), rejected_opportunities=0,
            risk_rejections=0, candidate_opportunities=len(trades),
            stop_losses=sum(1 for trade in trades if trade.status.value == "STOP_LOSS"),
            take_profits=sum(1 for trade in trades if trade.status.value == "TAKE_PROFIT"),
            end_of_test_closures=sum(1 for trade in trades if trade.status.value == "END_OF_TEST"),
            winning_trades=winners, losing_trades=losers,
            breakeven_trades=len(trades) - winners - losers,
            gross_profit=gross_profit, gross_loss=gross_loss,
            profit_factor=(gross_profit / gross_loss if gross_loss else None),
            average_win=(gross_profit / winners if winners else 0.0),
            average_loss=(-gross_loss / losers if losers else 0.0),
            average_risk_multiple=(mean(trade.risk_multiple for trade in trades) if trades else 0.0),
            total_transaction_costs=sum(trade.transaction_costs for trade in trades),
            risk_budget_breaches=sum(1 for trade in trades if trade.risk_budget_breached),
            config=dict(result.config), metadata=dict(result.metadata),
        )

    def out_of_sample(self, result: RiskAwareBacktestResult, train_fraction: float = 0.70) -> OutOfSampleReport:
        if not isinstance(train_fraction, (int, float)) or isinstance(train_fraction, bool) or not 0.0 < float(train_fraction) < 1.0:
            raise StrategyResearchError("train_fraction must be between 0 and 1")
        trades = tuple(result.trades)
        if len(trades) < 2:
            raise StrategyResearchError("at least two trades are required for an out-of-sample split")
        split = min(max(int(len(trades) * float(train_fraction)), 1), len(trades) - 1)
        train_result = self._subset_result(result, trades[:split])
        test_result = self._subset_result(result, trades[split:], initial_capital=train_result.final_equity)
        train = self.performance(train_result)
        test = self.performance(test_result)
        ratio = (test.total_return_pct / train.total_return_pct * 100.0) if train.total_return_pct > 0 else 0.0
        return OutOfSampleReport(train, test, split, ratio, test.net_pnl > 0)

    def walk_forward(self, result: RiskAwareBacktestResult, train_trades: int = 20, test_trades: int = 10, step_trades: int | None = None) -> tuple[WalkForwardWindow, ...]:
        trades = tuple(result.trades)
        if train_trades < 1 or test_trades < 1:
            raise StrategyResearchError("train_trades and test_trades must be positive")
        step = test_trades if step_trades is None else step_trades
        if step < 1:
            raise StrategyResearchError("step_trades must be positive")
        windows: list[WalkForwardWindow] = []
        start = 0
        window_id = 1
        while start + train_trades + test_trades <= len(trades):
            train_slice = trades[start : start + train_trades]
            test_slice = trades[start + train_trades : start + train_trades + test_trades]
            train_result = self._subset_result(result, train_slice)
            test_result = self._subset_result(result, test_slice, initial_capital=train_result.final_equity)
            windows.append(WalkForwardWindow(
                window_id, start, start + train_trades - 1,
                start + train_trades, start + train_trades + test_trades - 1,
                self.performance(train_result), self.performance(test_result),
            ))
            start += step
            window_id += 1
        if not windows:
            raise StrategyResearchError("insufficient trades for the requested walk-forward windows")
        return tuple(windows)

    def parameter_stability(self, runs: Mapping[str, RiskAwareBacktestResult]) -> ParameterStabilityResult:
        if not runs:
            raise StrategyResearchError("at least one parameter run is required")
        items = tuple((str(key), self.performance(value)) for key, value in runs.items())
        returns = [item[1].total_return_pct for item in items]
        pfs = [item[1].profit_factor for item in items if item[1].profit_factor is not None and math.isfinite(item[1].profit_factor)]
        profitable = sum(1 for value in returns if value > 0)
        avg = mean(returns)
        std = pstdev(returns) if len(returns) > 1 else 0.0
        # Higher when returns are positive and less dispersed; bounded to [0, 1].
        stability = 0.0 if avg <= 0 else max(0.0, min(1.0, avg / (avg + std + 1e-12)))
        return ParameterStabilityResult(
            run_count=len(items), returns_mean_pct=avg, returns_std_pct=std,
            returns_min_pct=min(returns), returns_max_pct=max(returns),
            profit_factor_mean=(mean(pfs) if pfs else None),
            max_drawdown_pct_mean=mean(item[1].max_drawdown_pct for item in items),
            profitable_run_count=profitable, profitable_run_fraction=profitable / len(items),
            return_stability_score=stability, runs=items,
        )

    @staticmethod
    def _trade_group(trade: RiskAwareTrade, field: str) -> str | None:
        metadata = trade.metadata or {}
        value = metadata.get(field)
        if value is None and field == "regime":
            value = metadata.get("market_regime")
        if value is None and field == "session":
            value = metadata.get("session_name") or metadata.get("forex_session")
        return str(value) if value is not None and str(value).strip() else None

    def group_stability(self, result: RiskAwareBacktestResult, field: str) -> GroupStabilityResult:
        if not isinstance(field, str) or not field.strip():
            raise StrategyResearchError("group field must be non-empty")
        grouped: dict[str, list[RiskAwareTrade]] = {}
        for trade in result.trades:
            key = self._trade_group(trade, field)
            if key is not None:
                grouped.setdefault(key, []).append(trade)
        if not grouped:
            raise StrategyResearchError(f"no trade metadata found for group field: {field}")
        items = tuple((key, self.performance(self._subset_result(result, trades))) for key, trades in sorted(grouped.items()))
        returns = [item[1].total_return_pct for item in items]
        profitable = sum(1 for value in returns if value > 0)
        return GroupStabilityResult(field, items, profitable / len(items), pstdev(returns) if len(returns) > 1 else 0.0)

    def monte_carlo(self, result: RiskAwareBacktestResult, simulations: int = 2000, trades_per_simulation: int | None = None, seed: int = 42, ruin_fraction: float = 0.5) -> MonteCarloResult:
        if simulations < 1 or simulations > 100_000:
            raise StrategyResearchError("simulations must be between 1 and 100000")
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise StrategyResearchError("seed must be an integer")
        if not 0.0 < float(ruin_fraction) < 1.0:
            raise StrategyResearchError("ruin_fraction must be between 0 and 1")
        rs = [float(trade.risk_multiple) for trade in result.trades if math.isfinite(float(trade.risk_multiple))]
        if not rs:
            raise StrategyResearchError("at least one finite trade risk multiple is required")
        count = len(rs) if trades_per_simulation is None else trades_per_simulation
        if count < 1 or count > 100_000:
            raise StrategyResearchError("trades_per_simulation must be between 1 and 100000")
        rng = random.Random(seed)
        terminal: list[float] = []
        drawdowns: list[float] = []
        positive = 0
        ruined = 0
        capital = float(result.initial_capital)
        risk_fraction_values = [
            float(trade.planned_risk_amount) / float(result.initial_capital)
            for trade in result.trades
            if trade.planned_risk_amount > 0
        ]
        risk_fraction = mean(risk_fraction_values) if risk_fraction_values else 0.0
        for _ in range(simulations):
            equity = capital
            peak = capital
            max_dd = 0.0
            for _ in range(count):
                r_multiple = rng.choice(rs)
                equity += equity * risk_fraction * r_multiple
                peak = max(peak, equity)
                max_dd = max(max_dd, peak - equity)
                if equity <= capital * ruin_fraction:
                    ruined += 1
                    # Continue the path to keep simulation length consistent.
            terminal.append(equity)
            drawdowns.append(max_dd)
            if equity > capital:
                positive += 1
        terminal_sorted = sorted(terminal)
        def quantile(values: list[float], q: float) -> float:
            position = (len(values) - 1) * q
            lower = int(math.floor(position))
            upper = int(math.ceil(position))
            if lower == upper:
                return values[lower]
            weight = position - lower
            return values[lower] * (1.0 - weight) + values[upper] * weight
        return MonteCarloResult(
            seed=seed, simulations=simulations, trades_per_simulation=count,
            starting_capital=capital, terminal_equity_mean=mean(terminal),
            terminal_equity_median=quantile(terminal_sorted, 0.50),
            terminal_equity_p05=quantile(terminal_sorted, 0.05),
            terminal_equity_p95=quantile(terminal_sorted, 0.95),
            drawdown_p95=quantile(sorted(drawdowns), 0.95),
            positive_terminal_fraction=positive / simulations,
            ruin_fraction=ruined / simulations,
        )

    def analyze(
        self,
        result: RiskAwareBacktestResult,
        *,
        train_fraction: float | None = 0.70,
        walk_forward_config: tuple[int, int, int | None] | None = None,
        parameter_runs: Mapping[str, RiskAwareBacktestResult] | None = None,
        include_regime: bool = True,
        include_session: bool = True,
        monte_carlo_config: tuple[int, int | None, int, float] | None = (2000, None, 42, 0.50),
        metadata: Mapping[str, Any] | None = None,
    ) -> StrategyResearchReport:
        baseline = self.performance(result)
        warnings: list[str] = []
        oos = None
        if train_fraction is not None:
            try:
                oos = self.out_of_sample(result, train_fraction)
                if not oos.out_of_sample_positive:
                    warnings.append("out-of-sample net P&L is non-positive")
            except StrategyResearchError as exc:
                warnings.append(str(exc))
        wf: tuple[WalkForwardWindow, ...] = ()
        if walk_forward_config is not None:
            try:
                wf = self.walk_forward(result, *walk_forward_config)
                if wf and sum(window.test.net_pnl > 0 for window in wf) < len(wf) / 2:
                    warnings.append("fewer than half of walk-forward test windows are profitable")
            except StrategyResearchError as exc:
                warnings.append(str(exc))
        parameter = self.parameter_stability(parameter_runs) if parameter_runs else None
        regime = None
        session = None
        if include_regime:
            try:
                regime = self.group_stability(result, "regime")
            except StrategyResearchError as exc:
                warnings.append(str(exc))
        if include_session:
            try:
                session = self.group_stability(result, "session")
            except StrategyResearchError as exc:
                warnings.append(str(exc))
        mc = None
        if monte_carlo_config is not None:
            try:
                mc = self.monte_carlo(result, *monte_carlo_config)
            except StrategyResearchError as exc:
                warnings.append(str(exc))
        return StrategyResearchReport(
            baseline=baseline, out_of_sample=oos, walk_forward=wf,
            parameter_stability=parameter, regime_stability=regime,
            session_stability=session, monte_carlo=mc,
            warnings=tuple(warnings), metadata=dict(metadata or {}),
        )


def research_backtest(result: RiskAwareBacktestResult, **kwargs: Any) -> StrategyResearchReport:
    """Convenience API for Phase 2.9 research analysis."""
    return StrategyResearchEngine().analyze(result, **kwargs)
