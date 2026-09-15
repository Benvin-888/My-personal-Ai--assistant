"""APEX / BENVIN Phase 2.26 - Deriv demo broker reconciliation.

Reads broker-confirmed contract state and reconciles it against the expected
APEX contract. It is deliberately read-only: no buy/sell/modify/cancel path
exists in this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .broker_state import (
    BrokerContractState,
    BrokerPositionStore,
    ReconciliationResult,
    ReconciliationStatus,
    PositionLifecycle,
)
from .deriv_demo import DerivContractSpec
from .deriv_demo_control import DerivDemoControlSession


class DerivReconciliationError(ValueError):
    """Raised for invalid reconciliation input."""


class DerivDemoReconciler:
    """Read-only reconciliation against Deriv ``proposal_open_contract``."""

    broker = "deriv"
    account_mode = "demo"

    def __init__(self, session: DerivDemoControlSession, *, store: BrokerPositionStore | None = None) -> None:
        self.session = session
        self.store = store or BrokerPositionStore()

    def reconcile(self, contract_id: str, expected: DerivContractSpec | None = None) -> ReconciliationResult:
        contract_id = str(contract_id).strip()
        if not contract_id:
            return ReconciliationResult(ReconciliationStatus.INVALID_INPUT, contract_id="", reasons=("contract_id is required",))
        if not self.session.websocket_url:
            return ReconciliationResult(ReconciliationStatus.UNKNOWN, contract_id=contract_id,
                                        reasons=("demo session is not connected",))
        try:
            raw_response = self.session.transport.request(
                self.session.websocket_url,
                {"proposal_open_contract": 1, "contract_id": int(contract_id) if contract_id.isdigit() else contract_id},
                self.session.config.timeout_seconds,
            )
            if raw_response.get("error"):
                return ReconciliationResult(ReconciliationStatus.UNKNOWN, contract_id=contract_id,
                                            reasons=(str((raw_response.get("error") or {}).get("message", "Deriv error")),))
            payload = raw_response.get("proposal_open_contract")
            if not isinstance(payload, Mapping):
                return ReconciliationResult(ReconciliationStatus.UNKNOWN, contract_id=contract_id,
                                            reasons=("broker did not return proposal_open_contract",))
            returned_id = str(payload.get("contract_id", ""))
            if returned_id != contract_id:
                return ReconciliationResult(ReconciliationStatus.MISMATCH, contract_id=contract_id,
                                            reasons=("broker contract_id does not match requested contract_id",),
                                            expected={"contract_id": contract_id})
            state = self._parse_state(payload)
            reasons: list[str] = []
            if expected is not None:
                if state.contract_type is not None and state.contract_type != expected.contract_type:
                    reasons.append("contract_type mismatch")
                if state.currency is not None and state.currency != expected.currency:
                    reasons.append("currency mismatch")
                if state.buy_price is not None and state.buy_price > expected.amount:
                    # This is not a semantic amount/price equivalence check; it is
                    # intentionally not treated as mismatch because Deriv's price
                    # and APEX amount can have different meanings.
                    pass
            if reasons:
                return ReconciliationResult(ReconciliationStatus.MISMATCH, contract_id=contract_id,
                                            reasons=tuple(reasons), state=state,
                                            expected=_expected_dict(expected))
            result = ReconciliationResult(ReconciliationStatus.MATCHED, contract_id=contract_id,
                                          state=state, expected=_expected_dict(expected))
            self.store.apply(result)
            return result
        except Exception as exc:
            return ReconciliationResult(ReconciliationStatus.UNKNOWN, contract_id=contract_id,
                                        reasons=(f"reconciliation failed: {exc}",))

    @staticmethod
    def _parse_state(payload: Mapping[str, Any]) -> BrokerContractState:
        sold = payload.get("is_sold")
        lifecycle = PositionLifecycle.CLOSED if bool(sold) else PositionLifecycle.OPEN if sold is not None else PositionLifecycle.UNKNOWN
        return BrokerContractState(
            broker="deriv",
            account_mode="demo",
            contract_id=str(payload.get("contract_id")),
            contract_type=_optional_str(payload.get("contract_type")),
            symbol=_optional_str(payload.get("underlying_symbol") or payload.get("symbol")),
            currency=_optional_str(payload.get("currency")),
            buy_price=_optional_float(payload.get("buy_price")),
            payout=_optional_float(payload.get("payout")),
            is_sold=bool(sold) if sold is not None else None,
            lifecycle=lifecycle,
            observed_at=datetime.now(timezone.utc).isoformat(),
            raw=dict(payload),
        )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _expected_dict(contract: DerivContractSpec | None) -> dict[str, Any]:
    if contract is None:
        return {}
    return {
        "underlying_symbol": contract.underlying_symbol,
        "contract_type": contract.contract_type,
        "currency": contract.currency,
    }
