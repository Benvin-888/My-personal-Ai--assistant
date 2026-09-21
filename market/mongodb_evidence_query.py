"""Read-only query layer for persisted APEX trade evidence."""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from .mongodb_journal import MongoTradeJournal

class MongoTradeEvidenceQuery:
    """Query persisted trade evidence without granting execution authority."""
    def __init__(self, journal: MongoTradeJournal | None = None) -> None:
        self._journal = journal or MongoTradeJournal()
    @property
    def collection(self) -> Any:
        return self._journal.collection
    def get(self, trade_id: str) -> dict[str, Any] | None:
        value = str(trade_id).strip()
        if not value: raise ValueError("trade_id is required")
        return self.collection.find_one({"_id": value})
    def find_by_fingerprint(self, evidence_fingerprint: str) -> list[dict[str, Any]]:
        value = str(evidence_fingerprint).strip()
        if not value: raise ValueError("evidence_fingerprint is required")
        return self._find_sorted({"evidence_fingerprint": value})
    def find_by_symbol(self, symbol: str) -> list[dict[str, Any]]:
        value = str(symbol).strip()
        if not value: raise ValueError("symbol is required")
        return self._find_sorted({"symbol": value})
    def find_by_status(self, status: str) -> list[dict[str, Any]]:
        value = str(status).strip()
        if not value: raise ValueError("status is required")
        return self._find_sorted({"status": value})
    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        return self._find_sorted({}, limit=limit)
    def find(self, filters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return evidence matching exact filters, newest first."""
        query = dict(filters or {})
        if any(not str(key).strip() for key in query):
            raise ValueError("filter keys must be non-empty")
        return self._find_sorted(query)
    def count(self, filters: Mapping[str, Any] | None = None) -> int:
        query = dict(filters or {})
        if any(not str(key).strip() for key in query):
            raise ValueError("filter keys must be non-empty")
        return int(self.collection.count_documents(query))
    def _find_sorted(self, query: Mapping[str, Any], *, limit: int | None = None) -> list[dict[str, Any]]:
        cursor = self.collection.find(dict(query)).sort("timestamp", -1)
        if limit is not None: cursor = cursor.limit(limit)
        return [dict(document) for document in cursor]
    def close(self) -> None:
        self._journal.close()
