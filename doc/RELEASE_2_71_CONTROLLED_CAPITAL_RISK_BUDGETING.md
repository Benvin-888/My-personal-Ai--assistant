# Phase 2.71 — Controlled Capital & Risk Budgeting

Adds a deterministic, point-in-time capital and risk budget boundary between strategy allocation and downstream portfolio/risk decision layers.

## Guarantees
- Explicit capital and risk budgets are required by default.
- Account balance is not silently treated as deployable capital.
- Optional balance fallback is explicit and subtracts reserved and committed capital.
- Missing budgets fail closed as `INSUFFICIENT_DATA`.
- Budget and strategy limits are evaluated without predicting returns.
- No broker, credential, order, or execution authority exists.
- Results carry deterministic provenance fingerprints.
