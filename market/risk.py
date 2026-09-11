"""APEX / BENVIN Risk Management Foundation.

Phase 2.7

This module turns an already-approved trade opportunity into a deterministic,
risk-bounded trade plan.  It does not place orders, access brokers, or grant
execution authority.

Design goals:
    * capital preservation before opportunity capture
    * explicit, configurable risk budgets
    * deterministic stop/target validation
    * position sizing from monetary risk, not signal strength
    * aggregate exposure and loss controls
    * immutable, auditable outputs
    * no network or account I/O
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite, floor
from typing import Any, Mapping


class RiskManagementError(ValueError):
    """Raised when risk configuration or inputs are invalid."""


class RiskStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"
    ERROR = "ERROR"


class StopMethod(str, Enum):
    PRICE_DISTANCE = "PRICE_DISTANCE"
    FIXED_PIPS = "FIXED_PIPS"
    ATR_MULTIPLE = "ATR_MULTIPLE"


class TargetMethod(str, Enum):
    PRICE_DISTANCE = "PRICE_DISTANCE"
    FIXED_PIPS = "FIXED_PIPS"
    REWARD_RISK = "REWARD_RISK"


def _number(value: Any, name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RiskManagementError(f"{name} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise RiskManagementError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise RiskManagementError(f"{name} must be at least {minimum}")
    return result


def _fraction(value: Any, name: str, maximum: float = 1.0) -> float:
    result = _number(value, name, 0.0)
    if result > maximum:
        raise RiskManagementError(f"{name} must be at most {maximum}")
    return result


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RiskManagementError(f"{name} must be a non-empty string")
    return value.strip()


def _direction(value: Any) -> str:
    direction = getattr(value, "value", value)
    if not isinstance(direction, str):
        raise RiskManagementError("opportunity direction must be textual")
    direction = direction.strip().upper()
    if direction not in {"LONG", "SHORT"}:
        raise RiskManagementError("risk planning requires LONG or SHORT direction")
    return direction


def _round_step(quantity: float, step: float) -> float:
    if step <= 0:
        return quantity
    return floor(quantity / step + 1e-12) * step


@dataclass(frozen=True)
class RiskPolicy:
    """Capital and exposure guardrails for one risk assessment.

    Defaults are conservative engineering defaults, not claims of optimality.
    They are deliberately configurable so later research can test their
    economic effect rather than hard-coding a supposedly profitable setting.
    """

    default_risk_fraction: float = 0.005
    max_risk_fraction_per_trade: float = 0.01
    max_total_risk_fraction: float = 0.02
    max_daily_loss_fraction: float = 0.03
    max_drawdown_fraction: float = 0.10
    max_consecutive_losses: int = 3
    minimum_reward_risk: float = 1.5
    max_open_positions: int = 5
    max_position_units: float | None = None
    allow_zero_daily_loss_limit: bool = False

    def __post_init__(self) -> None:
        _fraction(self.default_risk_fraction, "default_risk_fraction")
        _fraction(self.max_risk_fraction_per_trade, "max_risk_fraction_per_trade")
        _fraction(self.max_total_risk_fraction, "max_total_risk_fraction")
        _fraction(self.max_daily_loss_fraction, "max_daily_loss_fraction")
        _fraction(self.max_drawdown_fraction, "max_drawdown_fraction")
        _number(self.minimum_reward_risk, "minimum_reward_risk", 0.0)
        if self.max_consecutive_losses < 0:
            raise RiskManagementError("max_consecutive_losses must be non-negative")
        if self.max_open_positions < 0:
            raise RiskManagementError("max_open_positions must be non-negative")
        if self.max_position_units is not None:
            _number(self.max_position_units, "max_position_units", 0.0)
        if not self.allow_zero_daily_loss_limit and self.max_daily_loss_fraction <= 0:
            raise RiskManagementError("max_daily_loss_fraction must be positive")
        if self.default_risk_fraction > self.max_risk_fraction_per_trade:
            raise RiskManagementError("default_risk_fraction cannot exceed per-trade maximum")
        if self.max_total_risk_fraction < self.max_risk_fraction_per_trade:
            raise RiskManagementError("max_total_risk_fraction cannot be below per-trade maximum")

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_risk_fraction": float(self.default_risk_fraction),
            "max_risk_fraction_per_trade": float(self.max_risk_fraction_per_trade),
            "max_total_risk_fraction": float(self.max_total_risk_fraction),
            "max_daily_loss_fraction": float(self.max_daily_loss_fraction),
            "max_drawdown_fraction": float(self.max_drawdown_fraction),
            "max_consecutive_losses": self.max_consecutive_losses,
            "minimum_reward_risk": float(self.minimum_reward_risk),
            "max_open_positions": self.max_open_positions,
            "max_position_units": self.max_position_units,
            "allow_zero_daily_loss_limit": self.allow_zero_daily_loss_limit,
        }


@dataclass(frozen=True)
class AccountSnapshot:
    """Point-in-time capital state supplied by a trusted caller."""

    equity: float
    peak_equity: float | None = None

    def __post_init__(self) -> None:
        _number(self.equity, "equity", 0.0)
        if self.equity <= 0:
            raise RiskManagementError("equity must be greater than zero")
        if self.peak_equity is not None:
            _number(self.peak_equity, "peak_equity", self.equity)

    @property
    def drawdown_fraction(self) -> float:
        peak = self.peak_equity if self.peak_equity is not None else self.equity
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - self.equity) / peak)

    def to_dict(self) -> dict[str, Any]:
        return {
            "equity": float(self.equity),
            "peak_equity": self.peak_equity,
            "drawdown_fraction": round(self.drawdown_fraction, 8),
        }


@dataclass(frozen=True)
class ExposureSnapshot:
    """Current portfolio/loss state supplied by a trusted caller."""

    open_risk_amount: float = 0.0
    daily_realized_pnl: float = 0.0
    open_positions: int = 0
    consecutive_losses: int = 0
    pair_risk_amount: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "open_risk_amount",
            "daily_realized_pnl",
            "pair_risk_amount",
        ):
            _number(getattr(self, name), name)
        for name in ("open_positions", "consecutive_losses"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RiskManagementError(f"{name} must be a non-negative integer")
        if self.open_risk_amount < 0:
            raise RiskManagementError("open_risk_amount must be non-negative")
        if self.pair_risk_amount < 0:
            raise RiskManagementError("pair_risk_amount must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "open_risk_amount": float(self.open_risk_amount),
            "daily_realized_pnl": float(self.daily_realized_pnl),
            "open_positions": self.open_positions,
            "consecutive_losses": self.consecutive_losses,
            "pair_risk_amount": float(self.pair_risk_amount),
        }


@dataclass(frozen=True)
class StopLossPolicy:
    """Deterministic stop-distance calculator."""

    method: StopMethod = StopMethod.FIXED_PIPS
    distance: float | None = None
    pips: float | None = None
    atr_multiple: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.method, StopMethod):
            raise RiskManagementError("method must be a StopMethod")
        if self.method == StopMethod.PRICE_DISTANCE:
            _number(self.distance, "distance", 0.0)
            if self.distance <= 0:
                raise RiskManagementError("distance must be greater than zero")
        elif self.method == StopMethod.FIXED_PIPS:
            _number(self.pips, "pips", 0.0)
            if self.pips <= 0:
                raise RiskManagementError("pips must be greater than zero")
        elif self.method == StopMethod.ATR_MULTIPLE:
            _number(self.atr_multiple, "atr_multiple", 0.0)
            if self.atr_multiple <= 0:
                raise RiskManagementError("atr_multiple must be greater than zero")

    def calculate(self, entry_price: float, *, pip_size: float | None = None, atr: float | None = None) -> float:
        entry = _number(entry_price, "entry_price", 0.0)
        if self.method == StopMethod.PRICE_DISTANCE:
            return float(self.distance)
        if self.method == StopMethod.FIXED_PIPS:
            size = _number(pip_size, "pip_size", 0.0)
            if size <= 0:
                raise RiskManagementError("pip_size must be greater than zero")
            return float(self.pips) * size
        atr_value = _number(atr, "atr", 0.0)
        if atr_value <= 0:
            raise RiskManagementError("atr must be greater than zero")
        return float(self.atr_multiple) * atr_value

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method.value,
            "distance": self.distance,
            "pips": self.pips,
            "atr_multiple": self.atr_multiple,
        }


@dataclass(frozen=True)
class TakeProfitPolicy:
    """Deterministic target-distance calculator."""

    method: TargetMethod = TargetMethod.REWARD_RISK
    distance: float | None = None
    pips: float | None = None
    reward_risk: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.method, TargetMethod):
            raise RiskManagementError("method must be a TargetMethod")
        if self.method == TargetMethod.PRICE_DISTANCE:
            _number(self.distance, "distance", 0.0)
            if self.distance <= 0:
                raise RiskManagementError("distance must be greater than zero")
        elif self.method == TargetMethod.FIXED_PIPS:
            _number(self.pips, "pips", 0.0)
            if self.pips <= 0:
                raise RiskManagementError("pips must be greater than zero")
        elif self.method == TargetMethod.REWARD_RISK:
            _number(self.reward_risk, "reward_risk", 0.0)
            if self.reward_risk <= 0:
                raise RiskManagementError("reward_risk must be greater than zero")

    def calculate(self, entry_price: float, stop_distance: float, *, pip_size: float | None = None) -> float:
        _number(entry_price, "entry_price", 0.0)
        _number(stop_distance, "stop_distance", 0.0)
        if stop_distance <= 0:
            raise RiskManagementError("stop_distance must be greater than zero")
        if self.method == TargetMethod.PRICE_DISTANCE:
            return float(self.distance)
        if self.method == TargetMethod.FIXED_PIPS:
            size = _number(pip_size, "pip_size", 0.0)
            if size <= 0:
                raise RiskManagementError("pip_size must be greater than zero")
            return float(self.pips) * size
        return stop_distance * float(self.reward_risk)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method.value,
            "distance": self.distance,
            "pips": self.pips,
            "reward_risk": self.reward_risk,
        }


@dataclass(frozen=True)
class TradePlan:
    """Immutable risk-approved plan.  It is not an execution instruction."""

    pair: str
    interval: str
    timestamp_utc: str | None
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_distance: float
    target_distance: float
    reward_risk: float
    quantity: float
    risk_amount: float
    risk_fraction: float
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.pair, "pair")
        _text(self.interval, "interval")
        _direction(self.direction)
        for name in (
            "entry_price",
            "stop_loss",
            "take_profit",
            "stop_distance",
            "target_distance",
            "reward_risk",
            "quantity",
            "risk_amount",
            "risk_fraction",
        ):
            _number(getattr(self, name), name, 0.0)
        if self.stop_distance <= 0 or self.target_distance <= 0:
            raise RiskManagementError("trade distances must be greater than zero")
        if self.quantity <= 0 or self.risk_amount <= 0:
            raise RiskManagementError("quantity and risk_amount must be greater than zero")

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": "forex",
            "plan": "risk_managed_trade",
            "pair": self.pair,
            "interval": self.interval,
            "timestamp_utc": self.timestamp_utc,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "stop_distance": self.stop_distance,
            "target_distance": self.target_distance,
            "reward_risk": round(self.reward_risk, 8),
            "quantity": self.quantity,
            "risk_amount": self.risk_amount,
            "risk_fraction": self.risk_fraction,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RiskDecision:
    """Immutable, auditable result of risk assessment."""

    status: RiskStatus
    pair: str
    interval: str
    timestamp_utc: str | None
    direction: str
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    plan: TradePlan | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def approved(self) -> bool:
        return self.status == RiskStatus.APPROVED

    def to_dict(self) -> dict[str, Any]:
        result = {
            "success": self.approved,
            "market": "forex",
            "analysis": "risk_management",
            "status": self.status.value,
            "pair": self.pair,
            "interval": self.interval,
            "timestamp_utc": self.timestamp_utc,
            "direction": self.direction,
            "approved": self.approved,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }
        if self.plan is not None:
            result["plan"] = self.plan.to_dict()
        if self.error is not None:
            result["error"] = self.error
        return result


def _opportunity_fields(opportunity: Any) -> tuple[str, str, str | None, str]:
    if opportunity is None:
        raise RiskManagementError("opportunity is required")
    pair = _text(getattr(opportunity, "pair", None), "opportunity pair").upper()
    interval = _text(getattr(opportunity, "interval", None), "opportunity interval")
    timestamp = getattr(opportunity, "timestamp_utc", None)
    if timestamp is not None:
        timestamp = _text(timestamp, "opportunity timestamp_utc")
    direction = _direction(getattr(opportunity, "direction", None))
    if not bool(getattr(opportunity, "is_candidate", False)):
        raise RiskManagementError("opportunity is not a candidate")
    return pair, interval, timestamp, direction


def _reject(pair: str, interval: str, timestamp: str | None, direction: str, reasons: list[str], warnings: list[str] | None = None) -> RiskDecision:
    return RiskDecision(
        status=RiskStatus.REJECTED,
        pair=pair,
        interval=interval,
        timestamp_utc=timestamp,
        direction=direction,
        reasons=tuple(reasons),
        warnings=tuple(warnings or []),
    )


def assess_risk(
    opportunity: Any,
    *,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    account: AccountSnapshot,
    exposure: ExposureSnapshot | None = None,
    policy: RiskPolicy | None = None,
    risk_fraction: float | None = None,
    value_per_price_unit: float = 1.0,
    quantity_step: float = 1.0,
    min_quantity: float = 0.0,
    max_quantity: float | None = None,
) -> RiskDecision:
    """Assess a candidate and create a risk-bounded plan when all controls pass.

    ``value_per_price_unit`` is deliberately supplied by the caller.  This
    prevents the foundation from silently assuming an account currency or
    inventing FX conversion rates.  A later valuation service can provide it.
    """
    pair = interval = "UNKNOWN"
    timestamp = None
    direction = "UNKNOWN"
    try:
        pair, interval, timestamp, direction = _opportunity_fields(opportunity)
        policy = policy or RiskPolicy()
        exposure = exposure or ExposureSnapshot()
        entry = _number(entry_price, "entry_price", 0.0)
        stop = _number(stop_loss, "stop_loss", 0.0)
        target = _number(take_profit, "take_profit", 0.0)
        value = _number(value_per_price_unit, "value_per_price_unit", 0.0)
        step = _number(quantity_step, "quantity_step", 0.0)
        minimum_quantity = _number(min_quantity, "min_quantity", 0.0)
        if value <= 0 or step <= 0:
            raise RiskManagementError("value_per_price_unit and quantity_step must be greater than zero")
        if max_quantity is not None:
            _number(max_quantity, "max_quantity", 0.0)

        if direction == "LONG":
            if not stop < entry:
                return _reject(pair, interval, timestamp, direction, ["LONG stop-loss must be below entry price"])
            if not target > entry:
                return _reject(pair, interval, timestamp, direction, ["LONG take-profit must be above entry price"])
        else:
            if not stop > entry:
                return _reject(pair, interval, timestamp, direction, ["SHORT stop-loss must be above entry price"])
            if not target < entry:
                return _reject(pair, interval, timestamp, direction, ["SHORT take-profit must be below entry price"])

        stop_distance = abs(entry - stop)
        target_distance = abs(target - entry)
        reward_risk = target_distance / stop_distance
        if reward_risk + 1e-12 < policy.minimum_reward_risk:
            return _reject(
                pair, interval, timestamp, direction,
                ["reward-to-risk ratio is below the configured minimum"],
            )

        requested_fraction = policy.default_risk_fraction if risk_fraction is None else _fraction(risk_fraction, "risk_fraction")
        if requested_fraction > policy.max_risk_fraction_per_trade:
            return _reject(pair, interval, timestamp, direction, ["requested risk fraction exceeds per-trade maximum"])

        equity = account.equity
        max_trade_risk = equity * requested_fraction
        risk_per_unit = stop_distance * value
        raw_quantity = max_trade_risk / risk_per_unit
        quantity = _round_step(raw_quantity, step)
        if max_quantity is not None:
            quantity = min(quantity, float(max_quantity))
            quantity = _round_step(quantity, step)
        if policy.max_position_units is not None:
            quantity = min(quantity, float(policy.max_position_units))
            quantity = _round_step(quantity, step)
        if quantity < minimum_quantity or quantity <= 0:
            return _reject(pair, interval, timestamp, direction, ["calculated position size is below the minimum quantity"])

        risk_amount = quantity * risk_per_unit
        actual_fraction = risk_amount / equity
        if actual_fraction > policy.max_risk_fraction_per_trade + 1e-12:
            return _reject(pair, interval, timestamp, direction, ["rounded position risk exceeds per-trade maximum"])

        projected_total_risk = exposure.open_risk_amount + risk_amount
        if projected_total_risk > equity * policy.max_total_risk_fraction + 1e-12:
            return _reject(pair, interval, timestamp, direction, ["projected total portfolio risk exceeds configured maximum"])

        daily_loss = max(0.0, -exposure.daily_realized_pnl)
        if daily_loss + risk_amount > equity * policy.max_daily_loss_fraction + 1e-12:
            return _reject(pair, interval, timestamp, direction, ["projected daily loss exceeds configured maximum"])

        if account.drawdown_fraction >= policy.max_drawdown_fraction:
            return _reject(pair, interval, timestamp, direction, ["account drawdown is at or above configured maximum"])

        if exposure.consecutive_losses >= policy.max_consecutive_losses:
            return _reject(pair, interval, timestamp, direction, ["consecutive-loss limit has been reached"])

        if exposure.open_positions >= policy.max_open_positions:
            return _reject(pair, interval, timestamp, direction, ["maximum open-position count has been reached"])

        warnings: list[str] = []
        if exposure.pair_risk_amount + risk_amount > equity * policy.max_total_risk_fraction + 1e-12:
            return _reject(pair, interval, timestamp, direction, ["pair exposure would exceed configured risk budget"])
        if quantity < raw_quantity:
            warnings.append("position size was rounded down to the configured quantity step")
        if policy.max_position_units is not None and quantity >= policy.max_position_units:
            warnings.append("position size is capped by max_position_units")
        warnings.append("risk approval is not execution authorization")

        plan = TradePlan(
            pair=pair,
            interval=interval,
            timestamp_utc=timestamp,
            direction=direction,
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
            stop_distance=stop_distance,
            target_distance=target_distance,
            reward_risk=reward_risk,
            quantity=quantity,
            risk_amount=risk_amount,
            risk_fraction=actual_fraction,
            warnings=tuple(warnings),
            metadata={
                "risk_method": "monetary_risk_over_stop_distance",
                "value_per_price_unit": value,
                "quantity_step": step,
                "requested_risk_fraction": requested_fraction,
                "minimum_reward_risk": policy.minimum_reward_risk,
            },
        )
        return RiskDecision(
            status=RiskStatus.APPROVED,
            pair=pair,
            interval=interval,
            timestamp_utc=timestamp,
            direction=direction,
            warnings=tuple(warnings),
            plan=plan,
            metadata={
                "controls": policy.to_dict(),
                "account": account.to_dict(),
                "exposure": exposure.to_dict(),
            },
        )
    except RiskManagementError:
        raise
    except Exception as exc:
        return RiskDecision(
            status=RiskStatus.ERROR,
            pair=pair,
            interval=interval,
            timestamp_utc=timestamp,
            direction=direction,
            reasons=("risk assessment failed unexpectedly",),
            error=str(exc),
        )


class RiskEngine:
    """Reusable deterministic facade around :func:`assess_risk`."""

    def __init__(self, policy: RiskPolicy | None = None):
        self.policy = policy or RiskPolicy()

    def assess(self, opportunity: Any, **kwargs: Any) -> RiskDecision:
        kwargs.setdefault("policy", self.policy)
        return assess_risk(opportunity, **kwargs)
