"""Deterministic portfolio and exposure control boundary for APEX.

This module evaluates whether a proposed exposure can coexist with an existing
portfolio under explicitly configured limits. It is an assessment boundary,
not an execution authority, and has no broker or credential access.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


class PortfolioExposureStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_EXPOSURE = "INVALID_EXPOSURE"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    CONCENTRATION_EXCEEDED = "CONCENTRATION_EXCEEDED"
    CORRELATION_LIMIT_EXCEEDED = "CORRELATION_LIMIT_EXCEEDED"
    RISK_LIMIT_EXCEEDED = "RISK_LIMIT_EXCEEDED"


@dataclass(frozen=True)
class PortfolioPosition:
    trade_id: str
    symbol: str
    strategy_id: str
    risk_amount: float
    currency_exposure: Mapping[str, float]
    direction: str = "UNKNOWN"


@dataclass(frozen=True)
class ProposedExposure:
    trade_id: str
    symbol: str
    strategy_id: str
    risk_amount: float
    currency_exposure: Mapping[str, float]
    direction: str = "UNKNOWN"


@dataclass(frozen=True)
class PortfolioExposureCriteria:
    max_total_risk: float | None = None
    max_symbol_risk: float | None = None
    max_strategy_risk: float | None = None
    max_currency_abs_exposure: float | None = None
    max_correlated_risk: float | None = None
    minimum_correlation_for_cluster: float = 0.70
    max_concentration_ratio: float | None = None
    require_currency_exposure: bool = True
    require_risk_amount: bool = True
    require_correlation_data: bool = False


@dataclass(frozen=True)
class PortfolioExposureAssessment:
    status: PortfolioExposureStatus
    reasons: tuple[str, ...]
    current_total_risk: float
    projected_total_risk: float
    symbol_risk: float
    strategy_risk: float
    currency_exposure: Mapping[str, float]
    correlated_risk: float | None
    concentration_ratio: float | None
    criteria_fingerprint: str
    portfolio_fingerprint: str
    proposed_fingerprint: str
    assessment_fingerprint: str
    execution_authorized: bool = False


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
            return "<non_finite>"
        return value
    return value


def _fingerprint(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_mapping(values: Mapping[str, float], name: str) -> list[str]:
    reasons: list[str] = []
    for key, value in values.items():
        if not isinstance(key, str) or not key.strip():
            reasons.append(f"invalid_{name}_key")
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            reasons.append(f"invalid_{name}_value")
    return reasons


def _validate(criteria: PortfolioExposureCriteria, positions: Sequence[PortfolioPosition], proposed: ProposedExposure) -> list[str]:
    reasons: list[str] = []
    numeric_limits = {
        "max_total_risk": criteria.max_total_risk,
        "max_symbol_risk": criteria.max_symbol_risk,
        "max_strategy_risk": criteria.max_strategy_risk,
        "max_currency_abs_exposure": criteria.max_currency_abs_exposure,
        "max_correlated_risk": criteria.max_correlated_risk,
        "max_concentration_ratio": criteria.max_concentration_ratio,
    }
    for name, value in numeric_limits.items():
        if value is not None and (not math.isfinite(float(value)) or float(value) < 0):
            reasons.append(f"invalid_{name}")
    if not math.isfinite(criteria.minimum_correlation_for_cluster) or not 0 <= criteria.minimum_correlation_for_cluster <= 1:
        reasons.append("invalid_minimum_correlation")
    if proposed.risk_amount < 0 or not math.isfinite(proposed.risk_amount):
        reasons.append("invalid_proposed_risk_amount")
    if not proposed.trade_id.strip() or not proposed.symbol.strip() or not proposed.strategy_id.strip():
        reasons.append("missing_proposed_identity")
    reasons.extend(_validate_mapping(proposed.currency_exposure, "proposed_currency_exposure"))
    seen: set[str] = set()
    for position in positions:
        if not position.trade_id.strip() or position.trade_id in seen:
            reasons.append("invalid_or_duplicate_position_id")
        seen.add(position.trade_id)
        if not position.symbol.strip() or not position.strategy_id.strip():
            reasons.append("missing_position_identity")
        if position.risk_amount < 0 or not math.isfinite(position.risk_amount):
            reasons.append("invalid_position_risk_amount")
        reasons.extend(_validate_mapping(position.currency_exposure, "currency_exposure"))
    if criteria.require_currency_exposure and not proposed.currency_exposure:
        reasons.append("proposed_currency_exposure_missing")
    if criteria.require_risk_amount and proposed.risk_amount <= 0:
        reasons.append("proposed_risk_amount_missing")
    return sorted(set(reasons))


def _correlation_for(a: str, b: str, matrix: Mapping[str, Mapping[str, float]]) -> float | None:
    if a == b:
        return 1.0
    if a in matrix and b in matrix[a]:
        return float(matrix[a][b])
    if b in matrix and a in matrix[b]:
        return float(matrix[b][a])
    return None


def assess_portfolio_exposure(
    criteria: PortfolioExposureCriteria,
    positions: Sequence[PortfolioPosition],
    proposed: ProposedExposure,
    correlation_matrix: Mapping[str, Mapping[str, float]] | None = None,
) -> PortfolioExposureAssessment:
    """Assess aggregate exposure; never authorizes execution."""
    matrix = correlation_matrix or {}
    validation = _validate(criteria, positions, proposed)
    criteria_fp = _fingerprint(criteria)
    portfolio_fp = _fingerprint(tuple(positions))
    proposed_fp = _fingerprint(proposed)
    if validation:
        status = PortfolioExposureStatus.INVALID_EXPOSURE
        reasons = tuple(validation)
        current_total = sum(p.risk_amount for p in positions if math.isfinite(p.risk_amount))
        projected = current_total + proposed.risk_amount if math.isfinite(proposed.risk_amount) else current_total
        return _assessment(status, reasons, current_total, projected, 0.0, 0.0, {}, None, None, criteria_fp, portfolio_fp, proposed_fp)

    current_total = sum(p.risk_amount for p in positions)
    projected_total = current_total + proposed.risk_amount
    symbol_risk = sum(p.risk_amount for p in positions if p.symbol == proposed.symbol) + proposed.risk_amount
    strategy_risk = sum(p.risk_amount for p in positions if p.strategy_id == proposed.strategy_id) + proposed.risk_amount
    currency_exposure: dict[str, float] = {}
    for position in positions:
        for currency, value in position.currency_exposure.items():
            currency_exposure[currency] = currency_exposure.get(currency, 0.0) + float(value)
    for currency, value in proposed.currency_exposure.items():
        currency_exposure[currency] = currency_exposure.get(currency, 0.0) + float(value)

    reasons: list[str] = []
    if criteria.max_total_risk is not None and projected_total > criteria.max_total_risk:
        reasons.append("total_risk_limit_exceeded")
    if criteria.max_symbol_risk is not None and symbol_risk > criteria.max_symbol_risk:
        reasons.append("symbol_risk_limit_exceeded")
    if criteria.max_strategy_risk is not None and strategy_risk > criteria.max_strategy_risk:
        reasons.append("strategy_risk_limit_exceeded")
    if criteria.max_currency_abs_exposure is not None and any(abs(v) > criteria.max_currency_abs_exposure for v in currency_exposure.values()):
        reasons.append("currency_exposure_limit_exceeded")

    concentration = projected_total and proposed.risk_amount / projected_total or 0.0
    if criteria.max_concentration_ratio is not None and concentration > criteria.max_concentration_ratio:
        reasons.append("concentration_limit_exceeded")

    correlated_risk: float | None = None
    correlated_positions: list[PortfolioPosition] = []
    missing_corr = False
    for position in positions:
        corr = _correlation_for(position.symbol, proposed.symbol, matrix)
        if corr is None:
            missing_corr = True
        elif abs(corr) >= criteria.minimum_correlation_for_cluster:
            correlated_positions.append(position)
    if correlated_positions or (criteria.require_correlation_data and positions and missing_corr):
        correlated_risk = proposed.risk_amount + sum(p.risk_amount for p in correlated_positions)
    if criteria.require_correlation_data and positions and missing_corr:
        reasons.append("correlation_data_missing")
    elif criteria.max_correlated_risk is not None and correlated_risk is not None and correlated_risk > criteria.max_correlated_risk:
        reasons.append("correlated_risk_limit_exceeded")

    if any(r == "correlation_data_missing" for r in reasons):
        status = PortfolioExposureStatus.INSUFFICIENT_DATA
    elif "correlated_risk_limit_exceeded" in reasons:
        status = PortfolioExposureStatus.CORRELATION_LIMIT_EXCEEDED
    elif "total_risk_limit_exceeded" in reasons or "symbol_risk_limit_exceeded" in reasons or "strategy_risk_limit_exceeded" in reasons:
        status = PortfolioExposureStatus.RISK_LIMIT_EXCEEDED
    elif "currency_exposure_limit_exceeded" in reasons:
        status = PortfolioExposureStatus.LIMIT_EXCEEDED
    elif "concentration_limit_exceeded" in reasons:
        status = PortfolioExposureStatus.CONCENTRATION_EXCEEDED
    elif reasons:
        status = PortfolioExposureStatus.REJECTED
    else:
        status = PortfolioExposureStatus.APPROVED
        reasons = ["all_configured_portfolio_constraints_satisfied"]
    return _assessment(status, tuple(reasons), current_total, projected_total, symbol_risk, strategy_risk, currency_exposure, correlated_risk, concentration, criteria_fp, portfolio_fp, proposed_fp)


def _assessment(status, reasons, current_total, projected_total, symbol_risk, strategy_risk, currency_exposure, correlated_risk, concentration, criteria_fp, portfolio_fp, proposed_fp):
    fp = _fingerprint({"status": status.value, "reasons": reasons, "criteria": criteria_fp, "portfolio": portfolio_fp, "proposed": proposed_fp})
    return PortfolioExposureAssessment(status, tuple(reasons), current_total, projected_total, symbol_risk, strategy_risk, dict(sorted(currency_exposure.items())), correlated_risk, concentration, criteria_fp, portfolio_fp, proposed_fp, fp, False)


def portfolio_assessment_is_not_execution_authorization(assessment: PortfolioExposureAssessment) -> bool:
    return assessment.execution_authorized is False
