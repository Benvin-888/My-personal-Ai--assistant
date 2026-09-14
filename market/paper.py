"""APEX / BENVIN deterministic paper-trading simulation engine.

Phase 2.19 - Paper Trading Simulation Engine

Research-only simulation.  It consumes risk-approved TradePlan objects and
historical candle-like mappings.  It never connects to a broker, sends an
order, reads an account, or authorizes execution.

Execution semantics intentionally mirror the risk-aware backtester:
- a plan observed on candle N is eligible to enter at candle N+1 open;
- the plan is never created from future candles by the engine;
- spread/slippage/transaction costs are applied through ExecutionFrictionModel;
- stop/target collisions use an explicit intrabar policy;
- all state transitions are immutable event records.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from datetime import datetime
import math
from typing import Any, Callable, Mapping, Sequence

from .backtest.friction import ExecutionFrictionConfig, ExecutionFrictionModel
from .backtest.position import PositionSide
from .risk import TradePlan


class PaperTradingError(ValueError):
    """Raised when paper-trading configuration or input is invalid."""


class PaperTradeStatus(str, Enum):
    OPEN = "OPEN"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    END_OF_TEST = "END_OF_TEST"


class PaperEventType(str, Enum):
    MARK = "MARK"
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REJECTED = "REJECTED"


class PaperIntrabarPolicy(str, Enum):
    CONSERVATIVE_STOP = "CONSERVATIVE_STOP"
    TARGET_FIRST = "TARGET_FIRST"
    STOP_FIRST = "STOP_FIRST"


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PaperTradingError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise PaperTradingError(f"{name} must be finite")
    if positive and value <= 0:
        raise PaperTradingError(f"{name} must be positive")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PaperTradingError(f"{name} must be a non-empty string")
    return value.strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _candle(frame: Mapping[str, Any]) -> tuple[str, float, float, float, float]:
    if not isinstance(frame, Mapping):
        raise PaperTradingError("each candle must be a mapping")
    timestamp = _text(frame.get("timestamp_utc"), "candle timestamp_utc")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise PaperTradingError("candle timestamp_utc must be ISO-8601") from exc
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
        raise PaperTradingError("candle timestamp_utc must include timezone information")
    values = tuple(_number(frame.get(name), name, positive=True) for name in ("open", "high", "low", "close"))
    open_, high, low, close = values
    if high < max(open_, close) or low > min(open_, close) or high < low:
        raise PaperTradingError("invalid OHLC relationship")
    return timestamp, open_, high, low, close


@dataclass(frozen=True)
class PaperTradingConfig:
    """Conservative research-only paper simulation settings."""

    initial_equity: float = 10_000.0
    intrabar_policy: PaperIntrabarPolicy = PaperIntrabarPolicy.CONSERVATIVE_STOP
    allow_new_entries: bool = True
    mark_to_market: bool = True
    reject_if_friction_exceeds_planned_risk: bool = True
    max_bars: int | None = None

    def __post_init__(self) -> None:
        _number(self.initial_equity, "initial_equity", positive=True)
        if not isinstance(self.intrabar_policy, PaperIntrabarPolicy):
            raise PaperTradingError("intrabar_policy must be PaperIntrabarPolicy")
        for name in ("allow_new_entries", "mark_to_market", "reject_if_friction_exceeds_planned_risk"):
            if not isinstance(getattr(self, name), bool):
                raise PaperTradingError(f"{name} must be boolean")
        if self.max_bars is not None and (isinstance(self.max_bars, bool) or not isinstance(self.max_bars, int) or self.max_bars < 2):
            raise PaperTradingError("max_bars must be an integer >= 2 when supplied")

    def to_dict(self) -> dict[str, Any]:
        return {"initial_equity": self.initial_equity, "intrabar_policy": self.intrabar_policy.value,
                "allow_new_entries": self.allow_new_entries, "mark_to_market": self.mark_to_market,
                "reject_if_friction_exceeds_planned_risk": self.reject_if_friction_exceeds_planned_risk,
                "max_bars": self.max_bars}


@dataclass(frozen=True)
class PaperPosition:
    pair: str
    interval: str
    direction: str
    quantity: float
    plan_entry_price: float
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_timestamp_utc: str
    plan_timestamp_utc: str | None
    entry_cost: float
    risk_amount: float

    def __post_init__(self) -> None:
        _text(self.pair, "pair"); _text(self.interval, "interval"); _text(self.direction, "direction")
        for name in ("quantity", "entry_price", "stop_loss", "take_profit", "risk_amount"):
            _number(getattr(self, name), name, positive=True)
        _number(self.entry_cost, "entry_cost")
        if self.entry_cost < 0:
            raise PaperTradingError("entry_cost must be non-negative")
        _text(self.entry_timestamp_utc, "entry_timestamp_utc")

    def to_dict(self) -> dict[str, Any]:
        return {"pair": self.pair, "interval": self.interval, "direction": self.direction,
                "quantity": self.quantity, "plan_entry_price": self.plan_entry_price,
                "entry_price": self.entry_price,
                "stop_loss": self.stop_loss, "take_profit": self.take_profit,
                "entry_timestamp_utc": self.entry_timestamp_utc,
                "plan_timestamp_utc": self.plan_timestamp_utc, "entry_cost": self.entry_cost,
                "risk_amount": self.risk_amount}


@dataclass(frozen=True)
class PaperTrade:
    trade_id: str
    pair: str
    interval: str
    direction: str
    quantity: float
    plan_entry_price: float
    actual_entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    entry_timestamp_utc: str
    exit_timestamp_utc: str
    status: PaperTradeStatus
    gross_pnl: float
    entry_cost: float
    exit_cost: float
    net_pnl: float
    risk_amount: float
    r_multiple: float

    def to_dict(self) -> dict[str, Any]:
        result = {name: getattr(self, name) for name in self.__dataclass_fields__}
        result["status"] = self.status.value
        return result


@dataclass(frozen=True)
class PaperEvent:
    event_id: int
    event_type: PaperEventType
    timestamp_utc: str
    trade_id: str | None
    equity: float
    cash_equity: float
    price: float
    quantity: float
    realized_pnl: float
    unrealized_pnl: float
    reason: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "event_type": self.event_type.value,
                "timestamp_utc": self.timestamp_utc, "trade_id": self.trade_id,
                "equity": self.equity, "cash_equity": self.cash_equity, "price": self.price,
                "quantity": self.quantity, "realized_pnl": self.realized_pnl,
                "unrealized_pnl": self.unrealized_pnl, "reason": self.reason,
                "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class PaperTradingResult:
    initial_equity: float
    ending_equity: float
    realized_pnl: float
    total_costs: float
    max_drawdown_fraction: float
    trades: tuple[PaperTrade, ...]
    events: tuple[PaperEvent, ...]
    rejected_entries: int
    evidence_fingerprint: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def return_fraction(self) -> float:
        return (self.ending_equity - self.initial_equity) / self.initial_equity

    def to_dict(self) -> dict[str, Any]:
        return {"initial_equity": self.initial_equity, "ending_equity": self.ending_equity,
                "realized_pnl": self.realized_pnl, "total_costs": self.total_costs,
                "max_drawdown_fraction": self.max_drawdown_fraction,
                "return_fraction": self.return_fraction,
                "trades": [t.to_dict() for t in self.trades],
                "events": [e.to_dict() for e in self.events],
                "rejected_entries": self.rejected_entries,
                "evidence_fingerprint": self.evidence_fingerprint,
                "metadata": dict(self.metadata)}


PlanProvider = Callable[[Sequence[Mapping[str, Any]]], TradePlan | None]


class PaperTradingEngine:
    """Run deterministic paper trading against a supplied candle sequence."""

    def __init__(self, config: PaperTradingConfig | None = None,
                 friction: ExecutionFrictionModel | None = None) -> None:
        self.config = config or PaperTradingConfig()
        self.friction = friction or ExecutionFrictionModel(ExecutionFrictionConfig())

    def run(self, candles: Sequence[Mapping[str, Any]], plan_provider: PlanProvider) -> PaperTradingResult:
        if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)) or len(candles) < 2:
            raise PaperTradingError("at least two candles are required")
        if not callable(plan_provider):
            raise PaperTradingError("plan_provider must be callable")
        frames = list(candles[: self.config.max_bars] if self.config.max_bars else candles)
        parsed = [_candle(frame) for frame in frames]
        timestamps = [row[0] for row in parsed]
        timestamp_instants = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in timestamps]
        if timestamp_instants != sorted(timestamp_instants) or len(set(timestamp_instants)) != len(timestamp_instants):
            raise PaperTradingError("candle timestamps must be strictly chronological")

        equity = self.config.initial_equity
        peak = equity
        realized = 0.0
        costs = 0.0
        position: PaperPosition | None = None
        open_trade_id: str | None = None
        trades: list[PaperTrade] = []
        events: list[PaperEvent] = []
        rejected = 0
        event_id = 0

        def emit(kind: PaperEventType, i: int, price: float, qty: float, reason: str,
                 trade_id: str | None, unrealized: float = 0.0, metadata: Mapping[str, Any] | None = None) -> None:
            nonlocal event_id
            event_id += 1
            events.append(PaperEvent(event_id, kind, timestamps[i], trade_id, equity + unrealized,
                                     equity, price, qty, realized, unrealized, reason, dict(metadata or {})))

        def unrealized_at(pos: PaperPosition, price: float) -> float:
            return ((price - pos.entry_price) if pos.direction.upper() == "LONG" else (pos.entry_price - price)) * pos.quantity

        for i in range(len(parsed)):
            ts, open_, high, low, close = parsed[i]

            if position is not None:
                exit_kind: PaperTradeStatus | None = None
                market_exit: float | None = None
                if position.direction.upper() == "LONG":
                    hit_stop = low <= position.stop_loss
                    hit_target = high >= position.take_profit
                else:
                    hit_stop = high >= position.stop_loss
                    hit_target = low <= position.take_profit
                if hit_stop and hit_target:
                    if self.config.intrabar_policy is PaperIntrabarPolicy.TARGET_FIRST:
                        exit_kind, market_exit = PaperTradeStatus.TAKE_PROFIT, position.take_profit
                    elif self.config.intrabar_policy is PaperIntrabarPolicy.STOP_FIRST:
                        exit_kind, market_exit = PaperTradeStatus.STOP_LOSS, position.stop_loss
                    else:
                        exit_kind, market_exit = PaperTradeStatus.STOP_LOSS, position.stop_loss
                elif hit_stop:
                    exit_kind, market_exit = PaperTradeStatus.STOP_LOSS, position.stop_loss
                elif hit_target:
                    exit_kind, market_exit = PaperTradeStatus.TAKE_PROFIT, position.take_profit

                if exit_kind is not None and market_exit is not None:
                    side = PositionSide.LONG if position.direction.upper() == "LONG" else PositionSide.SHORT
                    fill = self.friction.fill(market_exit, position.quantity, side, is_entry=False)
                    gross = unrealized_at(position, fill.execution_price)
                    net = gross - position.entry_cost - fill.transaction_cost
                    equity += net
                    realized += net
                    costs += fill.transaction_cost
                    r = net / position.risk_amount if position.risk_amount > 0 else 0.0
                    trade = PaperTrade(open_trade_id or f"PAPER-{i}", position.pair, position.interval,
                                       position.direction, position.quantity, position.plan_entry_price,
                                       position.entry_price, position.stop_loss, position.take_profit,
                                       fill.execution_price, position.entry_timestamp_utc, ts, exit_kind,
                                       gross, position.entry_cost, fill.transaction_cost, net,
                                       position.risk_amount, r)
                    trades.append(trade)
                    emit(PaperEventType.EXIT, i, fill.execution_price, position.quantity, exit_kind.value,
                         trade.trade_id, 0.0, {"gross_pnl": gross, "net_pnl": net, "transaction_cost": fill.transaction_cost})
                    position = None
                    open_trade_id = None

            if position is not None and self.config.mark_to_market:
                unrealized = unrealized_at(position, close)
                emit(PaperEventType.MARK, i, close, position.quantity, "mark_to_market", open_trade_id, unrealized)
                peak = max(peak, equity + unrealized)
            else:
                peak = max(peak, equity)

            if i >= len(parsed) - 1 or not self.config.allow_new_entries or position is not None:
                continue

            # Crucial point-in-time boundary: provider sees candles [0..i],
            # but execution happens on candle i+1 open.
            plan = plan_provider(tuple(frames[: i + 1]))
            if plan is None:
                continue
            if not isinstance(plan, TradePlan):
                raise PaperTradingError("plan_provider must return TradePlan or None")
            if plan.pair.upper() != plan.pair:
                raise PaperTradingError("TradePlan pair must be normalized uppercase")
            next_ts, next_open, _, _, _ = parsed[i + 1]
            side = PositionSide.LONG if plan.direction.upper() == "LONG" else PositionSide.SHORT
            fill = self.friction.fill(next_open, plan.quantity, side, is_entry=True)
            if self.config.reject_if_friction_exceeds_planned_risk and fill.transaction_cost >= plan.risk_amount:
                rejected += 1
                emit(PaperEventType.REJECTED, i + 1, fill.execution_price, plan.quantity,
                     "entry_friction_exceeds_planned_risk", None,
                     metadata={"transaction_cost": fill.transaction_cost, "risk_amount": plan.risk_amount})
                continue

            position = PaperPosition(plan.pair, plan.interval, plan.direction, plan.quantity,
                                     plan.entry_price, fill.execution_price, plan.stop_loss, plan.take_profit,
                                     next_ts, plan.timestamp_utc, fill.transaction_cost, plan.risk_amount)
            open_trade_id = f"PAPER-{len(trades) + 1:06d}"
            costs += fill.transaction_cost
            emit(PaperEventType.ENTRY, i + 1, fill.execution_price, plan.quantity, "risk_approved_plan",
                 open_trade_id, 0.0, {"plan_entry_price": plan.entry_price,
                                      "planned_risk": plan.risk_amount,
                                      "transaction_cost": fill.transaction_cost})

        if position is not None:
            ts, _, _, _, close = parsed[-1]
            side = PositionSide.LONG if position.direction.upper() == "LONG" else PositionSide.SHORT
            fill = self.friction.fill(close, position.quantity, side, is_entry=False)
            gross = unrealized_at(position, fill.execution_price)
            net = gross - position.entry_cost - fill.transaction_cost
            equity += net
            realized += net
            costs += fill.transaction_cost + position.entry_cost
            r = net / position.risk_amount if position.risk_amount > 0 else 0.0
            trade = PaperTrade(open_trade_id or f"PAPER-{len(trades)+1:06d}", position.pair, position.interval,
                               position.direction, position.quantity, position.entry_price, position.entry_price,
                               position.stop_loss, position.take_profit, fill.execution_price,
                               position.entry_timestamp_utc, ts, PaperTradeStatus.END_OF_TEST, gross,
                               position.entry_cost, fill.transaction_cost, net, position.risk_amount, r)
            trades.append(trade)
            emit(PaperEventType.EXIT, len(parsed) - 1, fill.execution_price, position.quantity,
                 PaperTradeStatus.END_OF_TEST.value, trade.trade_id, 0.0,
                 {"gross_pnl": gross, "net_pnl": net, "transaction_cost": fill.transaction_cost})

        peak = max(peak, equity)
        # Reconstruct max drawdown from equity-bearing events plus final equity.
        running = self.config.initial_equity
        max_dd = 0.0
        for event in events:
            running = max(running, event.equity)
            if running > 0:
                max_dd = max(max_dd, (running - event.equity) / running)
        payload = {"initial_equity": self.config.initial_equity, "ending_equity": equity,
                   "realized_pnl": realized, "total_costs": costs,
                   "max_drawdown_fraction": max_dd,
                   "trades": [t.to_dict() for t in trades], "events": [e.to_dict() for e in events],
                   "rejected_entries": rejected, "config": self.config.to_dict(),
                   "friction": self.friction.describe()}
        return PaperTradingResult(self.config.initial_equity, equity, realized, costs, max_dd,
                                  tuple(trades), tuple(events), rejected, _fingerprint(payload),
                                  {"phase": "2.19", "research_only": True,
                                   "broker_access": False, "order_placement": False,
                                   "execution_authorization": False, "profitability_guarantee": False})


def run_paper_trading(candles: Sequence[Mapping[str, Any]], plan_provider: PlanProvider,
                      config: PaperTradingConfig | None = None,
                      friction: ExecutionFrictionModel | None = None) -> PaperTradingResult:
    """Functional wrapper for deterministic paper trading."""
    return PaperTradingEngine(config, friction).run(candles, plan_provider)
