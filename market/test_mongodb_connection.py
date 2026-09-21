"""Real MongoDB connectivity and Phase 2.47 index verification."""
from __future__ import annotations

import os
import uuid

import pytest

from market.mongodb_config import get_mongodb_database, get_mongodb_uri
from market.mongodb_journal import MongoTradeJournal


pytestmark = pytest.mark.integration


def test_real_mongodb_connection_database_and_indexes() -> None:
    """Ping the cluster, create evidence indexes, round-trip one probe, clean up."""
    if not os.getenv("MONGODB_URI", "").strip():
        pytest.skip("MONGODB_URI is not configured; real MongoDB integration test skipped")

    uri = get_mongodb_uri()
    assert uri.startswith(("mongodb://", "mongodb+srv://"))
    database = get_mongodb_database()
    assert database

    journal = MongoTradeJournal()
    probe_id = f"__apex_phase247_probe__{uuid.uuid4().hex}"
    try:
        assert journal.database_name == database
        assert journal.health_check() is True
        names = journal.ensure_indexes()
        assert names == (
            "evidence_fingerprint_1",
            "symbol_1",
            "timestamp_1",
            "status_1",
        )
        assert journal.save({"trade_id": probe_id, "status": "probe"}) == probe_id
        assert journal.get(probe_id)["status"] == "probe"
        journal.collection.delete_one({"_id": probe_id})
    finally:
        journal.close()
