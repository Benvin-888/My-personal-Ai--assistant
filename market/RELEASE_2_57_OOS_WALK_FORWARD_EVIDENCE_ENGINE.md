# Phase 2.57 — OOS / Walk-Forward Evidence Engine

Validates chronological out-of-sample and walk-forward evidence without optimizing strategies or making future-profit claims.

## Scope
- chronological train/test separation
- test-window breadth and minimum sample checks
- explicit parameter-selection lock
- leakage/overlap detection
- cost/risk coverage checks
- reproducible evidence fingerprint
- descriptive OOS aggregate results

## Boundary
This phase does not fetch market data, select parameters, optimize strategies, authorize execution, place broker orders, or establish future profitability.

## Evidence hierarchy
Historical, simulated, forward, and live evidence remain distinct and must not be silently mixed.
