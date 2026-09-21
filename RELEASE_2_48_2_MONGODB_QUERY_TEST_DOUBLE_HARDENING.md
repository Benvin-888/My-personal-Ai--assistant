# BENVIN/APEX Phase 2.48.2 — MongoDB Query Test-Double Hardening

## Correction

The Phase 2.48 MongoDB evidence-query test double now implements the `replace_one(..., upsert=True)` operation used by the existing `MongoTradeJournal.save()` contract.

This fixes the test harness without changing production MongoDB persistence or query behavior.

The Phase 2.48.1 corrections remain intact: the fake database uses the production default `benvin` database name and the research/backtest version modules retain `__release__` metadata.

## Safety

No broker, execution, risk, credential, or trading behavior is introduced or changed.
