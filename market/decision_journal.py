"""Phase 2.68 immutable decision provenance and outcome journal.

The journal preserves the exact decision-time snapshot separately from later
outcome links. It is an evidence/provenance layer, not an execution authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Protocol


class JournalError(ValueError):
    """Raised when journal input violates the immutable contract."""


class DecisionJournalStatus(str, Enum):
    CREATED = "CREATED"
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class DecisionJournalEntry:
    """Immutable snapshot of what APEX knew at decision time."""

    decision_id: str
    candidate_id: str
    timestamp: str
    symbol: str
    timeframe: str
    strategy_id: str
    strategy_version: str
    market_fingerprint: str
    opportunity_fingerprint: str
    economic_edge_fingerprint: str
    eligibility_fingerprint: str
    portfolio_fingerprint: str
    risk_fingerprint: str
    monitoring_fingerprint: str
    degradation_fingerprint: str
    safety_fingerprint: str
    decision_fingerprint: str
    decision_status: str
    admission_status: str
    blocking_reasons: tuple[str, ...] = ()
    decision_context: Mapping[str, Any] | None = None
    criteria_versions: Mapping[str, str] | None = None


@dataclass(frozen=True)
class DecisionOutcomeLink:
    """Later outcome references; never mutates the original decision snapshot."""

    decision_id: str
    linked_at: str
    execution_request_id: str | None = None
    execution_outcome_id: str | None = None
    reconciliation_id: str | None = None
    forward_evidence_id: str | None = None
    final_outcome: str | None = None
    realized_pnl: float | None = None
    outcome_fingerprint: str = ""


@dataclass(frozen=True)
class DecisionJournalRecord:
    """Read model containing immutable decision data plus an optional outcome link."""

    entry: DecisionJournalEntry
    outcome: DecisionOutcomeLink | None = None


class DecisionJournalRepository(Protocol):
    def append(self, entry: DecisionJournalEntry) -> str: ...
    def get(self, decision_id: str) -> DecisionJournalRecord | None: ...
    def link_outcome(self, outcome: DecisionOutcomeLink) -> str: ...


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: _canonical(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, set):
        return sorted(_canonical(v) for v in value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise JournalError("non_finite_value")
    return value


def fingerprint(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_text(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise JournalError(f"missing_{field}")


def validate_entry(entry: DecisionJournalEntry) -> DecisionJournalEntry:
    for field in (
        "decision_id", "candidate_id", "timestamp", "symbol", "timeframe",
        "strategy_id", "strategy_version", "market_fingerprint",
        "opportunity_fingerprint", "economic_edge_fingerprint",
        "eligibility_fingerprint", "portfolio_fingerprint", "risk_fingerprint",
        "monitoring_fingerprint", "degradation_fingerprint", "safety_fingerprint",
        "decision_fingerprint", "decision_status", "admission_status",
    ):
        _require_text(getattr(entry, field), field)
    if any(not isinstance(reason, str) or not reason.strip() for reason in entry.blocking_reasons):
        raise JournalError("invalid_blocking_reasons")
    _canonical(entry.decision_context)
    _canonical(entry.criteria_versions)
    return entry


def validate_outcome(outcome: DecisionOutcomeLink) -> DecisionOutcomeLink:
    _require_text(outcome.decision_id, "decision_id")
    _require_text(outcome.linked_at, "linked_at")
    if outcome.realized_pnl is not None and (
        not isinstance(outcome.realized_pnl, (int, float))
        or isinstance(outcome.realized_pnl, bool)
        or not math.isfinite(float(outcome.realized_pnl))
    ):
        raise JournalError("invalid_realized_pnl")
    _canonical(outcome)
    expected = fingerprint(replace(outcome, outcome_fingerprint=""))
    if outcome.outcome_fingerprint and outcome.outcome_fingerprint != expected:
        raise JournalError("outcome_fingerprint_mismatch")
    return replace(outcome, outcome_fingerprint=expected)


class InMemoryDecisionJournal:
    """Deterministic test/local repository with append-only decision snapshots."""

    def __init__(self) -> None:
        self._entries: dict[str, DecisionJournalEntry] = {}
        self._outcomes: dict[str, DecisionOutcomeLink] = {}

    def append(self, entry: DecisionJournalEntry) -> str:
        entry = validate_entry(entry)
        if entry.decision_id in self._entries:
            existing = self._entries[entry.decision_id]
            if fingerprint(existing) != fingerprint(entry):
                raise JournalError("immutable_decision_conflict")
            return entry.decision_id
        self._entries[entry.decision_id] = entry
        return entry.decision_id

    def get(self, decision_id: str) -> DecisionJournalRecord | None:
        entry = self._entries.get(decision_id)
        if entry is None:
            return None
        return DecisionJournalRecord(entry=entry, outcome=self._outcomes.get(decision_id))

    def link_outcome(self, outcome: DecisionOutcomeLink) -> str:
        outcome = validate_outcome(outcome)
        if outcome.decision_id not in self._entries:
            raise JournalError("decision_not_found")
        existing = self._outcomes.get(outcome.decision_id)
        if existing is not None and fingerprint(existing) != fingerprint(outcome):
            raise JournalError("immutable_outcome_conflict")
        self._outcomes[outcome.decision_id] = outcome
        return outcome.decision_id


class MongoDecisionJournal:
    """MongoDB repository; decision documents are immutable and outcomes are separate."""

    def __init__(self, collection: Any, outcome_collection: Any | None = None) -> None:
        self.collection = collection
        if outcome_collection is not None:
            self.outcome_collection = outcome_collection
        else:
            database = getattr(collection, "database", None)
            if database is None:
                raise JournalError("outcome_collection_required")
            self.outcome_collection = database["decision_outcomes"]
        try:
            self.collection.create_index("_id", unique=True)
            self.outcome_collection.create_index("_id", unique=True)
        except Exception:
            # Index creation is operational setup; reads/writes remain explicit.
            pass

    def append(self, entry: DecisionJournalEntry) -> str:
        entry = validate_entry(entry)
        document = _canonical(entry)
        document["_id"] = entry.decision_id
        existing = self.collection.find_one({"_id": entry.decision_id})
        if existing is not None:
            existing.pop("_id", None)
            if fingerprint(existing) != fingerprint(document):
                raise JournalError("immutable_decision_conflict")
            return entry.decision_id
        self.collection.insert_one(document)
        return entry.decision_id

    def get(self, decision_id: str) -> DecisionJournalRecord | None:
        document = self.collection.find_one({"_id": decision_id})
        if document is None:
            return None
        document.pop("_id", None)
        entry = DecisionJournalEntry(**document)
        outcome = self.outcome_collection.find_one({"_id": decision_id})
        if outcome is not None:
            outcome.pop("_id", None)
            outcome = DecisionOutcomeLink(**outcome)
        return DecisionJournalRecord(entry=entry, outcome=outcome)

    def link_outcome(self, outcome: DecisionOutcomeLink) -> str:
        outcome = validate_outcome(outcome)
        if self.collection.find_one({"_id": outcome.decision_id}) is None:
            raise JournalError("decision_not_found")
        document = _canonical(outcome)
        document["_id"] = outcome.decision_id
        existing = self.outcome_collection.find_one({"_id": outcome.decision_id})
        if existing is not None:
            existing.pop("_id", None)
            if fingerprint(existing) != fingerprint(document):
                raise JournalError("immutable_outcome_conflict")
            return outcome.decision_id
        self.outcome_collection.insert_one(document)
        return outcome.decision_id
