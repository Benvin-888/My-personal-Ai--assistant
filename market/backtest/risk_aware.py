"""APEX / BENVIN risk-aware historical backtesting.

Phase 2.8 - Risk-Aware Backtesting.

This module sits above the Phase 2.5 point-in-time replay foundation and
Phase 2.7 risk management foundation.  It answers a narrower economic
question than a signal-only backtest: what happens when candidate
opportunities are risk-assessed, sized, friction-adjusted, and then replayed
against historical OHLC data?

Hard invariants:
    * opportunities are generated from frame N only;
    * execution occurs at frame N+1 open;
    * no future candle is supplied to the opportunity or level provider;
    * stops/targets are evaluated only from the entry candle onward;
    * if both stop and target are touched in one bar, the configured policy is
      deterministic and defaults to the conservative stop outcome;
    * no broker, account, network, or live execution I/O occurs.

This module is a simulation and research tool.  It does not establish that a
strategy is profitable in live trading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Callable, Iterable, Mapping

from .friction import ExecutionFrictionConfig, ExecutionFrictionModel
from .models import BacktestConfig, BacktestDataset, BacktestFrame
from .position import PositionSide
from ..opportunity import TradeOpportunity
from ..risk import AccountSnapshot, ExposureSnapshot, RiskDecision, RiskEngine, RiskPolicy, TradePlan
from ..strategy.models import SignalDirection


class RiskAwareBacktestError(ValueError):
    """Raised when risk-aware backtesting input is invalid."""


class IntrabarPolicy(str, Enum):
    """Deterministic policy when SL and TP are both touched in one candle."""

    CONSERVATIVE_STOP = "CONSERVATIVE_STOP"
    TARGET_FIRST = "TARGET_FIRST"
    STOP_FIRST = "STOP_FIRST"


class RiskAwareTradeStatus(str, Enum):
    """Lifecycle outcome of one risk-approved historical trade."""

    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    END_OF_TEST = "END_OF_TEST"


@dataclass(frozen=True)
class RiskAwareBacktestConfig:
    """Immutable economic assumptions for a risk-aware replay."""

    pair: str
    interval: str
    initial_capital: float = 10_000.0
    warmup_candles: int = 0
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)
    risk_fraction: float | None = None
    value_per_price_unit: float = 1.0
    quantity_step: float = 1.0
    min_quantity: float = 0.0
    max_quantity: float | None = None
    friction: ExecutionFrictionConfig = field(default_factory=ExecutionFrictionConfig)
    intrabar_policy: IntrabarPolicy = IntrabarPolicy.CONSERVATIVE_STOP
    close_at_end: bool = True
    reject_if_friction_exceeds_planned_risk: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.pair, str) or not self.pair.strip():
            raise RiskAwareBacktestError("pair must be a non-empty string")
        if not isinstance(self.interval, str) or not self.interval.strip():
            raise RiskAwareBacktestError("interval must be a non-empty string")
        for name, value in (("initial_capital", self.initial_capital), ("value_per_price_unit", self.value_per_price_unit), ("quantity_step", self.quantity_step), ("min_quantity", self.min_quantity)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise RiskAwareBacktestError(f"{name} must be finite numeric")
        if self.initial_capital <= 0 or self.value_per_price_unit <= 0 or self.quantity_step <= 0 or self.min_quantity < 0:
            raise RiskAwareBacktestError("capital, value_per_price_unit, and quantity_step must be positive; min_quantity must be non-negative")
        if self.max_quantity is not None and (isinstance(self.max_quantity, bool) or not isinstance(self.max_quantity, (int, float)) or not math.isfinite(float(self.max_quantity)) or self.max_quantity <= 0):
            raise RiskAwareBacktestError("max_quantity must be positive and finite or None")
        if not isinstance(self.risk_policy, RiskPolicy):
            raise RiskAwareBacktestError("risk_policy must be a RiskPolicy")
        if self.risk_fraction is not None and (isinstance(self.risk_fraction, bool) or not isinstance(self.risk_fraction, (int, float)) or not math.isfinite(float(self.risk_fraction)) or self.risk_fraction < 0 or self.risk_fraction > 1):
            raise RiskAwareBacktestError("risk_fraction must be between 0 and 1 or None")
        if not isinstance(self.friction, ExecutionFrictionConfig):
            raise RiskAwareBacktestError("friction must be an ExecutionFrictionConfig")
        if not isinstance(self.intrabar_policy, IntrabarPolicy):
            raise RiskAwareBacktestError("intrabar_policy must be an IntrabarPolicy")
        if not isinstance(self.close_at_end, bool) or not isinstance(self.reject_if_friction_exceeds_planned_risk, bool):
            raise RiskAwareBacktestError("boolean configuration fields must be bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "interval": self.interval,
            "initial_capital": float(self.initial_capital),
            "warmup_candles": self.warmup_candles,
            "risk_policy": self.risk_policy.to_dict(),
            "risk_fraction": self.risk_fraction,
            "value_per_price_unit": float(self.value_per_price_unit),
            "quantity_step": float(self.quantity_step),
            "min_quantity": float(self.min_quantity),
            "max_quantity": self.max_quantity,
            "friction": self.friction.to_dict(),
            "intrabar_policy": self.intrabar_policy.value,
            "close_at_end": self.close_at_end,
            "reject_if_friction_exceeds_planned_risk": self.reject_if_friction_exceeds_planned_risk,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RiskAwareTrade:
    """One completed or end-of-test risk-managed historical trade."""

    trade_id: int
    opportunity_timestamp_utc: str | None
    signal_index: int
    entry_index: int
    exit_index: int
    pair: str
    direction: str
    entry_market_price: float
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_market_price: float
    exit_price: float
    quantity: float
    planned_risk_amount: float
    realized_pnl: float
    gross_pnl: float
    transaction_costs: float
    status: RiskAwareTradeStatus
    reward_risk: float
    risk_multiple: float
    risk_budget_breached: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.trade_id < 1 or self.signal_index < 0 or self.entry_index != self.signal_index + 1 or self.exit_index < self.entry_index:
            raise RiskAwareBacktestError("invalid trade indices")
        if not isinstance(self.status, RiskAwareTradeStatus):
            raise RiskAwareBacktestError("status must be RiskAwareTradeStatus")
        for name in ("entry_market_price", "entry_price", "stop_loss", "take_profit", "exit_market_price", "exit_price", "quantity", "planned_risk_amount", "realized_pnl", "gross_pnl", "transaction_costs", "reward_risk", "risk_multiple"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise RiskAwareBacktestError(f"{name} must be finite")
        if min(self.entry_market_price, self.entry_price, self.stop_loss, self.take_profit, self.exit_market_price, self.exit_price) <= 0:
            raise RiskAwareBacktestError("trade prices must be positive")
        if self.quantity <= 0 or self.planned_risk_amount <= 0 or self.transaction_costs < 0:
            raise RiskAwareBacktestError("quantity and planned risk must be positive; costs cannot be negative")
        if not math.isclose(self.realized_pnl, self.gross_pnl - self.transaction_costs, rel_tol=0.0, abs_tol=1e-10):
            raise RiskAwareBacktestError("realized_pnl must equal gross_pnl minus transaction_costs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "opportunity_timestamp_utc": self.opportunity_timestamp_utc,
            "signal_index": self.signal_index,
            "entry_index": self.entry_index,
            "exit_index": self.exit_index,
            "pair": self.pair,
            "direction": self.direction,
            "entry_market_price": self.entry_market_price,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "exit_market_price": self.exit_market_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "planned_risk_amount": self.planned_risk_amount,
            "realized_pnl": self.realized_pnl,
            "gross_pnl": self.gross_pnl,
            "transaction_costs": self.transaction_costs,
            "status": self.status.value,
            "reward_risk": self.reward_risk,
            "risk_multiple": self.risk_multiple,
            "risk_budget_breached": self.risk_budget_breached,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RiskAwareEvent:
    """Auditable point-in-time event from the risk-aware replay."""

    index: int
    timestamp_utc: str
    event_type: str
    equity: float
    realized_pnl: float
    open_risk_amount: float
    signal_index: int | None = None
    trade_id: int | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.index < 0 or not self.timestamp_utc or not self.event_type:
            raise RiskAwareBacktestError("invalid event identity")
        for name in ("equity", "realized_pnl", "open_risk_amount"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise RiskAwareBacktestError(f"{name} must be finite")
        if self.open_risk_amount < 0:
            raise RiskAwareBacktestError("open_risk_amount cannot be negative")
        if self.signal_index is not None and (self.signal_index < 0 or self.signal_index > self.index):
            raise RiskAwareBacktestError("signal_index must be at or before event index")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "timestamp_utc": self.timestamp_utc,
            "event_type": self.event_type,
            "equity": self.equity,
            "realized_pnl": self.realized_pnl,
            "open_risk_amount": self.open_risk_amount,
            "signal_index": self.signal_index,
            "trade_id": self.trade_id,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RiskAwareBacktestResult:
    """Complete immutable output of a risk-aware historical simulation."""

    pair: str
    interval: str
    initial_capital: float
    final_equity: float
    net_pnl: float
    total_return_pct: float
    peak_equity: float
    max_drawdown: float
    max_drawdown_pct: float
    trades: tuple[RiskAwareTrade, ...]
    events: tuple[RiskAwareEvent, ...]
    rejected_opportunities: int
    risk_rejections: int
    candidate_opportunities: int
    stop_losses: int
    take_profits: int
    end_of_test_closures: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    gross_profit: float
    gross_loss: float
    profit_factor: float | None
    average_win: float
    average_loss: float
    average_risk_multiple: float
    total_transaction_costs: float
    risk_budget_breaches: int
    config: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        return self.winning_trades / self.trade_count if self.trade_count else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": "forex",
            "analysis": "risk_aware_backtest",
            "pair": self.pair,
            "interval": self.interval,
            "initial_capital": self.initial_capital,
            "final_equity": self.final_equity,
            "net_pnl": self.net_pnl,
            "total_return_pct": self.total_return_pct,
            "peak_equity": self.peak_equity,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "trade_count": self.trade_count,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
            "win_rate": self.win_rate,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "profit_factor": self.profit_factor,
            "average_win": self.average_win,
            "average_loss": self.average_loss,
            "average_risk_multiple": self.average_risk_multiple,
            "total_transaction_costs": self.total_transaction_costs,
            "candidate_opportunities": self.candidate_opportunities,
            "rejected_opportunities": self.rejected_opportunities,
            "risk_rejections": self.risk_rejections,
            "stop_losses": self.stop_losses,
            "take_profits": self.take_profits,
            "end_of_test_closures": self.end_of_test_closures,
            "risk_budget_breaches": self.risk_budget_breaches,
            "config": dict(self.config),
            "trades": [item.to_dict() for item in self.trades],
            "events": [item.to_dict() for item in self.events],
            "metadata": dict(self.metadata),
        }


OpportunityProvider = Callable[[BacktestFrame], TradeOpportunity | None]
LevelProvider = Callable[[TradeOpportunity, BacktestFrame, float], tuple[float, float]]


class RiskAwareBacktestEngine:
    """Deterministic single-position risk-aware historical backtest engine."""

    def __init__(self, config: RiskAwareBacktestConfig) -> None:
        if not isinstance(config, RiskAwareBacktestConfig):
            raise RiskAwareBacktestError("config must be RiskAwareBacktestConfig")
        self.config = config
        self.friction = ExecutionFrictionModel(config.friction)
        self.risk_engine = RiskEngine(config.risk_policy)

    @staticmethod
    def _utc_date(timestamp_utc: str) -> str:
        try:
            value = timestamp_utc.replace("Z", "+00:00")
            return datetime.fromisoformat(value).astimezone(timezone.utc).date().isoformat()
        except Exception as exc:
            raise RiskAwareBacktestError("candle timestamp_utc must be ISO-8601") from exc

    @staticmethod
    def _validate_dataset(dataset: BacktestDataset, config: RiskAwareBacktestConfig) -> None:
        if not isinstance(dataset, BacktestDataset):
            raise RiskAwareBacktestError("dataset must be a BacktestDataset")
        if dataset.pair.strip().upper() != config.pair.strip().upper():
            raise RiskAwareBacktestError("dataset pair does not match config pair")
        if dataset.interval.strip().lower() != config.interval.strip().lower():
            raise RiskAwareBacktestError("dataset interval does not match config interval")
        if len(dataset.candles) < 2:
            raise RiskAwareBacktestError("at least two candles are required for next-bar execution")

    @staticmethod
    def _direction_side(direction: str) -> PositionSide:
        normalized = str(direction).upper()
        if normalized == "LONG":
            return PositionSide.LONG
        if normalized == "SHORT":
            return PositionSide.SHORT
        raise RiskAwareBacktestError("trade direction must be LONG or SHORT")

    def _friction_risk(self, plan: TradePlan) -> float:
        adverse = self.config.friction.half_spread + self.config.friction.slippage
        price_risk = (plan.stop_distance + 2.0 * adverse) * plan.quantity * self.config.value_per_price_unit
        costs = 2.0 * (self.config.friction.transaction_cost_per_unit * plan.quantity + self.config.friction.fixed_transaction_cost)
        return price_risk + costs

    def _hit(self, candle: Any, plan: TradePlan) -> tuple[float, RiskAwareTradeStatus] | None:
        open_price = float(candle.open)
        high = float(candle.high)
        low = float(candle.low)
        if plan.direction == "LONG":
            # A gap through a protective level is filled at the bar open, not
            # at an unavailable historical price beyond the open.
            if open_price <= plan.stop_loss:
                return open_price, RiskAwareTradeStatus.STOP_LOSS
            if open_price >= plan.take_profit:
                return open_price, RiskAwareTradeStatus.TAKE_PROFIT
            stop_hit = low <= plan.stop_loss
            target_hit = high >= plan.take_profit
        else:
            if open_price >= plan.stop_loss:
                return open_price, RiskAwareTradeStatus.STOP_LOSS
            if open_price <= plan.take_profit:
                return open_price, RiskAwareTradeStatus.TAKE_PROFIT
            stop_hit = high >= plan.stop_loss
            target_hit = low <= plan.take_profit
        if not stop_hit and not target_hit:
            return None
        if stop_hit and target_hit:
            if self.config.intrabar_policy in (IntrabarPolicy.CONSERVATIVE_STOP, IntrabarPolicy.STOP_FIRST):
                return plan.stop_loss, RiskAwareTradeStatus.STOP_LOSS
            return plan.take_profit, RiskAwareTradeStatus.TAKE_PROFIT
        if stop_hit:
            return plan.stop_loss, RiskAwareTradeStatus.STOP_LOSS
        return plan.take_profit, RiskAwareTradeStatus.TAKE_PROFIT

    def _close_trade(self, *, trade_id: int, opportunity: TradeOpportunity, plan: TradePlan, signal_index: int, entry_index: int, exit_index: int, exit_market_price: float, status: RiskAwareTradeStatus, entry_fill_price: float, entry_market_price: float, entry_cost: float) -> RiskAwareTrade:
        side = self._direction_side(plan.direction)
        exit_fill = self.friction.fill(exit_market_price, plan.quantity, side, is_entry=False)
        if side is PositionSide.LONG:
            gross = (exit_fill.execution_price - entry_fill_price) * plan.quantity * self.config.value_per_price_unit
        else:
            gross = (entry_fill_price - exit_fill.execution_price) * plan.quantity * self.config.value_per_price_unit
        costs = entry_cost + exit_fill.transaction_cost
        pnl = gross - costs
        risk_multiple = pnl / plan.risk_amount if plan.risk_amount > 0 else 0.0
        breach = status is RiskAwareTradeStatus.STOP_LOSS and abs(pnl) > plan.risk_amount + 1e-9
        return RiskAwareTrade(
            trade_id=trade_id,
            opportunity_timestamp_utc=opportunity.timestamp_utc,
            signal_index=signal_index,
            entry_index=entry_index,
            exit_index=exit_index,
            pair=plan.pair,
            direction=plan.direction,
            entry_market_price=entry_market_price,
            entry_price=entry_fill_price,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            exit_market_price=exit_market_price,
            exit_price=exit_fill.execution_price,
            quantity=plan.quantity,
            planned_risk_amount=plan.risk_amount,
            realized_pnl=pnl,
            gross_pnl=gross,
            transaction_costs=costs,
            status=status,
            reward_risk=plan.reward_risk,
            risk_multiple=risk_multiple,
            risk_budget_breached=breach,
            metadata={"risk_decision": "APPROVED", "risk_plan": plan.to_dict()},
        )

    def _marked_pnl(
        self,
        active: tuple[TradeOpportunity, TradePlan, int, int, float, float, float],
        market_price: float,
    ) -> float:
        """Return conservative mark-to-market P&L for an open trade."""
        _, plan, _, _, entry_price, _, entry_cost = active
        side = self._direction_side(plan.direction)
        exit_fill = self.friction.fill(market_price, plan.quantity, side, is_entry=False)
        if side is PositionSide.LONG:
            gross = (exit_fill.execution_price - entry_price) * plan.quantity * self.config.value_per_price_unit
        else:
            gross = (entry_price - exit_fill.execution_price) * plan.quantity * self.config.value_per_price_unit
        return gross - entry_cost - exit_fill.transaction_cost

    def run(
        self,
        dataset: BacktestDataset,
        opportunity_provider: OpportunityProvider,
        level_provider: LevelProvider,
    ) -> RiskAwareBacktestResult:
        """Run one deterministic, single-position risk-aware historical replay."""
        self._validate_dataset(dataset, self.config)
        if not callable(opportunity_provider) or not callable(level_provider):
            raise RiskAwareBacktestError(
                "opportunity_provider and level_provider must be callable"
            )

        candles = dataset.candles
        realized = 0.0
        peak_equity = float(self.config.initial_capital)
        current_day: str | None = None
        daily_realized = 0.0
        consecutive_losses = 0

        trades: list[RiskAwareTrade] = []
        events: list[RiskAwareEvent] = []
        candidate_count = 0
        rejected_count = 0
        risk_rejections = 0

        # opportunity, signal_index, entry_index, raw_entry, stop, target
        pending: tuple[TradeOpportunity, int, int, float, float, float] | None = None
        # opportunity, plan, signal_index, entry_index, entry_fill, raw_entry, entry_cost
        active: tuple[TradeOpportunity, TradePlan, int, int, float, float, float] | None = None

        def equity() -> float:
            return float(self.config.initial_capital) + realized

        def record(
            index: int,
            event_type: str,
            *,
            signal_index: int | None = None,
            trade_id: int | None = None,
            open_risk: float = 0.0,
            reason: str = "",
            metadata: dict[str, Any] | None = None,
            equity_override: float | None = None,
        ) -> None:
            nonlocal peak_equity
            current_equity = equity() if equity_override is None else float(equity_override)
            peak_equity = max(peak_equity, current_equity)
            events.append(
                RiskAwareEvent(
                    index=index,
                    timestamp_utc=candles[index].timestamp_utc,
                    event_type=event_type,
                    equity=current_equity,
                    realized_pnl=realized,
                    open_risk_amount=max(0.0, open_risk),
                    signal_index=signal_index,
                    trade_id=trade_id,
                    reason=reason,
                    metadata=metadata or {},
                )
            )

        for index, candle in enumerate(candles):
            frame = BacktestFrame(
                index=index,
                candle=candle,
                available_candles=tuple(candles[: index + 1]),
            )
            day = self._utc_date(candle.timestamp_utc)
            if current_day is None or day != current_day:
                current_day = day
                daily_realized = 0.0

            # 1. Execute the already-generated opportunity at N+1 open.
            if pending is not None and index == pending[2]:
                opportunity, signal_index, entry_index, raw_entry, stop, target = pending
                pending = None

                try:
                    direction = opportunity.direction.value
                    side = self._direction_side(direction)
                    decision: RiskDecision = self.risk_engine.assess(
                        opportunity,
                        entry_price=raw_entry,
                        stop_loss=stop,
                        take_profit=target,
                        account=AccountSnapshot(equity(), peak_equity),
                        exposure=ExposureSnapshot(
                            open_risk_amount=0.0,
                            daily_realized_pnl=daily_realized,
                            open_positions=0,
                            consecutive_losses=consecutive_losses,
                            pair_risk_amount=0.0,
                        ),
                        risk_fraction=self.config.risk_fraction,
                        value_per_price_unit=self.config.value_per_price_unit,
                        quantity_step=self.config.quantity_step,
                        min_quantity=self.config.min_quantity,
                        max_quantity=self.config.max_quantity,
                    )
                except Exception as exc:
                    risk_rejections += 1
                    record(
                        index,
                        "RISK_ERROR",
                        signal_index=signal_index,
                        reason=str(exc),
                    )
                    continue

                if not decision.approved or decision.plan is None:
                    risk_rejections += 1
                    record(
                        index,
                        "RISK_REJECTED",
                        signal_index=signal_index,
                        reason="; ".join(decision.reasons) or "risk decision rejected",
                        metadata={"status": decision.status.value},
                    )
                    continue

                plan = decision.plan
                entry_fill = self.friction.fill(raw_entry, plan.quantity, side, is_entry=True)
                friction_risk = self._friction_risk(plan)
                if (
                    self.config.reject_if_friction_exceeds_planned_risk
                    and friction_risk > plan.risk_amount + 1e-9
                ):
                    risk_rejections += 1
                    record(
                        index,
                        "RISK_REJECTED_FRICTION",
                        signal_index=signal_index,
                        reason="friction-adjusted worst-case loss exceeds planned risk budget",
                        metadata={
                            "planned_risk_amount": plan.risk_amount,
                            "friction_adjusted_worst_case": friction_risk,
                        },
                    )
                    continue

                active = (
                    opportunity,
                    plan,
                    signal_index,
                    entry_index,
                    entry_fill.execution_price,
                    raw_entry,
                    entry_fill.transaction_cost,
                )
                record(
                    index,
                    "ENTRY",
                    signal_index=signal_index,
                    trade_id=len(trades) + 1,
                    open_risk=plan.risk_amount,
                    reason="risk-approved next-bar-open entry",
                    equity_override=equity() - entry_fill.transaction_cost,
                    metadata={
                        "entry_market_price": raw_entry,
                        "entry_price": entry_fill.execution_price,
                        "quantity": plan.quantity,
                        "risk_amount": plan.risk_amount,
                    },
                )

            # 2. Evaluate the active position using only this candle's OHLC.
            if active is not None:
                (
                    opportunity,
                    plan,
                    signal_index,
                    entry_index,
                    entry_price,
                    entry_market_price,
                    entry_cost,
                ) = active
                hit = self._hit(candle, plan)
                if hit is not None and index >= entry_index:
                    exit_market, status = hit
                    trade = self._close_trade(
                        trade_id=len(trades) + 1,
                        opportunity=opportunity,
                        plan=plan,
                        signal_index=signal_index,
                        entry_index=entry_index,
                        exit_index=index,
                        exit_market_price=exit_market,
                        status=status,
                        entry_fill_price=entry_price,
                        entry_market_price=entry_market_price,
                        entry_cost=entry_cost,
                    )
                    trades.append(trade)
                    realized += trade.realized_pnl
                    daily_realized += trade.realized_pnl
                    consecutive_losses = (
                        consecutive_losses + 1 if trade.realized_pnl < 0 else 0
                    )
                    record(
                        index,
                        status.value,
                        signal_index=signal_index,
                        trade_id=trade.trade_id,
                        reason="deterministic SL/TP exit",
                        metadata={
                            "risk_multiple": trade.risk_multiple,
                            "realized_pnl": trade.realized_pnl,
                        },
                    )
                    active = None

            # 3. Every frame can generate a new candidate, but only N+1 can execute it.
            # The provider still receives the last frame's point-in-time prefix; a
            # directional candidate there is rejected because no future open exists.
            if active is None and pending is None:
                opportunity = opportunity_provider(frame)
                if opportunity is not None:
                    candidate_count += 1
                    if not isinstance(opportunity, TradeOpportunity):
                        raise RiskAwareBacktestError(
                            "opportunity_provider must return TradeOpportunity or None"
                        )
                    if not opportunity.is_candidate or opportunity.direction is SignalDirection.NEUTRAL:
                        rejected_count += 1
                        record(
                            index,
                            "OPPORTUNITY_REJECTED",
                            signal_index=index,
                            reason="opportunity is not a directional candidate",
                        )
                    elif index + 1 >= len(candles):
                        rejected_count += 1
                        record(
                            index,
                            "OPPORTUNITY_REJECTED_NO_NEXT_BAR",
                            signal_index=index,
                            reason="directional opportunity cannot execute without a next bar",
                        )
                    elif len(frame.available_candles) < self.config.warmup_candles:
                        rejected_count += 1
                        record(
                            index,
                            "OPPORTUNITY_REJECTED_WARMUP",
                            signal_index=index,
                            reason="configured warm-up period is not complete",
                        )
                    else:
                        next_open = float(candles[index + 1].open)
                        try:
                            stop, target = level_provider(
                                opportunity, frame, next_open
                            )
                        except Exception as exc:
                            risk_rejections += 1
                            record(
                                index,
                                "LEVEL_REJECTED",
                                signal_index=index,
                                reason=str(exc),
                            )
                            continue
                        if not all(
                            isinstance(value, (int, float))
                            and not isinstance(value, bool)
                            and math.isfinite(float(value))
                            and float(value) > 0
                            for value in (stop, target)
                        ):
                            risk_rejections += 1
                            record(
                                index,
                                "LEVEL_REJECTED",
                                signal_index=index,
                                reason="stop and target must be positive finite numbers",
                            )
                            continue
                        pending = (
                            opportunity,
                            index,
                            index + 1,
                            next_open,
                            float(stop),
                            float(target),
                        )
                        record(
                            index,
                            "OPPORTUNITY_ACCEPTED",
                            signal_index=index,
                            reason="candidate scheduled for next-bar-open risk assessment",
                        )

            # Mark the realized-equity timeline. Open P&L is deliberately not
            # folded into account equity here because the authoritative risk
            # controls operate on realized account state at decision points.
            if active is not None:
                marked_pnl = self._marked_pnl(active, float(candle.close))
                record(
                    index,
                    "MARK",
                    signal_index=active[2],
                    trade_id=len(trades) + 1,
                    open_risk=active[1].risk_amount,
                    equity_override=equity() + marked_pnl,
                    reason="point-in-time mark-to-market",
                    metadata={"marked_pnl": marked_pnl},
                )

        # Close an outstanding position at the final close if configured.
        if active is not None and self.config.close_at_end:
            (
                opportunity,
                plan,
                signal_index,
                entry_index,
                entry_price,
                entry_market_price,
                entry_cost,
            ) = active
            index = len(candles) - 1
            candle = candles[index]
            trade = self._close_trade(
                trade_id=len(trades) + 1,
                opportunity=opportunity,
                plan=plan,
                signal_index=signal_index,
                entry_index=entry_index,
                exit_index=index,
                exit_market_price=float(candle.close),
                status=RiskAwareTradeStatus.END_OF_TEST,
                entry_fill_price=entry_price,
                entry_market_price=entry_market_price,
                entry_cost=entry_cost,
            )
            trades.append(trade)
            realized += trade.realized_pnl
            record(
                index,
                RiskAwareTradeStatus.END_OF_TEST.value,
                signal_index=signal_index,
                trade_id=trade.trade_id,
                reason="end-of-test close",
                metadata={"risk_multiple": trade.risk_multiple},
            )

        final_equity = equity()
        running_peak = float(self.config.initial_capital)
        max_dd = 0.0
        for event in events:
            running_peak = max(running_peak, event.equity)
            max_dd = max(max_dd, running_peak - event.equity)
        max_dd_pct = (max_dd / running_peak * 100.0) if running_peak > 0 else 0.0

        winners = [trade for trade in trades if trade.realized_pnl > 0]
        losers = [trade for trade in trades if trade.realized_pnl < 0]
        gross_profit = sum(trade.realized_pnl for trade in winners)
        gross_loss = -sum(trade.realized_pnl for trade in losers)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

        return RiskAwareBacktestResult(
            pair=self.config.pair.upper(),
            interval=self.config.interval,
            initial_capital=self.config.initial_capital,
            final_equity=final_equity,
            net_pnl=final_equity - self.config.initial_capital,
            total_return_pct=(final_equity / self.config.initial_capital - 1.0) * 100.0,
            peak_equity=max(peak_equity, self.config.initial_capital),
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            trades=tuple(trades),
            events=tuple(events),
            rejected_opportunities=rejected_count,
            risk_rejections=risk_rejections,
            candidate_opportunities=candidate_count,
            stop_losses=sum(trade.status is RiskAwareTradeStatus.STOP_LOSS for trade in trades),
            take_profits=sum(trade.status is RiskAwareTradeStatus.TAKE_PROFIT for trade in trades),
            end_of_test_closures=sum(trade.status is RiskAwareTradeStatus.END_OF_TEST for trade in trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            breakeven_trades=sum(trade.realized_pnl == 0 for trade in trades),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            average_win=gross_profit / len(winners) if winners else 0.0,
            average_loss=sum(trade.realized_pnl for trade in losers) / len(losers) if losers else 0.0,
            average_risk_multiple=(
                sum(trade.risk_multiple for trade in trades) / len(trades)
                if trades else 0.0
            ),
            total_transaction_costs=sum(trade.transaction_costs for trade in trades),
            risk_budget_breaches=sum(trade.risk_budget_breached for trade in trades),
            config=self.config.to_dict(),
            metadata={
                "execution_timing": "NEXT_BAR_OPEN",
                "intrabar_policy": self.config.intrabar_policy.value,
                "single_position": True,
                "network_io": False,
                "broker_execution": False,
                "risk_controls_reassessed_at_entry": True,
            },
        )


def run_risk_aware_backtest(dataset: BacktestDataset, config: RiskAwareBacktestConfig, opportunity_provider: OpportunityProvider, level_provider: LevelProvider) -> RiskAwareBacktestResult:
    """Convenience API for deterministic Phase 2.8 replay."""
    return RiskAwareBacktestEngine(config).run(dataset, opportunity_provider, level_provider)


__all__ = [
    "IntrabarPolicy",
    "LevelProvider",
    "OpportunityProvider",
    "RiskAwareBacktestConfig",
    "RiskAwareBacktestEngine",
    "RiskAwareBacktestError",
    "RiskAwareBacktestResult",
    "RiskAwareEvent",
    "RiskAwareTrade",
    "RiskAwareTradeStatus",
    "run_risk_aware_backtest",
]
