"""APEX / BENVIN Execution Gateway & Safety Boundary.

Phase 2.22

This module defines the provider-neutral boundary between a risk-approved
TradePlan and any future execution adapter.  It validates and fingerprints
execution requests but deliberately performs no broker/network/account I/O.

The default mode is DISABLED.  A result that is ready for an adapter is not
itself an order, broker authorization, or proof that an execution occurred.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Mapping

from .risk import RiskDecision, RiskStatus, TradePlan


class ExecutionGatewayError(ValueError):
    """Raised for invalid execution-gateway input."""


class ExecutionMode(str, Enum):
    DISABLED = "DISABLED"
    SIMULATION = "SIMULATION"
    PAPER = "PAPER"
    DEMO = "DEMO"
    LIVE = "LIVE"


class ExecutionStatus(str, Enum):
    REJECTED = "REJECTED"
    READY_FOR_ADAPTER = "READY_FOR_ADAPTER"
    DUPLICATE = "DUPLICATE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"


class ExecutionAdapterCapability(str, Enum):
    VALIDATION_ONLY = "VALIDATION_ONLY"
    SIMULATION = "SIMULATION"
    PAPER = "PAPER"
    DEMO = "DEMO"
    LIVE = "LIVE"


def _number(value: Any, name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ExecutionGatewayError(f"{name} must be finite numeric")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ExecutionGatewayError(f"{name} must be at least {minimum}")
    return result


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionGatewayError(f"{name} must be a non-empty string")
    return value.strip()


def _timestamp(value: Any, name: str) -> str | None:
    if value is None:
        return None
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionGatewayError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ExecutionGatewayError(f"{name} must include timezone information")
    return text


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ExecutionPolicy:
    """Deterministic safety policy for execution-gateway admission."""

    mode: ExecutionMode = ExecutionMode.DISABLED
    require_risk_approval: bool = True
    require_plan: bool = True
    require_positive_quantity: bool = True
    require_positive_risk: bool = True
    require_valid_geometry: bool = True
    require_timestamp: bool = True
    maximum_risk_fraction: float = 0.01
    maximum_total_risk_fraction: float = 0.02
    allow_duplicate_requests: bool = False
    require_explicit_adapter: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ExecutionMode):
            raise ExecutionGatewayError("mode must be an ExecutionMode")
        _number(self.maximum_risk_fraction, "maximum_risk_fraction", 0.0)
        _number(self.maximum_total_risk_fraction, "maximum_total_risk_fraction", 0.0)
        if self.maximum_risk_fraction > 1.0 or self.maximum_total_risk_fraction > 1.0:
            raise ExecutionGatewayError("risk fractions must not exceed 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "require_risk_approval": self.require_risk_approval,
            "require_plan": self.require_plan,
            "require_positive_quantity": self.require_positive_quantity,
            "require_positive_risk": self.require_positive_risk,
            "require_valid_geometry": self.require_valid_geometry,
            "require_timestamp": self.require_timestamp,
            "maximum_risk_fraction": self.maximum_risk_fraction,
            "maximum_total_risk_fraction": self.maximum_total_risk_fraction,
            "allow_duplicate_requests": self.allow_duplicate_requests,
            "require_explicit_adapter": self.require_explicit_adapter,
        }


@dataclass(frozen=True)
class ExecutionRequest:
    """Immutable request to evaluate a risk-approved TradePlan for execution."""

    request_id: str
    plan: TradePlan
    created_at_utc: str
    mode: ExecutionMode
    candidate_id: str | None = None
    source_evidence_fingerprint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.request_id, "request_id")
        _timestamp(self.created_at_utc, "created_at_utc")
        if not isinstance(self.plan, TradePlan):
            raise ExecutionGatewayError("plan must be a TradePlan")
        if not isinstance(self.mode, ExecutionMode):
            raise ExecutionGatewayError("mode must be an ExecutionMode")
        if self.candidate_id is not None:
            _text(self.candidate_id, "candidate_id")
        if self.source_evidence_fingerprint is not None:
            _text(self.source_evidence_fingerprint, "source_evidence_fingerprint")

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "plan": self.plan.to_dict(),
            "created_at_utc": self.created_at_utc,
            "mode": self.mode.value,
            "candidate_id": self.candidate_id,
            "source_evidence_fingerprint": self.source_evidence_fingerprint,
            "metadata": dict(self.metadata),
        }

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable result of gateway validation; never an execution receipt."""

    status: ExecutionStatus
    request_id: str
    mode: ExecutionMode
    request_fingerprint: str | None
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ready_for_adapter(self) -> bool:
        return self.status == ExecutionStatus.READY_FOR_ADAPTER

    @property
    def execution_authorized(self) -> bool:
        """Always false: this phase creates a safety boundary, not authority."""
        return False

    @property
    def broker_access(self) -> bool:
        return False

    @property
    def order_placed(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        result = {
            "success": self.ready_for_adapter,
            "market": "forex",
            "component": "execution_gateway",
            "status": self.status.value,
            "request_id": self.request_id,
            "mode": self.mode.value,
            "request_fingerprint": self.request_fingerprint,
            "ready_for_adapter": self.ready_for_adapter,
            "execution_authorized": False,
            "broker_access": False,
            "order_placed": False,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }
        if self.error is not None:
            result["error"] = self.error
        return result


class ExecutionGateway:
    """Validate and fingerprint execution requests without performing I/O."""

    def __init__(self, policy: ExecutionPolicy | None = None) -> None:
        self.policy = policy or ExecutionPolicy()
        self._seen: set[str] = set()

    def create_request(
        self,
        risk_decision: RiskDecision,
        *,
        request_id: str,
        created_at_utc: str,
        candidate_id: str | None = None,
        source_evidence_fingerprint: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ExecutionRequest:
        if not isinstance(risk_decision, RiskDecision):
            raise ExecutionGatewayError("risk_decision must be a RiskDecision")
        if self.policy.require_risk_approval and risk_decision.status is not RiskStatus.APPROVED:
            raise ExecutionGatewayError("execution request requires an approved RiskDecision")
        if self.policy.require_plan and risk_decision.plan is None:
            raise ExecutionGatewayError("execution request requires a TradePlan")
        assert risk_decision.plan is not None
        return ExecutionRequest(
            request_id=request_id,
            plan=risk_decision.plan,
            created_at_utc=created_at_utc,
            mode=self.policy.mode,
            candidate_id=candidate_id,
            source_evidence_fingerprint=source_evidence_fingerprint,
            metadata=dict(metadata or {}),
        )

    def validate(self, request: ExecutionRequest, *, total_risk_fraction: float | None = None,
                 adapter_capability: ExecutionAdapterCapability | None = None) -> ExecutionResult:
        try:
            if not isinstance(request, ExecutionRequest):
                raise ExecutionGatewayError("request must be an ExecutionRequest")
            reasons: list[str] = []
            warnings: list[str] = []
            plan = request.plan
            if request.mode is not self.policy.mode:
                reasons.append("request mode does not match gateway policy mode")
            if self.policy.mode is ExecutionMode.DISABLED:
                reasons.append("execution gateway is disabled")
            if self.policy.require_positive_quantity and plan.quantity <= 0:
                reasons.append("quantity must be positive")
            if self.policy.require_positive_risk and plan.risk_amount <= 0:
                reasons.append("risk amount must be positive")
            if self.policy.require_valid_geometry:
                if plan.direction.upper() == "LONG" and not (plan.stop_loss < plan.entry_price < plan.take_profit):
                    reasons.append("LONG price geometry is invalid")
                if plan.direction.upper() == "SHORT" and not (plan.take_profit < plan.entry_price < plan.stop_loss):
                    reasons.append("SHORT price geometry is invalid")
            if self.policy.require_timestamp:
                _timestamp(plan.timestamp_utc, "plan.timestamp_utc")
                _timestamp(request.created_at_utc, "request.created_at_utc")
            if plan.risk_fraction > self.policy.maximum_risk_fraction:
                reasons.append("per-trade risk fraction exceeds execution policy")
            if total_risk_fraction is not None:
                total = _number(total_risk_fraction, "total_risk_fraction", 0.0)
                if total > self.policy.maximum_total_risk_fraction:
                    reasons.append("total risk fraction exceeds execution policy")
            if self.policy.require_explicit_adapter and adapter_capability is None:
                reasons.append("no explicit execution adapter capability supplied")
            elif adapter_capability is not None:
                required = {
                    ExecutionMode.SIMULATION: ExecutionAdapterCapability.SIMULATION,
                    ExecutionMode.PAPER: ExecutionAdapterCapability.PAPER,
                    ExecutionMode.DEMO: ExecutionAdapterCapability.DEMO,
                    ExecutionMode.LIVE: ExecutionAdapterCapability.LIVE,
                    ExecutionMode.DISABLED: ExecutionAdapterCapability.VALIDATION_ONLY,
                }[request.mode]
                if adapter_capability not in (required, ExecutionAdapterCapability.VALIDATION_ONLY):
                    reasons.append("adapter capability does not match requested execution mode")
            fingerprint = request.fingerprint
            if fingerprint in self._seen and not self.policy.allow_duplicate_requests:
                return ExecutionResult(ExecutionStatus.DUPLICATE, request.request_id, request.mode, fingerprint,
                                        ("duplicate execution request fingerprint",), tuple(warnings),
                                        {"execution_authorization": False, "broker_access": False})
            if reasons:
                return ExecutionResult(ExecutionStatus.REJECTED, request.request_id, request.mode, fingerprint,
                                       tuple(reasons), tuple(warnings),
                                       {"execution_authorization": False, "broker_access": False})
            self._seen.add(fingerprint)
            warnings.append("gateway validation is not an execution authorization")
            return ExecutionResult(ExecutionStatus.READY_FOR_ADAPTER, request.request_id, request.mode, fingerprint,
                                   (), tuple(warnings),
                                   {"execution_authorization": False, "broker_access": False,
                                    "order_placed": False, "adapter_invocation": False})
        except ExecutionGatewayError as exc:
            return ExecutionResult(ExecutionStatus.INVALID_INPUT, getattr(request, "request_id", "INVALID"),
                                   getattr(request, "mode", self.policy.mode),
                                   None, (), (), {"execution_authorization": False}, str(exc))


def validate_execution(request: ExecutionRequest, *, policy: ExecutionPolicy | None = None,
                       total_risk_fraction: float | None = None,
                       adapter_capability: ExecutionAdapterCapability | None = None) -> ExecutionResult:
    """Functional wrapper for deterministic gateway validation."""
    return ExecutionGateway(policy).validate(request, total_risk_fraction=total_risk_fraction,
                                              adapter_capability=adapter_capability)
