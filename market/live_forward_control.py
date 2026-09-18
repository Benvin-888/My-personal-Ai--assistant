"""APEX / BENVIN Phase 2.39 - Controlled Live Forward Trading.

Phase 2.39 is the first orchestration layer allowed to take an already
risk-approved LIVE ExecutionRequest through the Phase 2.37 Deriv adapter and
Phase 2.38 broker reconciliation.

It is deliberately a controlled forward-evidence harness, not an autonomous
strategy runner.  It never creates signals, changes a TradePlan, sizes a trade,
or chooses a broker contract.  The caller must supply those approved artifacts.

The controller is fail-closed and one-shot by default.  It adds operational
quality gates (freshness, evidence identity, maximum stake, risk fraction, and
minimum reward/risk) and requires explicit per-execution confirmation.  A
successful controller result requires BOTH a CONFIRMED execution outcome and a
MATCHED broker reconciliation.  Unknown or mismatched broker state is never
reported as a successful trade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Mapping, Protocol

from .broker_state import ReconciliationStatus
from .deriv_demo import DerivContractSpec
from .deriv_live_execution import DerivLiveExecutionAdapter, DerivLiveExecutionConfig, DerivLiveExecutionResult
from .deriv_live_reconciliation import DerivLiveReconciler, DerivLiveReconciliationResult, DerivLiveReadOnlyWebSocketTransport
from .execution import ExecutionRequest, ExecutionMode
from .execution_outcome import ExecutionOutcomeStatus


class ControlledLiveForwardError(ValueError):
    """Raised for invalid controlled-forward configuration."""


class ControlledForwardStatus(str, Enum):
    READY = "READY"
    REJECTED = "REJECTED"
    EXECUTED_AND_RECONCILED = "EXECUTED_AND_RECONCILED"
    EXECUTED_UNVERIFIED = "EXECUTED_UNVERIFIED"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ControlledLiveForwardPolicy:
    """Hard operational limits for controlled real-account forward evidence."""

    enabled: bool = False
    require_explicit_confirmation: bool = True
    require_candidate_id: bool = True
    require_source_evidence_fingerprint: bool = True
    maximum_plan_age_seconds: float = 60.0
    maximum_stake: float = 10.0
    maximum_risk_fraction: float = 0.01
    minimum_reward_risk: float = 1.0
    maximum_trades_per_controller: int = 1
    require_reconciliation: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ControlledLiveForwardError("enabled must be boolean")
        if not isinstance(self.require_explicit_confirmation, bool):
            raise ControlledLiveForwardError("require_explicit_confirmation must be boolean")
        if not isinstance(self.require_candidate_id, bool):
            raise ControlledLiveForwardError("require_candidate_id must be boolean")
        if not isinstance(self.require_source_evidence_fingerprint, bool):
            raise ControlledLiveForwardError("require_source_evidence_fingerprint must be boolean")
        for name in ("maximum_plan_age_seconds", "maximum_stake", "maximum_risk_fraction", "minimum_reward_risk"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ControlledLiveForwardError(f"{name} must be finite numeric")
            if value < 0:
                raise ControlledLiveForwardError(f"{name} cannot be negative")
        if self.maximum_stake <= 0:
            raise ControlledLiveForwardError("maximum_stake must be positive")
        if self.maximum_risk_fraction <= 0:
            raise ControlledLiveForwardError("maximum_risk_fraction must be positive")
        if isinstance(self.maximum_trades_per_controller, bool) or not isinstance(self.maximum_trades_per_controller, int):
            raise ControlledLiveForwardError("maximum_trades_per_controller must be an integer")
        if self.maximum_trades_per_controller < 1:
            raise ControlledLiveForwardError("maximum_trades_per_controller must be at least 1")
        if not isinstance(self.require_reconciliation, bool):
            raise ControlledLiveForwardError("require_reconciliation must be boolean")

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "ControlledLiveForwardPolicy":
        import os
        env = os.environ if environ is None else environ
        return cls(
            enabled=env.get("APEX_LIVE_FORWARD_ENABLED", "").strip().lower() == "true",
            maximum_plan_age_seconds=float(env.get("APEX_LIVE_FORWARD_MAX_PLAN_AGE_SECONDS", "60")),
            maximum_stake=float(env.get("APEX_LIVE_FORWARD_MAX_STAKE", "10")),
            maximum_risk_fraction=float(env.get("APEX_LIVE_FORWARD_MAX_RISK_FRACTION", "0.01")),
            minimum_reward_risk=float(env.get("APEX_LIVE_FORWARD_MIN_REWARD_RISK", "1.0")),
            maximum_trades_per_controller=int(env.get("APEX_LIVE_FORWARD_MAX_TRADES", "1")),
        )

    def safe_summary(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "require_explicit_confirmation": self.require_explicit_confirmation,
            "require_candidate_id": self.require_candidate_id,
            "require_source_evidence_fingerprint": self.require_source_evidence_fingerprint,
            "maximum_plan_age_seconds": self.maximum_plan_age_seconds,
            "maximum_stake": self.maximum_stake,
            "maximum_risk_fraction": self.maximum_risk_fraction,
            "minimum_reward_risk": self.minimum_reward_risk,
            "maximum_trades_per_controller": self.maximum_trades_per_controller,
            "require_reconciliation": self.require_reconciliation,
            "credentials_exposed": False,
        }


@dataclass(frozen=True)
class ControlledLiveForwardResult:
    status: ControlledForwardStatus
    request_id: str
    execution: DerivLiveExecutionResult | None = None
    reconciliation: DerivLiveReconciliationResult | None = None
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def successful(self) -> bool:
        return (
            self.status is ControlledForwardStatus.EXECUTED_AND_RECONCILED
            and self.execution is not None
            and self.execution.outcome is not None
            and self.execution.outcome.status is ExecutionOutcomeStatus.CONFIRMED
            and self.reconciliation is not None
            and self.reconciliation.status is ReconciliationStatus.MATCHED
        )

    @property
    def live_trade_verified(self) -> bool:
        return self.successful

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.successful,
            "status": self.status.value,
            "request_id": self.request_id,
            "live_trade_verified": self.live_trade_verified,
            "execution": self.execution.to_dict() if self.execution else None,
            "reconciliation": self.reconciliation.to_dict() if self.reconciliation else None,
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
            "error": self.error,
            "credentials_exposed": False,
        }


class LiveExecutionRunner(Protocol):
    def execute(self, request: ExecutionRequest, contract: DerivContractSpec, *, total_risk_fraction: float | None = None, explicit_live_confirmation: bool = False) -> DerivLiveExecutionResult: ...


class LiveReconciliationRunner(Protocol):
    def reconcile(self, request: ExecutionRequest, outcome: Any, expected: DerivContractSpec) -> DerivLiveReconciliationResult: ...


class ControlledLiveForwardController:
    """Run at most the policy-defined number of explicitly confirmed trades."""

    def __init__(
        self,
        config: DerivLiveExecutionConfig,
        *,
        policy: ControlledLiveForwardPolicy | None = None,
        execution: LiveExecutionRunner | None = None,
        reconciliation: LiveReconciliationRunner | None = None,
        clock: callable | None = None,
    ) -> None:
        self.config = config
        self.policy = policy or ControlledLiveForwardPolicy()
        self.execution = execution or DerivLiveExecutionAdapter(config)
        self.reconciliation = reconciliation or DerivLiveReconciler(config, transport=DerivLiveReadOnlyWebSocketTransport())
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._executions = 0

    @property
    def executions_used(self) -> int:
        return self._executions

    def evaluate(
        self,
        request: ExecutionRequest,
        contract: DerivContractSpec,
        *,
        explicit_live_confirmation: bool = False,
    ) -> ControlledLiveForwardResult:
        try:
            self._validate(request, contract, explicit_live_confirmation)
        except ControlledLiveForwardError as exc:
            return ControlledLiveForwardResult(
                ControlledForwardStatus.REJECTED,
                getattr(request, "request_id", "INVALID"),
                reasons=(str(exc),),
                metadata={"controller_executed": False, "credentials_exposed": False},
            )

        self._executions += 1
        execution_result = self.execution.execute(
            request,
            contract,
            total_risk_fraction=request.plan.risk_fraction,
            explicit_live_confirmation=explicit_live_confirmation,
        )
        outcome = execution_result.outcome
        if outcome is None:
            status = ControlledForwardStatus.UNKNOWN if execution_result.status.value == "UNKNOWN" else ControlledForwardStatus.FAILED
            return ControlledLiveForwardResult(
                status,
                request.request_id,
                execution=execution_result,
                reasons=execution_result.reasons,
                metadata={"controller_executed": False, "reconciliation_required": self.policy.require_reconciliation},
                error=execution_result.error,
            )

        if outcome.status is not ExecutionOutcomeStatus.CONFIRMED:
            status = ControlledForwardStatus.UNKNOWN if outcome.status is ExecutionOutcomeStatus.UNKNOWN else ControlledForwardStatus.FAILED
            return ControlledLiveForwardResult(
                status,
                request.request_id,
                execution=execution_result,
                reasons=(outcome.message or outcome.status.value,),
                metadata={"controller_executed": True, "reconciliation_required": self.policy.require_reconciliation},
            )

        if not self.policy.require_reconciliation:
            return ControlledLiveForwardResult(
                ControlledForwardStatus.EXECUTED_UNVERIFIED,
                request.request_id,
                execution=execution_result,
                reasons=("broker reconciliation is required by the default safety policy",),
                metadata={"controller_executed": True, "broker_confirmed_but_not_reconciled": True},
            )

        reconciliation_result = self.reconciliation.reconcile(request, outcome, contract)
        if reconciliation_result.status is ReconciliationStatus.MATCHED:
            return ControlledLiveForwardResult(
                ControlledForwardStatus.EXECUTED_AND_RECONCILED,
                request.request_id,
                execution=execution_result,
                reconciliation=reconciliation_result,
                metadata={
                    "controller_executed": True,
                    "forward_evidence_eligible": True,
                    "broker_state_verified": True,
                },
            )

        status = ControlledForwardStatus.UNKNOWN if reconciliation_result.status is ReconciliationStatus.UNKNOWN else ControlledForwardStatus.EXECUTED_UNVERIFIED
        return ControlledLiveForwardResult(
            status,
            request.request_id,
            execution=execution_result,
            reconciliation=reconciliation_result,
            reasons=reconciliation_result.reasons,
            metadata={"controller_executed": True, "forward_evidence_eligible": False},
        )

    def _validate(self, request: ExecutionRequest, contract: DerivContractSpec, confirmation: bool) -> None:
        if not isinstance(request, ExecutionRequest):
            raise ControlledLiveForwardError("request must be an ExecutionRequest")
        if request.mode is not ExecutionMode.LIVE:
            raise ControlledLiveForwardError("controlled live forward trading accepts LIVE requests only")
        if not isinstance(contract, DerivContractSpec):
            raise ControlledLiveForwardError("contract must be a DerivContractSpec")
        if not self.policy.enabled:
            raise ControlledLiveForwardError("controlled live forward trading is disabled by policy")
        if self.config.account_id.strip() == "":
            raise ControlledLiveForwardError("real Deriv account must be configured")
        if self._executions >= self.policy.maximum_trades_per_controller:
            raise ControlledLiveForwardError("controller execution limit has already been reached")
        if self.policy.require_explicit_confirmation and not confirmation:
            raise ControlledLiveForwardError("explicit per-execution live confirmation is required")
        if self.policy.require_candidate_id and not request.candidate_id:
            raise ControlledLiveForwardError("candidate_id is required for forward evidence")
        if self.policy.require_source_evidence_fingerprint and not request.source_evidence_fingerprint:
            raise ControlledLiveForwardError("source_evidence_fingerprint is required for forward evidence")
        if contract.underlying_symbol != request.plan.pair:
            raise ControlledLiveForwardError("contract symbol must match TradePlan pair")
        if contract.amount <= 0 or contract.amount > self.policy.maximum_stake:
            raise ControlledLiveForwardError("contract stake exceeds controlled-forward maximum")
        if request.plan.risk_fraction > self.policy.maximum_risk_fraction:
            raise ControlledLiveForwardError("TradePlan risk fraction exceeds controlled-forward maximum")
        if request.plan.reward_risk < self.policy.minimum_reward_risk:
            raise ControlledLiveForwardError("TradePlan reward/risk is below controlled-forward minimum")
        self._validate_freshness(request)

    def _validate_freshness(self, request: ExecutionRequest) -> None:
        timestamp = request.plan.timestamp_utc or request.created_at_utc
        try:
            observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ControlledLiveForwardError("TradePlan timestamp must be ISO-8601") from exc
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        age = (self._clock() - observed).total_seconds()
        if age < -5:
            raise ControlledLiveForwardError("TradePlan timestamp is unexpectedly in the future")
        if age > self.policy.maximum_plan_age_seconds:
            raise ControlledLiveForwardError("TradePlan is too old for controlled live execution")


class _DefaultReconciliationTransport:
    """Bridge only for transports that expose a read-only request method."""

    def __init__(self, execution: Any) -> None:
        transport = getattr(execution, "transport", None)
        self._transport = transport

    def get_authenticated_websocket_url(self, config: DerivLiveExecutionConfig) -> str:
        method = getattr(self._transport, "get_authenticated_websocket_url", None)
        if not callable(method):
            raise ControlledLiveForwardError("execution transport does not expose reconciliation authentication")
        return method(config)

    def request(self, websocket_url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
        method = getattr(self._transport, "request", None)
        if not callable(method):
            raise ControlledLiveForwardError("execution transport does not expose a read-only request method")
        return method(websocket_url, payload, timeout)
