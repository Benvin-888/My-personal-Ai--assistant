# BENVIN/APEX Phase 2.64 — Live Monitoring

## Purpose

Phase 2.64 adds a deterministic operational monitoring boundary for controlled live operation.
It observes connection/authentication state, reconciliation backlog, unknown/failed outcomes,
errors/warnings, positions, risk coverage, and observation freshness.

## Safety boundary

This module is observation-only. It does not:

- place, modify, cancel, or close orders;
- authorize execution;
- access broker credentials;
- connect directly to Deriv;
- replace portfolio/exposure controls;
- replace risk approval or permissions;
- predict future performance;
- automatically shut down trading.

A monitoring result is evidence for downstream safety controls, not execution authority.
Automatic safety shutdown is reserved for a later dedicated phase.

## Statuses

- `HEALTHY`
- `WARNING`
- `CRITICAL`
- `INSUFFICIENT_DATA`
- `INVALID_STATE`

## Design principles

- Missing risk or freshness information is not silently treated as safe.
- Unknown/reconciliation problems receive explicit treatment.
- Monitoring criteria are configurable rather than hidden constants.
- Inputs and assessment are deterministically fingerprinted.
- Operational monitoring remains separate from profitability/strategy evaluation.
