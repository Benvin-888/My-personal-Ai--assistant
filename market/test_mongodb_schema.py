import pytest

from market.mongodb_schema import validate_trade_evidence


def test_schema_requires_trade_id():
    with pytest.raises(ValueError, match="trade_id"):
        validate_trade_evidence({"symbol": "EURUSD"})


def test_schema_sets_stable_id_without_mutating_input():
    original = {"trade_id": "  T-100 ", "symbol": "EURUSD"}
    normalized = validate_trade_evidence(original)
    assert normalized["trade_id"] == "T-100"
    assert normalized["_id"] == "T-100"
    assert "_id" not in original
