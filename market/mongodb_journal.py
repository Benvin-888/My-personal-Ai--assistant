"""MongoDB persistence adapter for APEX trade evidence."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .mongodb_config import get_mongodb_database, get_mongodb_uri
from .mongodb_schema import TRADE_EVIDENCE_COLLECTION, TRADE_EVIDENCE_INDEXES, validate_trade_evidence


class MongoTradeJournal:
    """Persist trade evidence; never grants execution authority."""

    COLLECTION = TRADE_EVIDENCE_COLLECTION
    SERVER_SELECTION_TIMEOUT_MS = 5000

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._owned_client = False

    def connect(self) -> None:
        if self._client is not None:
            return
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise RuntimeError("pymongo is required for MongoDB persistence") from exc
        self._client = MongoClient(
            get_mongodb_uri(),
            serverSelectionTimeoutMS=self.SERVER_SELECTION_TIMEOUT_MS,
        )
        self._owned_client = True

    @property
    def database_name(self) -> str:
        return get_mongodb_database()

    @property
    def collection(self) -> Any:
        self.connect()
        return self._client[self.database_name][self.COLLECTION]

    def health_check(self) -> bool:
        """Verify the configured MongoDB server with a bounded ping.

        The URI is deliberately never included in the raised error message.
        """
        self.connect()
        try:
            result = self._client.admin.command("ping")
        except Exception as exc:  # PyMongo exposes several connection exceptions.
            raise RuntimeError("MongoDB connection verification failed") from exc
        if not isinstance(result, Mapping) or result.get("ok") != 1:
            raise RuntimeError("MongoDB connection verification returned an invalid ping response")
        return True

    def ensure_indexes(self) -> tuple[str, ...]:
        """Create the stable evidence indexes and return their names."""
        collection = self.collection
        names: list[str] = []
        for field, name in TRADE_EVIDENCE_INDEXES:
            names.append(str(collection.create_index([(field, 1)], name=name)))
        return tuple(names)

    def save(self, evidence: Mapping[str, Any]) -> str:
        document = validate_trade_evidence(evidence)
        trade_id = document["trade_id"]
        self.collection.replace_one({"_id": trade_id}, document, upsert=True)
        return trade_id

    def get(self, trade_id: str) -> dict[str, Any] | None:
        return self.collection.find_one({"_id": trade_id})

    def close(self) -> None:
        if self._owned_client and self._client is not None:
            self._client.close()
            self._client = None
            self._owned_client = False
