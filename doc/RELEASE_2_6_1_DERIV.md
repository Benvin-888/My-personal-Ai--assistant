# APEX / BENVIN Market
## Phase 2.6.1 — Deriv WebSocket Market Foundation

### Status

Implemented as a **read-only market foundation**.

### Added

- Public Deriv WebSocket connectivity.
- Configurable `DERIV_APP_ID` support.
- Active-symbol discovery.
- Forex pair to Deriv symbol discovery.
- Latest tick retrieval.
- UTC timestamp normalization.
- Read-only public health check using `ping`.
- Mocked unit tests without requiring network access or credentials.

### Explicitly not included

- Account authentication.
- Balance access.
- Portfolio access.
- Order placement.
- Contract selling.
- Historical tick retrieval.
- Tick streaming subscriptions.
- Tick-to-OHLC candle aggregation.
- Demo or real-money execution.

### Architecture

`Deriv WebSocket -> DerivWebSocketProvider -> APEX Market Layer`

The provider is tick-first. It does not invent OHLC candles merely to satisfy
an existing candle-based interface. Historical tick retrieval and deterministic
candle aggregation remain separate later phases.

### Dependency

Runtime WebSocket connectivity uses the Python package:

`websocket-client`

Install in the BENVIN environment:

`pip install websocket-client`

### Next planned phase

Phase 2.6.2 — Deriv Historical Tick Data.
