"""APEX / BENVIN Phase 2.27 - Controlled Demo Forward Trading.

A deliberately bounded orchestration layer for forward demo evidence.
It connects the existing risk/execution/Deriv/reconciliation boundaries without
creating autonomous trading. One controller instance can authorize at most one
explicitly confirmed demo purchase. Every successful purchase must be followed
by broker-side verification and reconciliation before it is considered a
verified forward-trading observation.

No live mode, portfolio optimization, signal generation, or unattended loop is
implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .broker_state import BrokerContractState, BrokerPositionStore, ReconciliationResult
from .deriv_demo import DerivContractSpec, DerivDemoConfig, DerivDemoExecutionAdapter, DerivDemoExecutionResult, DerivDemoStatus
from .deriv_demo_control import DerivDemoControlResult, DerivDemoControlSession, DemoControlStatus, DerivDemoControlWebSocketTransport
from .deriv_demo_verification import DemoExecutionVerificationResult, DerivDemoExecutionVerifier, DemoVerificationStatus
from .execution import ExecutionAdapterCapability, ExecutionGateway, ExecutionMode, ExecutionPolicy, ExecutionRequest


class DemoForwardError(ValueError):
    """Raised for invalid controlled-forward configuration or input."""


class DemoForwardStatus(str, Enum):
    READY = "READY"
    REJECTED = "REJECTED"
    PURCHASED = "PURCHASED"
    VERIFIED = "VERIFIED"
    RECONCILED = "RECONCILED"
    ALREADY_EXECUTED = "ALREADY_EXECUTED"
    API_ERROR = "API_ERROR"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class DemoForwardPolicy:
    """Hard bounds for a controlled demo-forward run."""

    require_explicit_confirmation: bool = True
    max_executions_per_controller: int = 1
    require_broker_verification: bool = True
    require_reconciliation: bool = True
    require_demo_mode: bool = True

    def __post_init__(self) -> None:
        if self.max_executions_per_controller < 1:
            raise DemoForwardError("max_executions_per_controller must be at least 1")
        if self.max_executions_per_controller != 1:
            raise DemoForwardError("Phase 2.27 intentionally permits exactly one execution per controller")


@dataclass(frozen=True)
class DemoForwardResult:
    status: DemoForwardStatus
    request_id: str
    contract_id: str | None = None
    execution: DerivDemoExecutionResult | None = None
    verification: DemoExecutionVerificationResult | None = None
    reconciliation: ReconciliationResult | None = None
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def live_execution(self) -> bool:
        return False

    @property
    def broker_confirmed(self) -> bool:
        return bool(self.reconciliation and self.reconciliation.safe_for_position_state)

    @property
    def forward_evidence_ready(self) -> bool:
        return (
            self.status is DemoForwardStatus.RECONCILED
            and self.verification is not None
            and self.verification.verified
            and self.broker_confirmed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "request_id": self.request_id,
            "contract_id": self.contract_id,
            "live_execution": False,
            "broker_confirmed": self.broker_confirmed,
            "forward_evidence_ready": self.forward_evidence_ready,
            "execution": self.execution.to_dict() if self.execution else None,
            "verification": self.verification.to_dict() if self.verification else None,
            "reconciliation": self.reconciliation.to_dict() if self.reconciliation else None,
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
        }


class ControlledDemoForwardTrader:
    """One-shot, explicitly confirmed Deriv demo-forward orchestrator.

    The caller supplies an already approved ``ExecutionRequest``. The trader
    never creates a strategy signal or a risk decision and never changes the
    execution gateway's safety policy. It merely connects the existing pieces:
    gateway validation -> demo adapter -> broker verification -> reconciliation.
    """

    def __init__(
        self,
        config: DerivDemoConfig,
        *,
        policy: DemoForwardPolicy | None = None,
        adapter: DerivDemoExecutionAdapter | None = None,
        verifier: DerivDemoExecutionVerifier | None = None,
        store: BrokerPositionStore | None = None,
        gateway: ExecutionGateway | None = None,
        control_session: DerivDemoControlSession | None = None,
    ) -> None:
        self.config = config
        self.policy = policy or DemoForwardPolicy()
        if self.policy.require_demo_mode and not config:
            raise DemoForwardError("demo configuration is required")
        if gateway is not None:
            self.gateway = gateway
        else:
            # Keep orchestration validation separate from the adapter's own
            # gateway instance so the same request is not mistaken for a
            # duplicate when the adapter performs its mandatory second check.
            self.gateway = ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO))
        self.adapter = adapter or DerivDemoExecutionAdapter(config, gateway=ExecutionGateway(ExecutionPolicy(mode=ExecutionMode.DEMO)))
        self.control_session = control_session or DerivDemoControlSession(config, transport=DerivDemoControlWebSocketTransport())
        self.verifier = verifier or DerivDemoExecutionVerifier(self.control_session)
        self.store = store or BrokerPositionStore()
        self._executions = 0

    @property
    def executions_used(self) -> int:
        return self._executions

    def execute_once(
        self,
        request: ExecutionRequest,
        contract: DerivContractSpec,
        *,
        confirm_purchase: bool = False,
        total_risk_fraction: float | None = None,
    ) -> DemoForwardResult:
        try:
            if not isinstance(request, ExecutionRequest):
                raise DemoForwardError("request must be an ExecutionRequest")
            if not isinstance(contract, DerivContractSpec):
                raise DemoForwardError("contract must be a DerivContractSpec")
            if self.policy.require_demo_mode and request.mode is not ExecutionMode.DEMO:
                return self._reject(request.request_id, "controlled forward trader accepts DEMO mode only")
            if self._executions >= self.policy.max_executions_per_controller:
                return DemoForwardResult(DemoForwardStatus.ALREADY_EXECUTED, request.request_id,
                                         reasons=("one-shot demo execution limit has already been used",))
            if self.policy.require_explicit_confirmation and not confirm_purchase:
                return self._reject(request.request_id, "explicit demo purchase confirmation is required")

            gateway_result = self.gateway.validate(
                request,
                total_risk_fraction=total_risk_fraction,
                adapter_capability=ExecutionAdapterCapability.DEMO,
            )
            if not gateway_result.ready_for_adapter:
                return self._reject(request.request_id, *gateway_result.reasons)

            self._executions += 1
            execution = self.adapter.execute(request, contract, total_risk_fraction=total_risk_fraction)
            if execution.status is not DerivDemoStatus.CONTRACT_PURCHASED or not execution.contract_id:
                return DemoForwardResult(
                    DemoForwardStatus.API_ERROR if execution.status is DerivDemoStatus.API_ERROR else DemoForwardStatus.REJECTED,
                    request.request_id,
                    execution=execution,
                    reasons=execution.reasons or ((execution.error,) if execution.error else ("demo execution did not complete",)),
                )

            verification = self.verifier.verify(execution_to_control_result(execution), contract,
                                           expected_contract_id=execution.contract_id)
            if self.policy.require_broker_verification and not verification.verified:
                return DemoForwardResult(DemoForwardStatus.REJECTED, request.request_id,
                                         contract_id=execution.contract_id, execution=execution,
                                         verification=verification,
                                         reasons=verification.reasons or ((verification.error,) if verification.error else ("broker verification failed",)))

            # Reconciliation uses the same broker-confirmed open-contract state.
            session = self.control_session
            if not session.websocket_url:
                connected = session.connect()
                if connected.status is not DemoControlStatus.CONNECTED:
                    return DemoForwardResult(DemoForwardStatus.API_ERROR, request.request_id, contract_id=execution.contract_id, execution=execution, verification=verification, reasons=connected.reasons or ((connected.error,) if connected.error else ("demo reconciliation session could not connect",)))
            from .deriv_reconciliation import DerivDemoReconciler
            reconciler = DerivDemoReconciler(session, store=self.store)
            reconciliation = reconciler.reconcile(execution.contract_id, expected=contract)
            if self.policy.require_reconciliation and not reconciliation.safe_for_position_state:
                return DemoForwardResult(DemoForwardStatus.REJECTED, request.request_id,
                                         contract_id=execution.contract_id, execution=execution,
                                         verification=verification, reconciliation=reconciliation,
                                         reasons=reconciliation.reasons or ("broker reconciliation failed",))
            return DemoForwardResult(DemoForwardStatus.RECONCILED, request.request_id,
                                     contract_id=execution.contract_id, execution=execution,
                                     verification=verification, reconciliation=reconciliation,
                                     metadata={"broker": "deriv", "account_mode": "demo", "live_execution": False})
        except DemoForwardError as exc:
            return DemoForwardResult(DemoForwardStatus.INVALID_INPUT, getattr(request, "request_id", "INVALID"), reasons=(str(exc),))
        except Exception as exc:
            return DemoForwardResult(DemoForwardStatus.API_ERROR, getattr(request, "request_id", "INVALID"), reasons=(str(exc),))

    @staticmethod
    def _reject(request_id: str, *reasons: str) -> DemoForwardResult:
        return DemoForwardResult(DemoForwardStatus.REJECTED, request_id, reasons=tuple(reasons))


def execution_to_control_result(execution: DerivDemoExecutionResult) -> DerivDemoControlResult:
    """Adapt the execution receipt to the Phase 2.24/2.25 verification model."""
    from .deriv_demo_control import DemoControlStatus
    if execution.status is not DerivDemoStatus.CONTRACT_PURCHASED:
        return DerivDemoControlResult(DemoControlStatus.REJECTED, reasons=execution.reasons)
    return DerivDemoControlResult(
        DemoControlStatus.PURCHASED,
        websocket_url_scoped_demo=True,
        proposal_id=execution.proposal.proposal_id if execution.proposal else None,
        ask_price=execution.proposal.ask_price if execution.proposal else None,
        contract_id=execution.contract_id,
        metadata={"broker": "deriv", "account_mode": "demo", "live_execution": False},
    )
