"""Application-level MongoDB schema and index contract for trade evidence."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


TRADE_EVIDENCE_COLLECTION = "trade_evidence"

# Indexes intentionally avoid assumptions about broker-specific fields.  The
# _id index is supplied by MongoDB automatically and is therefore not listed.
TRADE_EVIDENCE_INDEXES: tuple[tuple[str, str], ...] = (
    ("evidence_fingerprint", "evidence_fingerprint_1"),
    ("symbol", "symbol_1"),
    ("timestamp", "timestamp_1"),
    ("status", "status_1"),
)

REQUIRED_FIELDS = ("trade_id",)


def validate_trade_evidence(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize the persistence boundary document.

    MongoDB storage accepts the existing Trade Evidence contract without
    inventing broker/execution fields.  The stable trade_id is the only
    mandatory application-level field at this layer.
    """
    normalized = dict(document)
    trade_id = str(normalized.get("trade_id", "")).strip()
    if not trade_id:
        raise ValueError("trade_id is required")
    normalized["trade_id"] = trade_id
    normalized["_id"] = trade_id
    return normalized
