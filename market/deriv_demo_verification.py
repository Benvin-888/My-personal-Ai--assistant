"""APEX / BENVIN Phase 2.25 - Deriv Demo Execution Verification.

This module verifies the broker receipt after a deliberately controlled demo
purchase. It does not place orders, sell contracts, modify positions, or
support live execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .deriv_demo import DerivContractSpec
from .deriv_demo_control import DemoControlStatus, DerivDemoControlSession, DerivDemoControlResult


class DemoVerificationError(ValueError):
    """Raised for invalid verification input."""


class DemoVerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    API_ERROR = "API_ERROR"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class DemoExecutionVerificationResult:
    status: DemoVerificationStatus
    contract_id: str | None = None
    contract_type: str | None = None
    currency: str | None = None
    buy_price: float | None = None
    payout: float | None = None
    contract_is_sold: bool | None = None
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def verified(self) -> bool:
        return self.status is DemoVerificationStatus.VERIFIED

    @property
    def live_execution(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "status": self.status.value,
            "contract_id": self.contract_id,
            "contract_type": self.contract_type,
            "currency": self.currency,
            "buy_price": self.buy_price,
            "payout": self.payout,
            "contract_is_sold": self.contract_is_sold,
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
            "error": self.error,
            "live_execution": False,
            "account_mode": "demo",
            "broker": "deriv",
        }


class DerivDemoExecutionVerifier:
    """Verify a purchased Deriv demo contract using open-contract state."""

    def __init__(self, session: DerivDemoControlSession) -> None:
        self.session = session

    def verify(
        self,
        purchase_result: DerivDemoControlResult,
        contract: DerivContractSpec,
        *,
        expected_contract_id: str | None = None,
    ) -> DemoExecutionVerificationResult:
        try:
            if not isinstance(purchase_result, DerivDemoControlResult):
                raise DemoVerificationError("purchase_result must be a DerivDemoControlResult")
            if not isinstance(contract, DerivContractSpec):
                raise DemoVerificationError("contract must be a DerivContractSpec")
            if purchase_result.status is not DemoControlStatus.PURCHASED:
                return DemoExecutionVerificationResult(
                    DemoVerificationStatus.REJECTED,
                    reasons=("a successful demo purchase result is required",),
                )
            contract_id = purchase_result.contract_id
            if not contract_id:
                raise DemoVerificationError("purchase result is missing contract_id")
            if expected_contract_id is not None and str(expected_contract_id) != str(contract_id):
                return DemoExecutionVerificationResult(
                    DemoVerificationStatus.REJECTED,
                    contract_id=str(contract_id),
                    reasons=("returned contract_id does not match expected contract_id",),
                )
            if not self.session.websocket_url:
                return DemoExecutionVerificationResult(
                    DemoVerificationStatus.REJECTED,
                    contract_id=str(contract_id),
                    reasons=("demo session is not connected",),
                )

            response = self.session.transport.request(
                self.session.websocket_url,
                {"proposal_open_contract": 1, "contract_id": int(contract_id) if str(contract_id).isdigit() else contract_id},
                self.session.config.timeout_seconds,
            )
            if response.get("error"):
                return DemoExecutionVerificationResult(
                    DemoVerificationStatus.API_ERROR,
                    contract_id=str(contract_id),
                    error=str((response.get("error") or {}).get("message", "Deriv error")),
                )

            payload = response.get("proposal_open_contract")
            if not isinstance(payload, Mapping):
                raise DemoVerificationError("proposal_open_contract response did not contain an object")

            returned_id = payload.get("contract_id")
            if returned_id is None or str(returned_id) != str(contract_id):
                return DemoExecutionVerificationResult(
                    DemoVerificationStatus.REJECTED,
                    contract_id=str(contract_id),
                    reasons=("broker contract_id does not match the purchase receipt",),
                )

            returned_type = payload.get("contract_type")
            returned_currency = payload.get("currency")
            reasons: list[str] = []
            if isinstance(returned_type, str) and returned_type != contract.contract_type:
                reasons.append("broker contract_type does not match requested contract")
            if isinstance(returned_currency, str) and returned_currency != contract.currency:
                reasons.append("broker currency does not match requested contract")
            if reasons:
                return DemoExecutionVerificationResult(
                    DemoVerificationStatus.REJECTED,
                    contract_id=str(contract_id),
                    contract_type=returned_type if isinstance(returned_type, str) else None,
                    currency=returned_currency if isinstance(returned_currency, str) else None,
                    reasons=tuple(reasons),
                )

            buy_price = _optional_float(payload.get("buy_price"))
            payout = _optional_float(payload.get("payout"))
            sold = payload.get("is_sold")
            return DemoExecutionVerificationResult(
                DemoVerificationStatus.VERIFIED,
                contract_id=str(contract_id),
                contract_type=returned_type if isinstance(returned_type, str) else None,
                currency=returned_currency if isinstance(returned_currency, str) else None,
                buy_price=buy_price,
                payout=payout,
                contract_is_sold=bool(sold) if sold is not None else None,
                metadata={"broker": "deriv", "account_mode": "demo", "live_execution": False},
            )
        except DemoVerificationError as exc:
            return DemoExecutionVerificationResult(DemoVerificationStatus.INVALID_INPUT, error=str(exc))
        except Exception as exc:
            return DemoExecutionVerificationResult(DemoVerificationStatus.API_ERROR, error=str(exc))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise DemoVerificationError(f"expected numeric broker field, got {value!r}") from exc
