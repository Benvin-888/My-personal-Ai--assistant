import context


def test_context_round_trip_uses_module_path_and_atomic_save(tmp_path, monkeypatch):
    target = tmp_path / "context.json"
    monkeypatch.setattr(context, "CONTEXT_FILE", str(target))
    value = context.create_default_context()
    value["last_action"] = {"name": "test"}
    context.save_context(value)
    loaded = context.load_context()
    assert loaded["last_action"] == {"name": "test"}
    assert not target.with_suffix(".json.tmp").exists()
