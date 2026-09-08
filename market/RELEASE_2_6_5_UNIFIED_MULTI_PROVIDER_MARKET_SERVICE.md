# APEX / BENVIN — Phase 2.6.5

## Unified Multi-Provider Market Service

Phase 2.6.5 introduces a capability-aware provider registry and a unified
market-data gateway.

### New files

- `market/provider_registry.py`
- `market/unified.py`
- `market/test_unified.py`
- `market/RELEASE_2_6_5_UNIFIED_MULTI_PROVIDER_MARKET_SERVICE.md`

### Architecture

```text
APEX consumers
      |
      v
UnifiedMarketDataService
      |
      v
ProviderRegistry
   /       \
  v         v
Yahoo      Deriv
OHLC       Tick/Live
```

### Provider capabilities

The registry makes capabilities explicit instead of assuming that every
provider supports every operation.

**Yahoo Finance:**

- standardized Forex quote
- historical OHLC market data

**Deriv:**

- latest public tick
- live public tick stream
- public health check

Deriv is deliberately **not** advertised as an OHLC provider in this phase.
This prevents the unified layer from fabricating candles simply because a
provider object happens to expose compatibility methods.

### Selection semantics

A caller can:

1. explicitly select a provider, or
2. omit the provider and let the registry select the highest-priority
   provider that explicitly supports the requested capability.

Provider selection is therefore capability-aware and deterministic.

### Live stream semantics

`create_live_tick_stream()` creates a stream but does not start it. The
caller owns the stream lifecycle. For Deriv, the unified service resolves the
Forex pair to the currently active Deriv symbol and constructs the existing
Phase 2.6.4 `DerivTickStream`.

### Safety boundaries

Phase 2.6.5 does not:

- authenticate trading accounts
- read balances or portfolios
- place, modify, or close trades
- select strategies
- generate trading signals
- calculate position sizes
- claim profitability

### Profitability foundation

The purpose of this phase is architectural: APEX can consume multiple market
data sources without coupling strategy/research code to a single provider.
This supports later data-quality comparison, realistic forward testing,
backtesting, execution modelling, and risk-controlled profitability research.

### Validation

The dedicated Phase 2.6.5 test suite covers:

- aliases
- duplicate registration
- provider replacement
- capability selection
- deterministic priority selection
- explicit provider routing
- quote routing
- history routing
- latest-tick symbol resolution
- health routing
- invalid-pair handling
- unsupported-capability handling
- unknown-provider handling
- default Yahoo/Deriv capability declarations
- prevention of fabricated Deriv OHLC capability
- unregistering providers
