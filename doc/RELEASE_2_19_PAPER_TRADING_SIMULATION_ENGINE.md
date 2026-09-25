# APEX / BENVIN Phase 2.19 — Paper Trading Simulation Engine

## Purpose

Phase 2.19 provides a deterministic, research-only paper-trading simulator. It
is the first executable simulation layer after the Phase 2.18 readiness gate.
It is deliberately isolated from broker connectivity and real account state.

## Guarantees

- Plan generation receives only the historical candle prefix through candle N.
- A plan from candle N executes at candle N+1 open.
- Spread, slippage, variable costs, and fixed costs use the existing friction model.
- Stop/target collision behavior is explicit and deterministic.
- Open positions are marked to market when configured.
- Open positions are closed at the final available close as `END_OF_TEST`.
- Every entry, exit, rejection, and mark is an immutable event.
- Results receive a deterministic SHA-256 evidence fingerprint.
- The initial release permits one open position and does not model stacking or correlation.

## Safety boundary

This module has no broker client, credentials, account reads/writes, order
placement, leverage management, or execution authorization. `eligible_for_demo`
is intentionally not provided by the simulator. A simulated fill is not a real
fill and paper performance is not evidence of guaranteed profitability.

## Profitability discipline

The simulator preserves realistic execution friction and point-in-time
semantics so future paper results can be compared with backtests. It does not
optimize parameters or manufacture profitable outcomes.
