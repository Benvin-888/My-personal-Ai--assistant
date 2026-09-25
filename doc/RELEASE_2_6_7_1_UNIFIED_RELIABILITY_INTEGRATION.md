# APEX / BENVIN — Phase 2.6.7.1
# Unified Provider Freshness & Reliability Integration

## Purpose

Integrate the Phase 2.6.7 reliability layer into `UnifiedMarketDataService`
without changing provider authority or introducing trading behavior.

## Added behavior

- Unified service owns an injectable `ProviderReliabilityMonitor`.
- Quote, historical, latest-tick, and health operations record provider
  success/failure and measured latency.
- Latest ticks receive deterministic freshness metadata.
- Standardized quote candles receive freshness metadata when a valid
  `timestamp_utc` is available.
- A public `reliability_snapshot()` method exposes monitoring statistics.
- `assess_observation_freshness()` exposes the provider-neutral freshness
  assessor through the unified service.
- Custom `FreshnessPolicy` and monitor instances can be injected.

## Architectural guarantees

This phase does not:

- choose a trading strategy
- generate signals
- select a broker
- place or modify trades
- access accounts or balances
- declare one market-data provider correct
- fabricate timestamps or market data
- turn stale data into fresh data

Historical datasets are not assigned a single freshness status because they
represent a range of observations rather than one point-in-time observation.

## Compatibility

The existing provider registry and provider implementations remain intact.
The reliability layer is additive and provider-neutral.

## Validation

Dedicated Phase 2.6.7.1 integration tests cover:

- successful quote monitoring
- failed quote monitoring
- latest-tick monitoring
- health monitoring
- aggregate snapshots
- custom freshness policies
- direct freshness assessment
- dependency injection

Run:

    python -m pytest market/test_unified_reliability.py -v

The project-wide regression baseline remains the previously verified
312/312 passing tests; this phase should be run against that baseline after
the files are installed.
