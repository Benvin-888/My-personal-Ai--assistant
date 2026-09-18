"""APEX / BENVIN strict execution-outcome contract.

Phase 2.36.2 introduces a provider-neutral result contract for future execution
adapters.  It does not connect to a broker and does not place orders.

The key rule is deliberate: adapter invocation is never equivalent to a
successful trade.  Only an explicit broker-confirmed outcome is considered
successful.  Submission without confirmation is non-successful, and an
ambiguous/unknown state is never converted into success.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping

from .execution import ExecutionMode, ExecutionRequest


class ExecutionOutcomeError(ValueError):
    """Raised when an execution adapter returns an invalid outcome."""


class ExecutionOutcomeStatus(str, Enum):
    REJECTED = "REJECTED"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


_TERMINAL = {
    ExecutionOutcomeStatus.REJECTED,
    ExecutionOutcomeStatus.CONFIRMED,
    ExecutionOutcomeStatus.FAILED,
}


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionOutcomeError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


def _number(value: Any, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExecutionOutcomeError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ExecutionOutcomeError(f"{name} must be finite")
    return result


@dataclass(frozen=True)
class ExecutionOutcome:
    """Strict, provider-neutral result returned by a future execution adapter.

    ``CONFIRMED`` is the only status for which ``successful`` is true.
    ``SUBMITTED`` deliberately means "accepted for processing" rather than
    "filled/confirmed".  ``UNKNOWN`` represents an uncertain broker state and
    must be reconciled before any later action is treated as successful.
    """

    request_id: str
    mode: ExecutionMode
    status: ExecutionOutcomeStatus
    broker: str
    account_scope: str
    broker_order_id: str | None = None
    execution_price: float | None = None
    executed_quantity: float | None = None
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.request_id, "request_id")
        if not isinstance(self.mode, ExecutionMode):
            raise ExecutionOutcomeError("mode must be an ExecutionMode")
        if not isinstance(self.status, ExecutionOutcomeStatus):
            raise ExecutionOutcomeError("status must be an ExecutionOutcomeStatus")
        _text(self.broker, "broker")
        _text(self.account_scope, "account_scope")
        _optional_text(self.broker_order_id, "broker_order_id")
        price = _number(self.execution_price, "execution_price")
        quantity = _number(self.executed_quantity, "executed_quantity")
        if price is not None and price <= 0:
            raise ExecutionOutcomeError("execution_price must be positive")
        if quantity is not None and quantity <= 0:
            raise ExecutionOutcomeError("executed_quantity must be positive")
        if not isinstance(self.message, str):
            raise ExecutionOutcomeError("message must be a string")
        if not isinstance(self.metadata, dict):
            raise ExecutionOutcomeError("metadata must be a dictionary")

        if self.status in {
            ExecutionOutcomeStatus.SUBMITTED,
            ExecutionOutcomeStatus.CONFIRMED,
        } and not self.broker_order_id:
            raise ExecutionOutcomeError(
                f"{self.status.value} outcome requires broker_order_id"
            )

        if self.status is ExecutionOutcomeStatus.CONFIRMED:
            if self.execution_price is None or self.executed_quantity is None:
                raise ExecutionOutcomeError(
                    "CONFIRMED outcome requires execution_price and executed_quantity"
                )

    @property
    def successful(self) -> bool:
        """True only when the broker-confirmed outcome is CONFIRMED."""
        return self.status is ExecutionOutcomeStatus.CONFIRMED

    @property
    def uncertain(self) -> bool:
        return self.status is ExecutionOutcomeStatus.UNKNOWN

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.successful,
            "component": "execution_outcome",
            "request_id": self.request_id,
            "mode": self.mode.value,
            "status": self.status.value,
            "broker": self.broker,
            "account_scope": self.account_scope,
            "broker_order_id": self.broker_order_id,
            "execution_price": self.execution_price,
            "executed_quantity": self.executed_quantity,
            "message": self.message,
            "metadata": dict(self.metadata),
            "successful": self.successful,
            "uncertain": self.uncertain,
            "terminal": self.terminal,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionOutcome":
        """Parse a strict adapter payload without treating missing fields as success."""
        if not isinstance(payload, Mapping):
            raise ExecutionOutcomeError("execution outcome must be a mapping")

        try:
            mode = ExecutionMode(payload.get("mode"))
            status = ExecutionOutcomeStatus(payload.get("status"))
        except (ValueError, TypeError) as exc:
            raise ExecutionOutcomeError("mode and status must be valid execution enum values") from exc

        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ExecutionOutcomeError("metadata must be a dictionary")

        return cls(
            request_id=payload.get("request_id"),
            mode=mode,
            status=status,
            broker=payload.get("broker"),
            account_scope=payload.get("account_scope"),
            broker_order_id=payload.get("broker_order_id"),
            execution_price=payload.get("execution_price"),
            executed_quantity=payload.get("executed_quantity"),
            message=payload.get("message", ""),
            metadata=dict(metadata),
        )


def validate_execution_outcome(
    request: ExecutionRequest,
    outcome: ExecutionOutcome,
) -> ExecutionOutcome:
    """Validate that an adapter outcome belongs to the request and mode.

    This function performs no broker I/O.  It rejects cross-request, cross-mode,
    and malformed results before they can be interpreted by higher layers.
    """
    if not isinstance(request, ExecutionRequest):
        raise ExecutionOutcomeError("request must be an ExecutionRequest")
    if not isinstance(outcome, ExecutionOutcome):
        raise ExecutionOutcomeError("outcome must be an ExecutionOutcome")
    if outcome.request_id != request.request_id:
        raise ExecutionOutcomeError("execution outcome request_id does not match request")
    if outcome.mode is not request.mode:
        raise ExecutionOutcomeError("execution outcome mode does not match request mode")
    return outcome
