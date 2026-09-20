"""Phase 2.44 journal abstraction.

Persistence implementations can be added later (MongoDB, SQL, etc.).
"""

from typing import Protocol

from .trade_evidence import TradeEvidence


class PerformanceJournal(Protocol):
    def record(self, evidence: TradeEvidence) -> None:
        ...

    def get(self, trade_id: str) -> TradeEvidence | None:
        ...


class InMemoryPerformanceJournal:
    def __init__(self) -> None:
        self._items: dict[str, TradeEvidence] = {}

    def record(self, evidence: TradeEvidence) -> None:
        self._items[evidence.trade_id] = evidence

    def get(self, trade_id: str) -> TradeEvidence | None:
        return self._items.get(trade_id)
