"""Real MongoDB connectivity verification for Phase 2.46.

Run explicitly with:
    python -m pytest market/test_mongodb_connection.py -m integration -q

The test is intentionally excluded from the normal suite because it requires
a real external MongoDB cluster configured through MONGODB_URI.
"""
from __future__ import annotations

import os

import pytest

from market.mongodb_config import get_mongodb_database, get_mongodb_uri
from market.mongodb_journal import MongoTradeJournal


pytestmark = pytest.mark.integration


def test_real_mongodb_connection_and_database_verification() -> None:
    """Ping the configured cluster and verify the configured database scope."""
    if not os.getenv("MONGODB_URI", "").strip():
        pytest.skip("MONGODB_URI is not configured; real MongoDB integration test skipped")

    uri = get_mongodb_uri()
    assert uri.startswith(("mongodb://", "mongodb+srv://"))
    database = get_mongodb_database()
    assert database

    journal = MongoTradeJournal()
    try:
        assert journal.database_name == database
        assert journal.health_check() is True
    finally:
        journal.close()
