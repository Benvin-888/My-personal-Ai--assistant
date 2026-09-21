# BENVIN/APEX Phase 2.49 — MongoDB Trade Evidence Performance Analytics Foundation

## Scope

Phase 2.49 adds a deterministic, read-only analytics layer over the Phase 2.48 MongoDB Trade Evidence Query Layer.

It provides:
- status and symbol record counts;
- explicit `realized_pnl` aggregation when present and finite;
- winning, losing, and breakeven trade counts for records with valid realized P&L;
- total P&L, gross profit, gross loss, win rate, profit factor, and expectancy;
- optional exact-match filters for research segmentation.

## Safety

This phase is analytics-only. It does not create execution requests, authorize trades, access broker credentials, or call Deriv execution APIs. It does not infer profitability from status alone; P&L metrics require explicit numeric `realized_pnl` evidence.

## Verification

The dedicated Phase 2.49 analytics tests must pass before the user's Windows project is considered to have a verified Phase 2.49 baseline. The user's local full-project test results remain authoritative.
