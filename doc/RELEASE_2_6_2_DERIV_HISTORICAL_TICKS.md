# APEX / BENVIN Market — Phase 2.6.2

## Deriv Historical Tick Data

This delta package contains only the files newly introduced for Phase 2.6.2.

### Files

- `market/ticks.py`
  - `HistoricalTick`
  - `ForexTickHistory`

- `market/deriv_history.py`
  - `DerivHistoricalTickProvider`
  - one-shot `ticks_history` retrieval
  - request validation
  - timestamp/price validation
  - chronological normalization

- `market/test_deriv_history.py`
  - mocked unit tests for the new historical tick layer

### Integration

The new layer depends on the existing Phase 2.6.1:

`market.deriv.DerivWebSocketProvider`

No existing Phase 2.6.1 file is replaced by this delta.

### Deliberately excluded

- OHLC/candle aggregation
- live tick subscriptions
- account authentication
- balances/portfolio
- contract execution
- trading decisions
