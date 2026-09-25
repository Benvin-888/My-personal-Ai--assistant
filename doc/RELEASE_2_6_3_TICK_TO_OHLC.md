# APEX / BENVIN Market Release 2.6.3

## Deterministic Tick -> OHLC Aggregation

Phase 2.6.3 adds a provider-agnostic deterministic aggregation layer for
turning validated point-in-time ticks into OHLC candles.

### New files

- `market/tick_ohlc.py`
- `market/test_tick_ohlc.py`
- `market/RELEASE_2_6_3_TICK_TO_OHLC.md`

### Semantics

For each UTC interval bucket:

- `open` = first chronological tick price
- `high` = highest tick price
- `low` = lowest tick price
- `close` = last chronological tick price
- `timestamp` = UTC interval bucket start
- empty intervals are omitted
- volume is `None`; tick count is not represented as traded volume

Input ticks are sorted chronologically. Python's stable sorting preserves the
original order for ticks sharing the same timestamp, so equal-timestamp input
has deterministic open/close behavior without inventing an ordering.

### Supported aggregation intervals

`1m`, `2m`, `5m`, `15m`, `30m`, `60m`, `90m`, `1h`, `1d`.

### Explicit exclusions

Phase 2.6.3 does not:

- retrieve data from Deriv
- subscribe to live ticks
- fabricate missing candles
- fabricate traded volume
- generate trading signals
- select strategies
- calculate position size
- place or close trades
- access account state

The output is compatible with the existing `Candle` / `ForexHistory`
market-data models and can therefore feed the existing analysis and backtest
layers without modifying those layers.
