"""Phase 2.60 economic edge evaluation.

This module evaluates whether a declared opportunity has enough *observed*
economic evidence to be treated as a candidate edge.  It is conservative:
missing costs/risk are never zero, evidence classes are never mixed silently,
and an edge candidate is not a prediction, guarantee, or execution decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Iterable, Mapping

INVALID = "INVALID"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
EDGE_CANDIDATE = "EDGE_CANDIDATE"
EDGE_CANDIDATE_WITH_LIMITATIONS = "EDGE_CANDIDATE_WITH_LIMITATIONS"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _explicit_cost(record: Mapping[str, Any]) -> float | None:
    total = _finite(record.get("total_costs"))
    if total is not None and total >= 0:
        return total
    components = []
    for name in ("transaction_cost", "slippage_cost", "financing_cost"):
        value = _finite(record.get(name))
        if value is None or value < 0:
            return None
        components.append(value)
    return sum(components) if components else None


def _risk(record: Mapping[str, Any]) -> float | None:
    for name in ("risk_amount", "max_risk", "initial_risk"):
        value = _finite(record.get(name))
        if value is not None and value >= 0:
            return value
    return None


@dataclass(frozen=True)
class EconomicEdgeCriteria:
    """Fixed evaluation criteria; callers must declare them rather than optimize."""

    min_records: int = 30
    min_cost_coverage: float = 1.0
    min_risk_coverage: float = 1.0
    min_positive_net_fraction: float = 0.50
    min_net_expectancy: float = 0.0
    min_expectancy_to_risk: float = 0.0
    max_cost_to_gross_profit: float | None = 1.0
    require_oos_evidence: bool = True
    require_statistical_robustness: bool = True
    allowed_robustness_statuses: tuple[str, ...] = ("UNCERTAINTY_QUANTIFIED", "WITHIN_SAMPLE_STABILITY")
    allowed_oos_statuses: tuple[str, ...] = ("OOS_EVIDENCE", "OOS_STABILITY")

    def __post_init__(self) -> None:
        if isinstance(self.min_records, bool) or not isinstance(self.min_records, int) or self.min_records < 1:
            raise ValueError("min_records must be a positive integer")
        for name in ("min_cost_coverage", "min_risk_coverage", "min_positive_net_fraction"):
            value = _finite(getattr(self, name))
            if value is None or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        for name in ("min_net_expectancy", "min_expectancy_to_risk"):
            value = _finite(getattr(self, name))
            if value is None:
                raise ValueError(f"{name} must be finite")
        if self.max_cost_to_gross_profit is not None:
            value = _finite(self.max_cost_to_gross_profit)
            if value is None or value < 0:
                raise ValueError("max_cost_to_gross_profit must be non-negative or None")


@dataclass(frozen=True)
class EconomicEdgeSummary:
    evidence_class: str
    total_records: int
    economic_records: int
    risk_records: int
    winning_records: int
    losing_records: int
    breakeven_records: int
    positive_net_fraction: float | None
    total_realized_pnl: float
    total_explicit_costs: float
    total_net_pnl: float
    gross_profit: float
    gross_loss: float
    net_expectancy: float | None
    expectancy_to_risk: float | None
    cost_coverage: float
    risk_coverage: float
    cost_to_gross_profit: float | None
    oos_status: str | None
    statistical_status: str | None
    limitations: tuple[str, ...]
    evidence_fingerprint: str


@dataclass(frozen=True)
class EconomicEdgeResult:
    status: str
    summary: EconomicEdgeSummary | None
    limitations: tuple[str, ...]
    evaluation_fingerprint: str

    @property
    def edge_candidate(self) -> bool:
        return self.status in {EDGE_CANDIDATE, EDGE_CANDIDATE_WITH_LIMITATIONS}

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "edge_candidate": self.edge_candidate,
            "summary": self.summary.__dict__ if self.summary else None,
            "limitations": list(self.limitations),
            "evaluation_fingerprint": self.evaluation_fingerprint,
        }


def evaluate_economic_edge(
    evidence: Iterable[Mapping[str, Any]],
    *,
    evidence_class: str,
    criteria: EconomicEdgeCriteria | None = None,
    statistical_status: str | None = None,
    oos_status: str | None = None,
) -> EconomicEdgeResult:
    """Evaluate observed economic evidence without predicting or executing."""
    if not isinstance(evidence_class, str) or not evidence_class.strip():
        raise ValueError("evidence_class must be non-empty")
    c = criteria or EconomicEdgeCriteria()
    if not isinstance(c, EconomicEdgeCriteria):
        raise TypeError("criteria must be EconomicEdgeCriteria")
    records = [dict(r) for r in evidence if isinstance(r, Mapping)]
    class_name = evidence_class.strip()
    scoped = [r for r in records if _text(r.get("evidence_class")) == class_name]
    limitations: list[str] = []
    if not scoped:
        result = EconomicEdgeResult(INSUFFICIENT_EVIDENCE, None, ("no_evidence_for_declared_class",), "")
        return EconomicEdgeResult(result.status, result.summary, result.limitations, _fingerprint({"class": class_name, "criteria": c.__dict__, "records": []}))

    economic: list[tuple[Mapping[str, Any], float, float]] = []
    risk_records = 0
    for record in scoped:
        pnl = _finite(record.get("realized_pnl"))
        cost = _explicit_cost(record)
        risk = _risk(record)
        if pnl is not None and cost is not None:
            economic.append((record, pnl, cost))
        if risk is not None:
            risk_records += 1

    economic_count = len(economic)
    cost_coverage = economic_count / len(scoped)
    risk_coverage = risk_records / len(scoped)
    if cost_coverage < c.min_cost_coverage:
        limitations.append("cost_coverage_below_threshold")
    if risk_coverage < c.min_risk_coverage:
        limitations.append("risk_coverage_below_threshold")
    if economic_count < c.min_records:
        limitations.append("economic_sample_small")

    total_pnl = sum(pnl for _, pnl, _ in economic)
    total_costs = sum(cost for _, _, cost in economic)
    net_values = [pnl - cost for _, pnl, cost in economic]
    total_net = sum(net_values)
    wins = sum(value > 0 for value in net_values)
    losses = sum(value < 0 for value in net_values)
    breakeven = sum(value == 0 for value in net_values)
    positive_fraction = wins / economic_count if economic_count else None
    expectancy = total_net / economic_count if economic_count else None
    risk_values = [_risk(record) for record, _, _ in economic]
    priced_risk = [value for value in risk_values if value is not None and value > 0]
    expectancy_to_risk = expectancy / (sum(priced_risk) / len(priced_risk)) if expectancy is not None and priced_risk else None
    gross_profit = sum(max(pnl, 0.0) for _, pnl, _ in economic)
    gross_loss = sum(-min(pnl, 0.0) for _, pnl, _ in economic)
    cost_ratio = total_costs / gross_profit if gross_profit > 0 else None

    if c.require_oos_evidence:
        if oos_status is None:
            limitations.append("oos_status_missing")
        elif oos_status not in c.allowed_oos_statuses:
            limitations.append("oos_evidence_not_sufficient")
    if c.require_statistical_robustness:
        if statistical_status is None:
            limitations.append("statistical_status_missing")
        elif statistical_status not in c.allowed_robustness_statuses:
            limitations.append("statistical_robustness_not_sufficient")
    if positive_fraction is not None and positive_fraction < c.min_positive_net_fraction:
        limitations.append("positive_net_fraction_below_threshold")
    if expectancy is not None and expectancy < c.min_net_expectancy:
        limitations.append("net_expectancy_below_threshold")
    if expectancy_to_risk is not None and expectancy_to_risk < c.min_expectancy_to_risk:
        limitations.append("expectancy_to_risk_below_threshold")
    if c.max_cost_to_gross_profit is not None and cost_ratio is not None and cost_ratio > c.max_cost_to_gross_profit:
        limitations.append("cost_to_gross_profit_above_threshold")
    if c.max_cost_to_gross_profit is not None and gross_profit <= 0:
        limitations.append("no_gross_profit_for_cost_ratio")

    evidence_fingerprint = _fingerprint({
        "evidence_class": class_name,
        "records": sorted(scoped, key=lambda r: (str(r.get("trade_id", "")), str(r.get("timestamp", "")))),
        "criteria": c.__dict__,
        "oos_status": oos_status,
        "statistical_status": statistical_status,
    })
    summary = EconomicEdgeSummary(
        evidence_class=class_name,
        total_records=len(scoped),
        economic_records=economic_count,
        risk_records=risk_records,
        winning_records=wins,
        losing_records=losses,
        breakeven_records=breakeven,
        positive_net_fraction=positive_fraction,
        total_realized_pnl=total_pnl,
        total_explicit_costs=total_costs,
        total_net_pnl=total_net,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_expectancy=expectancy,
        expectancy_to_risk=expectancy_to_risk,
        cost_coverage=cost_coverage,
        risk_coverage=risk_coverage,
        cost_to_gross_profit=cost_ratio,
        oos_status=oos_status,
        statistical_status=statistical_status,
        limitations=tuple(dict.fromkeys(limitations)),
        evidence_fingerprint=evidence_fingerprint,
    )

    hard_invalid = False
    evidence_ready = (
        economic_count >= c.min_records
        and cost_coverage >= c.min_cost_coverage
        and risk_coverage >= c.min_risk_coverage
    )
    economic_positive = (
        expectancy is not None
        and expectancy >= c.min_net_expectancy
        and positive_fraction is not None
        and positive_fraction >= c.min_positive_net_fraction
        and (expectancy_to_risk is None or expectancy_to_risk >= c.min_expectancy_to_risk)
        and (c.max_cost_to_gross_profit is None or (cost_ratio is not None and cost_ratio <= c.max_cost_to_gross_profit))
    )
    validation_ready = (not c.require_oos_evidence or oos_status in c.allowed_oos_statuses) and (
        not c.require_statistical_robustness or statistical_status in c.allowed_robustness_statuses
    )

    if hard_invalid:
        status = INVALID
    elif not evidence_ready:
        status = INSUFFICIENT_EVIDENCE
    elif not economic_positive or not validation_ready:
        status = DESCRIPTIVE_ONLY
    elif limitations:
        status = EDGE_CANDIDATE_WITH_LIMITATIONS
    else:
        status = EDGE_CANDIDATE

    payload = summary.__dict__ | {"status": status}
    return EconomicEdgeResult(status, summary, summary.limitations, _fingerprint(payload))
