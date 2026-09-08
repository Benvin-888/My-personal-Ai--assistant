# APEX / BENVIN — Phase 2.6.4 Release

## Deriv Live Tick Streaming

Phase 2.6.4 adds a dedicated, read-only live Deriv tick stream on top of the validated 2.6.1 provider foundation and the deterministic 2.6.3 tick-to-OHLC semantics.

### New files

- `market/live_ticks.py`
- `market/deriv_stream.py`
- `market/test_deriv_stream.py`
- `market/RELEASE_2_6_4_DERIV_LIVE_TICK_STREAMING.md`

### Core semantics

1. Connect to Deriv's public WebSocket market-data endpoint.
2. Subscribe with `ticks=<provider_symbol>, subscribe=1`.
3. Normalize the required `epoch`, `quote`, and `symbol` tick fields.
4. Deduplicate exact repeated ticks using provider tick id when available, otherwise timestamp/price identity.
5. Preserve raw provider tick metadata.
6. Maintain a bounded local tick queue so an unattended consumer cannot grow memory without limit.
7. Treat completed candles as immutable: a late tick for an already emitted bucket is rejected.
8. Permit out-of-order ticks inside the still-open bucket so the current candle remains deterministic from received point-in-time data.
9. Emit a candle only when the next bucket begins; the current bucket is never treated as complete merely because the connection stops.
10. Reconnect after transport/API failure using bounded exponential backoff.
11. Send a Deriv ping every 30 seconds by default to keep the WebSocket connection alive.
12. Support graceful shutdown by closing the connection and leaving the current candle incomplete.
13. Keep all account, balance, portfolio, proposal, buy, sell, and trading functionality outside this phase.

### Candle path

`Deriv WebSocket → validated LiveTick → deterministic 2.6.3 candle builder → completed Candle`

The stream does not make trading decisions or invoke strategies.

### Operational safety

The implementation deliberately avoids fabricating missing intervals and does not backfill or alter completed candles when a late tick arrives. This preserves point-in-time semantics needed by later live analysis, forward testing, and profitability evaluation.

### Validation target

Run:

```text
python -m pytest market/test_deriv_stream.py -v
python -m pytest market -v
```

The full market suite should remain green after these additive files are applied.
