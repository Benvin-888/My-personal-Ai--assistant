# BENVIN / APEX — Phase 2.6.10

## Unified Market Operational State

Phase 2.6.10 combines already-observed market-data operational facts into one deterministic, auditable state.

### Inputs

- provider health observation
- provider reliability snapshot
- observation freshness assessment
- normalized data-quality report

### Outputs

`MarketOperationalState` exposes:

- provider and pair
- overall status: `HEALTHY`, `DEGRADED`, `UNUSABLE`, or `UNKNOWN`
- `analysis_usable`
- assessment timestamp
- freshness and observation age
- data-quality classification and score
- provider health
- reliability success rate
- consecutive failures
- total reliability checks
- explicit reasons and warnings

### Safety / architecture

This phase is intentionally observation-only. It does not:

- fetch data
- select or switch providers
- generate trading signals
- select strategies
- calculate position size
- access accounts
- place, modify, or close trades
- claim profitability

`analysis_usable` means only that the supplied operational evidence satisfies this layer's policy. It is not a trading authorization.

The function is deterministic and performs no network I/O, so it can be used with explicitly time-bounded inputs during historical replay as well as live monitoring.

### Conservative defaults

- fresh data is required for analysis eligibility
- stale data is not eligible by default
- fair/poor/invalid quality is not eligible by default
- failed health is a hard blocker
- reliability below 95% is degraded
- more than 2 consecutive failures is degraded
- missing required observations prevent readiness

Policies are explicit and injectable rather than hidden in strategy code.

### Profitability rationale

Reliable strategy research requires separating signal quality from data quality. A strategy should not receive an implicit green light merely because its indicator conditions are satisfied while the underlying provider is stale, failing, or structurally poor.

This phase therefore creates an auditable operational gate for later research, forward testing, and execution layers without conflating operational readiness with a trading decision.
