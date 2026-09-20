# Phase 2.46 — Real MongoDB Connection & Persistence Verification

Verifies the configured MongoDB cluster through a real, bounded `ping` while keeping MongoDB strictly in the persistence/research layer.

## Configuration

Only `MONGODB_URI` is required. The existing `python-dotenv` configuration loads local `.env` values without overriding an explicitly supplied process environment variable.

## Verification

Run the real integration check explicitly:

```powershell
python -m pytest market/test_mongodb_connection.py -m integration -q
```

The normal `market` and full suites continue to exclude external integration tests.

## Safety

- Uses a 5-second server-selection timeout.
- Never prints or embeds the MongoDB URI in connection failure messages.
- Verifies the configured database name and a successful MongoDB `ping`.
- MongoDB cannot authorize, execute, modify, cancel, or risk-manage trades.
