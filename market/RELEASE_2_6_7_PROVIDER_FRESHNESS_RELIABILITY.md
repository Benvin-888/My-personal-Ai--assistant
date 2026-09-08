# APEX / BENVIN — Phase 2.6.7

## Provider Freshness & Reliability Monitoring

Phase 2.6.7 adds provider-neutral monitoring primitives for determining whether market observations are fresh, stale, very stale, unavailable, unknown, or invalid, and for maintaining deterministic in-memory provider reliability statistics.

### Scope

- Freshness classification from point-in-time observation timestamps.
- Configurable freshness thresholds.
- Explicit handling of missing timestamps and future timestamps.
- Provider reliability check counters.
- Consecutive-failure tracking.
- Success-rate calculation.
- Average observed health-check latency.
- Deterministic provider snapshot ordering.

### Safety boundaries

This phase does not fetch data, reconnect sockets, select trades, generate signals, place orders, access accounts, or declare a provider's data correct. It measures observations and provider health results supplied by higher-level components.

A missing timestamp becomes `UNKNOWN`; it is never treated as fresh. A future timestamp becomes `INVALID`; the module never silently clamps or rewrites it.

### Freshness states

- `FRESH`: age is at or below `fresh_after_seconds`.
- `STALE`: age is above fresh and at or below `stale_after_seconds`.
- `VERY_STALE`: age is above stale and at or below `unavailable_after_seconds`.
- `UNAVAILABLE`: age is above the unavailable threshold.
- `UNKNOWN`: observation timestamp is missing.
- `INVALID`: observation timestamp is in the future.

### Reliability metrics

The monitor records provider health-check outcomes and optional latency observations. It preserves total checks, successes, failures, consecutive failures, last success/failure timestamps, success rate, and average latency.

The monitor is intentionally in-memory. Persistence and live scheduling belong to later orchestration layers.

### Validation

Dedicated tests cover threshold boundaries, missing/future timestamps, malformed observations, custom policies, provider statistics, consecutive-failure reset, success rate, deterministic ordering, and invalid inputs.
