"""APEX / BENVIN deterministic execution-friction model.

Phase 2.5.5 - Transaction Costs, Spread & Slippage

This module models hypothetical execution friction for backtests only.
It contains no broker execution, live orders, leverage, or account mutation.

The model uses:
    * absolute spread in price units, applied as half-spread on each side;
    * absolute adverse slippage in price units per execution;
    * variable transaction cost per unit traded;
    * optional fixed transaction cost per execution.

All friction is deterministic and direction-aware.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from market.backtest.position import PositionSide


class ExecutionFrictionError(ValueError):
    """Raised when execution-friction configuration or inputs are invalid."""


@dataclass(frozen=True)
class ExecutionFrictionConfig:
    """Deterministic hypothetical execution-friction configuration."""

    spread: float = 0.0
    slippage: float = 0.0
    transaction_cost_per_unit: float = 0.0
    fixed_transaction_cost: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("spread", self.spread),
            ("slippage", self.slippage),
            ("transaction_cost_per_unit", self.transaction_cost_per_unit),
            ("fixed_transaction_cost", self.fixed_transaction_cost),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ExecutionFrictionError(f"{name} must be finite.")
            if value < 0:
                raise ExecutionFrictionError(f"{name} must be non-negative.")

    @property
    def half_spread(self) -> float:
        return float(self.spread) / 2.0

    def to_dict(self) -> dict:
        return {
            "spread": float(self.spread),
            "slippage": float(self.slippage),
            "transaction_cost_per_unit": float(self.transaction_cost_per_unit),
            "fixed_transaction_cost": float(self.fixed_transaction_cost),
        }


@dataclass(frozen=True)
class ExecutionFill:
    """A hypothetical execution price and its transaction cost."""

    market_price: float
    execution_price: float
    quantity: float
    side: PositionSide
    is_entry: bool
    transaction_cost: float

    def __post_init__(self) -> None:
        for name, value in (
            ("market_price", self.market_price),
            ("execution_price", self.execution_price),
            ("quantity", self.quantity),
            ("transaction_cost", self.transaction_cost),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ExecutionFrictionError(f"{name} must be finite.")
        if self.market_price <= 0 or self.execution_price <= 0:
            raise ExecutionFrictionError("market_price and execution_price must be positive.")
        if self.quantity <= 0:
            raise ExecutionFrictionError("quantity must be positive.")
        if self.side not in (PositionSide.LONG, PositionSide.SHORT):
            raise ExecutionFrictionError("side must be LONG or SHORT.")
        if self.transaction_cost < 0:
            raise ExecutionFrictionError("transaction_cost must be non-negative.")

    def to_dict(self) -> dict:
        return {
            "market_price": self.market_price,
            "execution_price": self.execution_price,
            "quantity": self.quantity,
            "side": self.side.value,
            "is_entry": self.is_entry,
            "transaction_cost": self.transaction_cost,
        }


class ExecutionFrictionModel:
    """Apply deterministic adverse spread/slippage and transaction costs."""

    def __init__(self, config: ExecutionFrictionConfig | None = None) -> None:
        self.config = config or ExecutionFrictionConfig()

    def fill(
        self,
        market_price: float,
        quantity: float,
        side: PositionSide,
        *,
        is_entry: bool,
    ) -> ExecutionFill:
        self._validate_price(market_price)
        self._validate_quantity(quantity)
        if side not in (PositionSide.LONG, PositionSide.SHORT):
            raise ExecutionFrictionError("side must be LONG or SHORT.")
        if not isinstance(is_entry, bool):
            raise ExecutionFrictionError("is_entry must be bool.")

        # Opening a long buys above market; closing a long sells below market.
        # Opening a short sells below market; closing a short buys above market.
        adverse = self.config.half_spread + self.config.slippage
        if side is PositionSide.LONG:
            execution_price = market_price + adverse if is_entry else market_price - adverse
        else:
            execution_price = market_price - adverse if is_entry else market_price + adverse

        if execution_price <= 0:
            raise ExecutionFrictionError("Execution price must remain positive.")

        cost = (
            self.config.transaction_cost_per_unit * float(quantity)
            + self.config.fixed_transaction_cost
        )
        return ExecutionFill(
            market_price=float(market_price),
            execution_price=float(execution_price),
            quantity=float(quantity),
            side=side,
            is_entry=is_entry,
            transaction_cost=float(cost),
        )

    @staticmethod
    def _validate_price(value: float) -> None:
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ExecutionFrictionError("market_price must be positive and finite.")

    @staticmethod
    def _validate_quantity(value: float) -> None:
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ExecutionFrictionError("quantity must be positive and finite.")

    def describe(self) -> dict:
        return {"model": "deterministic_execution_friction", "config": self.config.to_dict()}
