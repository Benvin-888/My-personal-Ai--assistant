# Phase 2.72 — Capital & Risk Reservation Ledger

## Purpose

Phase 2.72 adds an auditable reservation boundary between evaluated capital/risk
capacity and later decision/execution stages.

A budget assessment alone is not enough when multiple decisions are evaluated
close together: two independent decisions could both observe the same remaining
capacity. The reservation ledger records capital and risk that have been
explicitly reserved so later assessments do not silently double-count capacity.

## Guarantees

- Point-in-time, deterministic reservation state.
- Capital and risk reservations are explicit and account-scoped.
- Reservations can be released, consumed, or expired; terminal states cannot be
  reused as active reservations.
- Duplicate reservation identities are rejected.
- Reservation fingerprints provide tamper-evident provenance.
- Missing budgets fail closed.
- Missing expiry or source decision identity fails validation by default.
- Existing committed capital/risk is separated from active reservations.
- Strategy-level reservation limits are supported.
- No assumption that account balance equals deployable capital.
- No broker connectivity, credentials, order placement, cancellation, or
  execution authorization.
- No profit prediction or strategy selection.
- `execution_authorized` remains permanently `False`.

## Relationship to 2.71

2.71 answers whether a proposed capital/risk use fits the supplied budget.
2.72 adds a separate reservation state so capacity already reserved by prior
  decisions is visible to subsequent budget checks.

2.72 does not replace 2.71 and does not convert a reservation into an
`ExecutionRequest`.
