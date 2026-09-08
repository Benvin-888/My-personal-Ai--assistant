# APEX / BENVIN Phase 2.6.9 — Continuous Provider Health Monitoring

## Purpose

Phase 2.6.9 adds an explicit lifecycle-managed provider health monitoring
layer on top of the existing provider registry and reliability monitor.

It answers:

> Is a provider currently responding to its declared public health check,
and what has the monitoring layer observed over time?

It does **not** answer which provider is correct, which strategy should run,
or whether a trade should be taken.

## Components

### `provider_monitor.py`

Provides:

- `ProviderMonitorPolicy`
- `ProviderHealthObservation`
- `ProviderHealthMonitor`
- `ProviderMonitorError`

### Deterministic primitive

`run_once()` checks every provider that explicitly advertises the `health`
capability. Each observation records:

- provider
- success/failure
- provider status
- UTC check timestamp
- measured latency when a health method was callable
- provider result when available
- error when the check failed

Every observation is also recorded in the existing
`ProviderReliabilityMonitor`.

### Continuous mode

`start()` launches a daemon monitoring loop using the configured interval.
`stop()` explicitly terminates it. The caller owns lifecycle control.

The first monitoring cycle runs immediately after `start()` begins.

## Safety boundaries

This phase deliberately does not:

- authenticate accounts
- read balances or portfolios
- place/cancel/close trades
- generate signals
- select strategies
- calculate position size
- automatically switch providers
- declare one provider correct
- fabricate market observations

Provider health is an observation, not trading authority.

## Failure isolation

A provider health exception becomes a failed observation and a reliability
record. It does not terminate monitoring of other providers.

Observer callbacks are isolated as well: callback exceptions cannot change the
recorded result or stop the monitoring loop.

## Profitability relevance

This phase supports the profitability objective indirectly but importantly.
Future research, strategy, and execution layers need measurable evidence that
the market-data infrastructure was available and responsive at the time an
observation or decision was made. Continuous provider health history gives
that infrastructure evidence without contaminating strategy logic with
provider-specific behavior.

It is not a profitability guarantee.

## Deferred work

Future phases can add:

- market-observation watchdogs tied to live tick streams
- provider/data-quality state aggregation
- persistence of monitoring history
- alerting/event sinks
- explicit, policy-controlled provider failover

Those should remain separate from trading authority.
