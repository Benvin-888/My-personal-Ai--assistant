"""Phase 2.61 forward-evidence contracts and deterministic lifecycle engine.

Read-only evidence layer. This module does not authorize or execute trades.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Mapping


FORWARD_EVIDENCE_CLASS = "forward"

DECISION_LOCKED = "DECISION_LOCKED"
EXECUTION_PENDING = "EXECUTION_PENDING"
EXECUTED = "EXECUTED"
RECONCILIATION_PENDING = "RECONCILIATION_PENDING"
OUTCOME_CONFIRMED = "OUTCOME_CONFIRMED"
REJECTED = "REJECTED"
EXECUTION_FAILED = "EXECUTION_FAILED"
RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(float(value))


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return _aware(value).astimezone(timezone.utc).isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _canonical(getattr(value, name))
            for name in value.__dataclass_fields__
            if name not in {"decision_fingerprint"}
        }
    if isinstance(value, Mapping):
        return {str(k): _canonical(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def _fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ForwardDecision:
    """Immutable point-in-time decision snapshot."""

    forward_evidence_id: str
    opportunity_id: str
    opportunity_fingerprint: str
    decision_timestamp: datetime
    symbol: str
    timeframe: str
    direction: str
    strategy_id: str
    strategy_version: str
    regime: str
    session: str
    opportunity_status: str
    economic_edge_status: str
    risk_amount: float | None = None
    intended_entry: float | None = None
    intended_exit: float | None = None
    intended_stop: float | None = None
    intended_target: float | None = None
    expected_reward_risk: float | None = None
    execution_mode: str = "OBSERVATION"
    evidence_class: str = FORWARD_EVIDENCE_CLASS
    decision_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _aware(self.decision_timestamp)
        required = {
            "forward_evidence_id": self.forward_evidence_id,
            "opportunity_id": self.opportunity_id,
            "opportunity_fingerprint": self.opportunity_fingerprint,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "regime": self.regime,
            "session": self.session,
        }
        if any(not isinstance(v, str) or not v.strip() for v in required.values()):
            raise ValueError("decision identity fields must be non-empty strings")
        if self.evidence_class != FORWARD_EVIDENCE_CLASS:
            raise ValueError("forward decision evidence_class must be 'forward'")
        for name in ("risk_amount", "intended_entry", "intended_exit", "intended_stop", "intended_target", "expected_reward_risk"):
            value = getattr(self, name)
            if value is not None and not _finite(value):
                raise ValueError(f"{name} must be finite when supplied")
        payload = {k: getattr(self, k) for k in self.__dataclass_fields__ if k not in {"decision_fingerprint"}}
        object.__setattr__(self, "decision_fingerprint", _fingerprint(payload))


@dataclass(frozen=True)
class ForwardOutcome:
    """Outcome observed after a locked forward decision."""

    outcome_timestamp: datetime
    status: str
    actual_entry: float | None = None
    actual_exit: float | None = None
    actual_fill_price: float | None = None
    slippage: float | None = None
    transaction_cost: float | None = None
    financing_cost: float | None = None
    realized_pnl: float | None = None
    reconciliation_status: str | None = None

    def __post_init__(self) -> None:
        _aware(self.outcome_timestamp)
        if not isinstance(self.status, str) or not self.status.strip():
            raise ValueError("outcome status is required")
        for name in (
            "actual_entry", "actual_exit", "actual_fill_price", "slippage",
            "transaction_cost", "financing_cost", "realized_pnl"
        ):
            value = getattr(self, name)
            if value is not None and not _finite(value):
                raise ValueError(f"{name} must be finite when supplied")


@dataclass(frozen=True)
class ForwardEvidence:
    """Immutable linkage between a point-in-time decision and later outcome."""

    decision: ForwardDecision
    lifecycle_status: str = DECISION_LOCKED
    outcome: ForwardOutcome | None = None
    outcome_fingerprint: str | None = None

    @property
    def evidence_class(self) -> str:
        return FORWARD_EVIDENCE_CLASS

    @property
    def forward_evidence_id(self) -> str:
        return self.decision.forward_evidence_id

    @property
    def evidence_fingerprint(self) -> str:
        payload = {
            "decision": self.decision.decision_fingerprint,
            "outcome": _canonical(self.outcome) if self.outcome else None,
            "lifecycle_status": self.lifecycle_status,
        }
        return _fingerprint(payload)

    def lock(self) -> "ForwardEvidence":
        return replace(self, lifecycle_status=DECISION_LOCKED)

    def mark_execution_pending(self) -> "ForwardEvidence":
        return replace(self, lifecycle_status=EXECUTION_PENDING)

    def record_execution(self, outcome: ForwardOutcome) -> "ForwardEvidence":
        if self.lifecycle_status not in {EXECUTION_PENDING, DECISION_LOCKED}:
            raise ValueError("execution can only be recorded from a pending or locked decision")
        return replace(self, lifecycle_status=EXECUTED, outcome=outcome)

    def mark_reconciliation_pending(self) -> "ForwardEvidence":
        if self.lifecycle_status != EXECUTED:
            raise ValueError("reconciliation requires an executed outcome")
        return replace(self, lifecycle_status=RECONCILIATION_PENDING)

    def confirm_outcome(self, outcome: ForwardOutcome | None = None) -> "ForwardEvidence":
        final_outcome = outcome or self.outcome
        if self.lifecycle_status not in {EXECUTED, RECONCILIATION_PENDING}:
            raise ValueError("outcome can only be confirmed after execution")
        if final_outcome is None:
            raise ValueError("confirmed outcome requires outcome data")
        return replace(self, lifecycle_status=OUTCOME_CONFIRMED, outcome=final_outcome)

    def terminal(self, status: str) -> "ForwardEvidence":
        if status not in {REJECTED, EXECUTION_FAILED, RECONCILIATION_FAILED, OUTCOME_UNKNOWN}:
            raise ValueError("invalid terminal status")
        return replace(self, lifecycle_status=status)


def create_forward_decision(**kwargs: Any) -> ForwardDecision:
    """Create a locked point-in-time forward decision."""
    return ForwardDecision(**kwargs)


def compare_forward_to_research(
    forward: Mapping[str, Any],
    research: Mapping[str, Any],
) -> dict[str, Any]:
    """Descriptively compare forward observations with prior research metrics.

    No significance test or profitability conclusion is inferred here.
    """
    result: dict[str, Any] = {"comparisons": {}, "limitations": []}
    for key in ("realized_pnl", "net_pnl", "expectancy", "win_rate", "profit_factor", "pnl_to_risk"):
        f = forward.get(key)
        r = research.get(key)
        if _finite(f) and _finite(r):
            result["comparisons"][key] = {"forward": float(f), "research": float(r), "difference": float(f) - float(r)}
        else:
            result["limitations"].append(f"{key}_comparison_unavailable")
    return result


__all__ = [
    "FORWARD_EVIDENCE_CLASS",
    "DECISION_LOCKED", "EXECUTION_PENDING", "EXECUTED",
    "RECONCILIATION_PENDING", "OUTCOME_CONFIRMED",
    "REJECTED", "EXECUTION_FAILED", "RECONCILIATION_FAILED", "OUTCOME_UNKNOWN",
    "ForwardDecision", "ForwardOutcome", "ForwardEvidence",
    "create_forward_decision", "compare_forward_to_research",
]
