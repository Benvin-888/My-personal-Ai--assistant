"""Phase 2.59 evidence-driven opportunity evaluation.

This module qualifies a point-in-time trading opportunity using declared market
context and previously observed evidence. It is deterministic, descriptive,
and read-only. It does not optimize strategies, predict returns, declare an
economic edge, authorize execution, or communicate with a broker.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Iterable, Mapping

INVALID = "INVALID"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
INCOMPLETE = "INCOMPLETE"
QUALIFIED = "QUALIFIED"
QUALIFIED_WITH_LIMITATIONS = "QUALIFIED_WITH_LIMITATIONS"

MISSING = "<missing>"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None
    return dt.astimezone(timezone.utc)


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OpportunityEvaluationCriteria:
    """Declared qualification rules; no parameter search or optimization."""

    min_relevant_evidence_records: int = 10
    require_evidence_class: bool = True
    require_cost_coverage: bool = True
    require_risk_coverage: bool = True
    require_regime: bool = True
    require_session: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.min_relevant_evidence_records, bool) or not isinstance(self.min_relevant_evidence_records, int):
            raise ValueError("min_relevant_evidence_records must be an integer")
        if self.min_relevant_evidence_records < 1:
            raise ValueError("min_relevant_evidence_records must be positive")


@dataclass(frozen=True)
class OpportunityContext:
    """Normalized point-in-time opportunity identity and market context."""

    timestamp: str
    symbol: str
    timeframe: str
    direction: str
    strategy_id: str
    strategy_version: str
    regime: str
    session: str
    evidence_class: str
    signal_timestamp: str | None
    context_timestamp: str | None


@dataclass(frozen=True)
class OpportunityEvidenceProfile:
    """Evidence relevance and completeness for one opportunity."""

    evidence_class: str
    total_evidence_records: int
    temporal_evidence_records: int
    relevant_evidence_records: int
    exact_strategy_records: int
    exact_market_records: int
    exact_regime_records: int
    exact_session_records: int
    cost_covered_records: int
    risk_covered_records: int
    cost_coverage: float | None
    risk_coverage: float | None
    relevant_sample_sufficient: bool
    economic_coverage_complete: bool
    risk_coverage_complete: bool
    evidence_fingerprint: str


@dataclass(frozen=True)
class OpportunityQualification:
    """Independent qualification dimensions; never an execution authorization."""

    signal_valid: bool
    point_in_time_valid: bool
    context_valid: bool
    evidence_valid: bool
    economic_valid: bool
    risk_valid: bool
    complete: bool
    status: str
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class TradeOpportunity:
    """Auditable opportunity contract with no broker or execution authority."""

    opportunity_id: str
    context: OpportunityContext
    evidence: OpportunityEvidenceProfile
    qualification: OpportunityQualification
    evidence_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "context": self.context.__dict__,
            "evidence": self.evidence.__dict__,
            "qualification": {
                **self.qualification.__dict__,
                "limitations": list(self.qualification.limitations),
            },
            "evidence_fingerprint": self.evidence_fingerprint,
        }


@dataclass(frozen=True)
class OpportunityEvaluationResult:
    """Deterministic result for one declared point-in-time opportunity."""

    status: str
    opportunity: TradeOpportunity | None
    limitations: tuple[str, ...]
    evaluation_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "opportunity": self.opportunity.to_dict() if self.opportunity else None,
            "limitations": list(self.limitations),
            "evaluation_fingerprint": self.evaluation_fingerprint,
        }


def _coverage(record: Mapping[str, Any], names: tuple[str, ...]) -> bool:
    for name in names:
        value = record.get(name)
        if isinstance(value, bool):
            if value:
                return True
        elif value is not None:
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if isfinite(number) and number >= 0:
                return True
    return False


def _record_matches(record: Mapping[str, Any], context: OpportunityContext) -> bool:
    return (
        _text(record.get("strategy_id")) == context.strategy_id
        and _text(record.get("strategy_version")) == context.strategy_version
        and _text(record.get("symbol")) == context.symbol
        and _text(record.get("timeframe")) == context.timeframe
        and _text(record.get("regime")) == context.regime
        and _text(record.get("session")) == context.session
    )


def _build_context(opportunity: Mapping[str, Any]) -> tuple[OpportunityContext | None, list[str]]:
    required = ("timestamp", "symbol", "timeframe", "direction", "strategy_id", "strategy_version")
    missing = [name for name in required if not _text(opportunity.get(name))]
    timestamp = _parse_timestamp(opportunity.get("timestamp"))
    if timestamp is None:
        missing.append("valid_timezone_aware_timestamp")
    regime = _text(opportunity.get("regime"))
    session = _text(opportunity.get("session"))
    evidence_class = _text(opportunity.get("evidence_class"))
    if not regime:
        missing.append("regime")
    if not session:
        missing.append("session")
    if not evidence_class:
        missing.append("evidence_class")
    signal_timestamp = opportunity.get("signal_timestamp")
    context_timestamp = opportunity.get("context_timestamp")
    if signal_timestamp is not None and _parse_timestamp(signal_timestamp) is None:
        missing.append("valid_signal_timestamp")
    if context_timestamp is not None and _parse_timestamp(context_timestamp) is None:
        missing.append("valid_context_timestamp")
    if missing:
        return None, list(dict.fromkeys(missing))
    return OpportunityContext(
        timestamp=timestamp.isoformat().replace("+00:00", "Z"),
        symbol=_text(opportunity["symbol"]) or MISSING,
        timeframe=_text(opportunity["timeframe"]) or MISSING,
        direction=_text(opportunity["direction"]) or MISSING,
        strategy_id=_text(opportunity["strategy_id"]) or MISSING,
        strategy_version=_text(opportunity["strategy_version"]) or MISSING,
        regime=regime or MISSING,
        session=session or MISSING,
        evidence_class=evidence_class or MISSING,
        signal_timestamp=_text(signal_timestamp),
        context_timestamp=_text(context_timestamp),
    ), []


def evaluate_opportunity(
    opportunity: Mapping[str, Any],
    evidence: Iterable[Mapping[str, Any]],
    *,
    criteria: OpportunityEvaluationCriteria | None = None,
) -> OpportunityEvaluationResult:
    """Evaluate one declared point-in-time opportunity against relevant evidence."""
    if not isinstance(opportunity, Mapping):
        raise TypeError("opportunity must be a mapping")
    c = criteria or OpportunityEvaluationCriteria()
    if not isinstance(c, OpportunityEvaluationCriteria):
        raise TypeError("criteria must be OpportunityEvaluationCriteria")
    context, context_errors = _build_context(opportunity)
    if context is None:
        qualification = OpportunityQualification(
            signal_valid=False,
            point_in_time_valid=False,
            context_valid=False,
            evidence_valid=False,
            economic_valid=False,
            risk_valid=False,
            complete=False,
            status=INVALID,
            limitations=tuple(context_errors),
        )
        payload = {"opportunity": dict(opportunity), "status": INVALID, "limitations": context_errors}
        return OpportunityEvaluationResult(INVALID, None, tuple(context_errors), _fingerprint(payload))

    now = _parse_timestamp(context.timestamp)
    signal_dt = _parse_timestamp(context.signal_timestamp) if context.signal_timestamp else None
    context_dt = _parse_timestamp(context.context_timestamp) if context.context_timestamp else None
    limitations: list[str] = []
    point_in_time_valid = True
    if signal_dt is not None and signal_dt > now:
        limitations.append("signal_timestamp_after_opportunity")
        point_in_time_valid = False
    if context_dt is not None and context_dt > now:
        limitations.append("context_timestamp_after_opportunity")
        point_in_time_valid = False

    records = [dict(item) for item in evidence if isinstance(item, Mapping)]
    total = len(records)
    temporal: list[Mapping[str, Any]] = []
    relevant: list[Mapping[str, Any]] = []
    exact_strategy = exact_market = exact_regime = exact_session = 0
    cost_count = risk_count = 0
    for record in records:
        record_class = _text(record.get("evidence_class"))
        if record_class != context.evidence_class:
            continue
        record_time = _parse_timestamp(record.get("timestamp"))
        if record_time is None:
            continue
        if record_time > now:
            continue
        temporal.append(record)
        if _text(record.get("strategy_id")) == context.strategy_id and _text(record.get("strategy_version")) == context.strategy_version:
            exact_strategy += 1
        if _text(record.get("symbol")) == context.symbol and _text(record.get("timeframe")) == context.timeframe:
            exact_market += 1
        if _text(record.get("regime")) == context.regime:
            exact_regime += 1
        if _text(record.get("session")) == context.session:
            exact_session += 1
        if _record_matches(record, context):
            relevant.append(record)
            if _coverage(record, ("total_costs", "transaction_cost", "slippage_cost", "financing_cost")):
                cost_count += 1
            if _coverage(record, ("risk_amount", "max_risk", "initial_risk")):
                risk_count += 1

    if not temporal:
        limitations.append("no_temporally_valid_evidence")
    if not relevant:
        limitations.append("no_exact_context_evidence")
    relevant_count = len(relevant)
    cost_coverage = cost_count / relevant_count if relevant_count else None
    risk_coverage = risk_count / relevant_count if relevant_count else None
    sample_sufficient = relevant_count >= c.min_relevant_evidence_records
    economic_complete = (not c.require_cost_coverage) or cost_count == relevant_count
    risk_complete = (not c.require_risk_coverage) or risk_count == relevant_count
    if not sample_sufficient and relevant_count:
        limitations.append("relevant_evidence_sample_small")
    if c.require_cost_coverage and not economic_complete:
        limitations.append("relevant_evidence_cost_coverage_incomplete")
    if c.require_risk_coverage and not risk_complete:
        limitations.append("relevant_evidence_risk_coverage_incomplete")
    if c.require_regime and not context.regime:
        limitations.append("regime_missing")
    if c.require_session and not context.session:
        limitations.append("session_missing")
    if c.require_evidence_class and not context.evidence_class:
        limitations.append("evidence_class_missing")

    evidence_valid = bool(relevant) and point_in_time_valid
    signal_valid = bool(context.strategy_id and context.strategy_version and context.direction)
    context_valid = bool(context.symbol and context.timeframe and context.regime and context.session)
    economic_valid = economic_complete
    risk_valid = risk_complete
    complete = all((signal_valid, point_in_time_valid, context_valid, evidence_valid, economic_valid, risk_valid, sample_sufficient))
    if not point_in_time_valid or not signal_valid or not context_valid:
        status = INVALID
    elif not relevant:
        status = INSUFFICIENT_EVIDENCE
    elif not sample_sufficient:
        status = QUALIFIED_WITH_LIMITATIONS
    elif not economic_valid or not risk_valid:
        status = QUALIFIED_WITH_LIMITATIONS
    else:
        status = QUALIFIED
    profile_payload = {
        "context": context.__dict__,
        "relevant": sorted(relevant, key=lambda r: (str(r.get("trade_id", "")), str(r.get("timestamp", "")))),
        "criteria": c.__dict__,
    }
    profile = OpportunityEvidenceProfile(
        evidence_class=context.evidence_class,
        total_evidence_records=total,
        temporal_evidence_records=len(temporal),
        relevant_evidence_records=relevant_count,
        exact_strategy_records=exact_strategy,
        exact_market_records=exact_market,
        exact_regime_records=exact_regime,
        exact_session_records=exact_session,
        cost_covered_records=cost_count,
        risk_covered_records=risk_count,
        cost_coverage=cost_coverage,
        risk_coverage=risk_coverage,
        relevant_sample_sufficient=sample_sufficient,
        economic_coverage_complete=economic_complete,
        risk_coverage_complete=risk_complete,
        evidence_fingerprint=_fingerprint(profile_payload),
    )
    qualification = OpportunityQualification(
        signal_valid=signal_valid,
        point_in_time_valid=point_in_time_valid,
        context_valid=context_valid,
        evidence_valid=evidence_valid,
        economic_valid=economic_valid,
        risk_valid=risk_valid,
        complete=complete,
        status=status,
        limitations=tuple(dict.fromkeys(limitations)),
    )
    opportunity_id = _text(opportunity.get("opportunity_id")) or _fingerprint({"context": context.__dict__, "evidence": profile.evidence_fingerprint})[:24]
    trade_opportunity = TradeOpportunity(opportunity_id, context, profile, qualification, profile.evidence_fingerprint)
    payload = trade_opportunity.to_dict()
    return OpportunityEvaluationResult(status, trade_opportunity, qualification.limitations, _fingerprint(payload))


def summarize_opportunity_evidence(query: Any, opportunity: Mapping[str, Any], filters: Mapping[str, Any] | None = None, *, criteria: OpportunityEvaluationCriteria | None = None) -> OpportunityEvaluationResult:
    """Read-only MongoDB query adapter for opportunity evaluation."""
    if not hasattr(query, "find"):
        raise TypeError("query must provide find(filters)")
    if filters is not None and not isinstance(filters, Mapping):
        raise TypeError("filters must be a mapping or None")
    return evaluate_opportunity(opportunity, query.find(filters), criteria=criteria)
