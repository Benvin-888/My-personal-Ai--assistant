# Phase 2.47 — MongoDB Collections, Indexes & Trade Evidence Schema

Extends the verified MongoDB connection layer into a deterministic persistence contract for Trade Evidence.

## Scope

- Establishes the `trade_evidence` collection contract.
- Adds deterministic indexes for evidence fingerprint, symbol, timestamp, and status.
- Adds application-level schema validation with a stable required `trade_id`.
- Keeps `_id` bound to `trade_id` for idempotent upsert behavior.
- Extends the real integration test to ping, create indexes, round-trip a temporary probe, and clean it up.

## Safety

MongoDB remains a persistence/research component. This phase does not authorize, submit, modify, cancel, or risk-manage trades and does not access broker credentials.

## Verification

```powershell
python -m pytest market/test_mongodb_schema.py -q
python -m pytest market/test_mongodb_persistence.py -q
python -m pytest market/test_mongodb_connection.py -m integration -q
python -m pytest tests/test_phase_220_regressions.py::test_versions_are_consistent -q
python -m pytest market -q
python -m pytest -q
```

The integration test requires `MONGODB_URI` in the local environment/.env and removes its temporary probe document when finished.
