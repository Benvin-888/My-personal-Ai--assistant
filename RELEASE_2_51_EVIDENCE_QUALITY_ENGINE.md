# Phase 2.51 — Evidence Quality Engine

Adds a deterministic, read-only quality assessment layer for persisted APEX trade evidence.

## Purpose

Determine whether evidence records are structurally trustworthy enough to enter later
performance, validation, and edge-analysis workflows. Data quality is kept separate from
sample-size sufficiency and profitability conclusions.

## Checks

- stable `trade_id` presence and `_id` consistency when `_id` is present
- evidence fingerprint presence
- strategy/context attribution coverage
- lifecycle field coverage (`timestamp`, `status`)
- timestamp validity when supplied
- finite numeric `realized_pnl` when supplied
- explicit `VALID`, `INCOMPLETE`, or `INVALID` classification
- deterministic issue codes and field-coverage counts
- fingerprint occurrence reporting without treating repeated fingerprints as automatically invalid

## Safety

This phase is strictly read-only. It cannot create, authorize, submit, modify, cancel, or
close trades; it does not access broker credentials and does not bypass the Risk →
Permissions → Executor → Execution Gateway boundary.
