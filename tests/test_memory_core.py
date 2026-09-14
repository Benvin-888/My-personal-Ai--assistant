import memory


def test_memory_helpers_are_deterministic():
    assert memory.classify_memory("I love Python") == "preference"
    assert memory.detect_topic("I am building BENVIN") == "current_project_benvin"
    assert memory.normalize_text("Hello, BENVIN!") == ["hello", "benvin"]


def test_memory_round_trip_uses_atomic_save(tmp_path, monkeypatch):
    target = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", str(target))
    payload = [{"id": "mem_test", "content": "BENVIN", "category": "project"}]
    memory.save_memory(payload)
    assert target.exists()
    assert not target.with_suffix(".json.tmp").exists()
    loaded = memory.load_memory()
    assert loaded[0]["id"] == payload[0]["id"]
    assert loaded[0]["content"] == payload[0]["content"]
