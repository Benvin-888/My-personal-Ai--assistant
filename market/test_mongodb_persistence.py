import pytest

from market.mongodb_config import get_mongodb_database, get_mongodb_uri
from market.mongodb_journal import MongoTradeJournal


class FakeCollection:
    def __init__(self):
        self.docs = {}

    def replace_one(self, query, document, upsert=False):
        assert upsert is True
        self.docs[query["_id"]] = dict(document)

    def find_one(self, query):
        return self.docs.get(query["_id"])


class FakeDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection())


class FakeAdmin:
    def command(self, name):
        assert name == "ping"
        return {"ok": 1}


class FakeClient:
    def __init__(self):
        self.databases = {}
        self.admin = FakeAdmin()

    def __getitem__(self, name):
        return self.databases.setdefault(name, FakeDatabase())


def test_dotenv_environment_is_used(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://example/testdb")
    assert get_mongodb_database() == "testdb"


def test_missing_uri_is_rejected(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    with pytest.raises(RuntimeError, match="MONGODB_URI"):
        get_mongodb_uri()


def test_save_and_get_use_trade_id_as_stable_key(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://example/testdb")
    journal = MongoTradeJournal(FakeClient())
    assert journal.save({"trade_id": "T-001", "symbol": "EURUSD"}) == "T-001"
    assert journal.get("T-001")["symbol"] == "EURUSD"


def test_save_requires_trade_id():
    with pytest.raises(ValueError, match="trade_id"):
        MongoTradeJournal(FakeClient()).save({"symbol": "EURUSD"})


def test_health_check_uses_database_ping():
    assert MongoTradeJournal(FakeClient()).health_check() is True


def test_adapter_has_no_execution_authority():
    journal = MongoTradeJournal(FakeClient())
    assert not hasattr(journal, "buy")
    assert not hasattr(journal, "sell")
    assert not hasattr(journal, "execute")


def test_health_check_rejects_invalid_ping_response():
    class BadAdmin:
        def command(self, name):
            return {"ok": 0}

    class BadClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.admin = BadAdmin()

    with pytest.raises(RuntimeError, match="invalid ping response"):
        MongoTradeJournal(BadClient()).health_check()


def test_health_check_sanitizes_connection_errors():
    class FailingAdmin:
        def command(self, name):
            raise RuntimeError("mongodb+srv://user:secret@example.invalid/db")

    class FailingClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.admin = FailingAdmin()

    with pytest.raises(RuntimeError, match="connection verification failed") as exc_info:
        MongoTradeJournal(FailingClient()).health_check()
    assert "secret" not in str(exc_info.value)
