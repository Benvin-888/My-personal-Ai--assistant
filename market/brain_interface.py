"""Controlled read-only bridge from BENVIN/Brain to Market Intelligence.

Phase 2.41

This module is intentionally an orchestration boundary.  It accepts a
structured request, invokes deterministic Market Intelligence, and returns a
read-only snapshot.  It cannot create, approve, or execute trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .intelligence import MarketIntelligenceEngine, MarketIntelligenceSnapshot
from .strategy.factory import StrategyFactory
from .strategy.registry import StrategyRegistry


class BrainMarketInterfaceError(ValueError):
    """Raised when a Brain -> Market request violates the interface contract."""


@dataclass(frozen=True)
class MarketIntelligenceRequest:
    """Validated, read-only request that Brain may send to Market."""

    analysis: Mapping[str, Any]
    regime: Mapping[str, Any] | None
    session: Mapping[str, Any] | None
    operational_state: Mapping[str, Any] | None
    request_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise BrainMarketInterfaceError("request_id must be a non-empty string")
        if not isinstance(self.analysis, Mapping):
            raise BrainMarketInterfaceError("analysis must be a mapping")
        for name, value in (
            ("regime", self.regime),
            ("session", self.session),
            ("operational_state", self.operational_state),
        ):
            if value is not None and not isinstance(value, Mapping):
                raise BrainMarketInterfaceError(f"{name} must be a mapping or None")


@dataclass(frozen=True)
class BrainMarketResult:
    """Immutable response exposed back to Brain/main orchestration."""

    request_id: str
    snapshot: MarketIntelligenceSnapshot
    execution_authorized: bool = False

    def __post_init__(self) -> None:
        if self.execution_authorized:
            raise BrainMarketInterfaceError(
                "Brain-Market interface cannot authorize execution"
            )
        if self.snapshot.execution_authorized:
            raise BrainMarketInterfaceError(
                "Market snapshot cannot authorize execution"
            )

    def to_dict(self) -> dict[str, Any]:
        result = self.snapshot.to_dict()
        result["request_id"] = self.request_id
        result["execution_authorized"] = False
        result["interface"] = "brain_market_read_only"
        result["interface_version"] = "2.41"
        return result


class BrainMarketInterface:
    """Controlled adapter for future ``brain.py`` / ``main.py`` integration.

    Brain supplies structured market evidence; deterministic Market code
    evaluates it.  The interface exposes no execution method and contains no
    broker/provider execution dependency.
    """

    def __init__(
        self,
        *,
        engine: MarketIntelligenceEngine | None = None,
    ) -> None:
        self.engine = engine or MarketIntelligenceEngine()

    def evaluate(
        self,
        request: MarketIntelligenceRequest,
        *,
        registry: StrategyRegistry,
        factory: StrategyFactory,
    ) -> BrainMarketResult:
        if not isinstance(request, MarketIntelligenceRequest):
            raise BrainMarketInterfaceError(
                "request must be a MarketIntelligenceRequest"
            )
        if not isinstance(registry, StrategyRegistry):
            raise BrainMarketInterfaceError("registry must be a StrategyRegistry")
        if not isinstance(factory, StrategyFactory):
            raise BrainMarketInterfaceError("factory must be a StrategyFactory")

        snapshot = self.engine.evaluate(
            request.analysis,
            registry=registry,
            factory=factory,
            regime=request.regime,
            session=request.session,
            operational_state=request.operational_state,
        )
        return BrainMarketResult(request.request_id, snapshot, False)
