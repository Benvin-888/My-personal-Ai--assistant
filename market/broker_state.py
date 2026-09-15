"""APEX / BENVIN Phase 2.26 - Broker Reconciliation & Position State.

Provider-neutral state model for broker-confirmed demo positions/contracts.
This module contains no network I/O and never places, modifies, or closes orders.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class BrokerStateError(ValueError):
    """Raised for invalid broker-state input."""


class PositionLifecycle(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"
    MISSING = "MISSING"


class ReconciliationStatus(str, Enum):
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class BrokerContractState:
    broker: str
    account_mode: str
    contract_id: str
    contract_type: str | None = None
    symbol: str | None = None
    currency: str | None = None
    buy_price: float | None = None
    payout: float | None = None
    is_sold: bool | None = None
    lifecycle: PositionLifecycle = PositionLifecycle.UNKNOWN
    observed_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("broker", "account_mode", "contract_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise BrokerStateError(f"{name} must be non-empty")
        if self.buy_price is not None and self.buy_price < 0:
            raise BrokerStateError("buy_price cannot be negative")
        if self.payout is not None and self.payout < 0:
            raise BrokerStateError("payout cannot be negative")

    @property
    def live(self) -> bool:
        return self.account_mode.lower() == "live"

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker": self.broker,
            "account_mode": self.account_mode,
            "contract_id": self.contract_id,
            "contract_type": self.contract_type,
            "symbol": self.symbol,
            "currency": self.currency,
            "buy_price": self.buy_price,
            "payout": self.payout,
            "is_sold": self.is_sold,
            "lifecycle": self.lifecycle.value,
            "observed_at": self.observed_at,
            "live": self.live,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class ReconciliationResult:
    status: ReconciliationStatus
    contract_id: str
    reasons: tuple[str, ...] = ()
    state: BrokerContractState | None = None
    expected: dict[str, Any] = field(default_factory=dict)

    @property
    def matched(self) -> bool:
        return self.status is ReconciliationStatus.MATCHED

    @property
    def safe_for_position_state(self) -> bool:
        return self.status is ReconciliationStatus.MATCHED and self.state is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "contract_id": self.contract_id,
            "matched": self.matched,
            "safe_for_position_state": self.safe_for_position_state,
            "reasons": list(self.reasons),
            "state": self.state.to_dict() if self.state else None,
            "expected": dict(self.expected),
        }


class BrokerPositionStore:
    """Small deterministic in-memory position state store.

    State is replaced only by broker-confirmed reconciliation results. Unknown
    or mismatched observations are never promoted into the authoritative state.
    """

    def __init__(self) -> None:
        self._states: dict[tuple[str, str, str], BrokerContractState] = {}

    def apply(self, result: ReconciliationResult) -> bool:
        if not isinstance(result, ReconciliationResult):
            raise BrokerStateError("result must be a ReconciliationResult")
        if not result.safe_for_position_state:
            return False
        state = result.state
        assert state is not None
        self._states[(state.broker, state.account_mode, state.contract_id)] = state
        return True

    def get(self, broker: str, account_mode: str, contract_id: str) -> BrokerContractState | None:
        return self._states.get((broker, account_mode, str(contract_id)))

    def all(self) -> tuple[BrokerContractState, ...]:
        return tuple(self._states.values())

    def open_positions(self) -> tuple[BrokerContractState, ...]:
        return tuple(s for s in self._states.values() if s.lifecycle is PositionLifecycle.OPEN)

    def clear(self) -> None:
        self._states.clear()
