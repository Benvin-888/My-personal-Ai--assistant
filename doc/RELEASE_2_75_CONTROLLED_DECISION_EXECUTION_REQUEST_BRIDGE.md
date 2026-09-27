# Phase 2.75 — Controlled Decision → Execution Request Bridge

## Purpose

Phase 2.75 closes the boundary between an already-admitted trading decision
and a fully specified execution-request candidate.

The bridge consumes:

`2.67 Decision Admission + 2.72/2.73 Capital/Risk Reservation + 2.74 Decision/Reservation Binding`

and materializes:

`ExecutionRequestCandidate`

The candidate remains subject to the existing downstream safety chain:

`Validator → Permissions → Executor → Execution Gateway → Broker Adapter → Reconciliation`

## Safety boundary

This phase does **not**:

- place, modify, cancel, or close a broker order;
- contact Deriv;
- read credentials;
- authorize execution;
- run strategy selection or market analysis;
- choose a symbol, direction, quantity, stake, broker, or execution mode;
- resize a trade or change its risk/capital allocation;
- bypass Validator, Permissions, Executor, Execution Gateway, 2.66 safety admission, or downstream reconciliation.

All trade terms are caller-supplied as already-approved intent. Invalid or
mismatched terms fail closed.

## Integrity controls

The bridge verifies decision admission, reservation binding, identity,
strategy identity, account scope, provenance fingerprints, request timing,
expiry, direction, and positive quantity/stake constraints.

The resulting request carries decision, reservation, source-snapshot,
admission, binding, and request fingerprints. `execution_authorized` is
always `False`.

## Important implementation boundary

`ExecutionRequestCandidate` is an immutable bridge contract. Integration with
the project's existing `ExecutionRequest` type belongs at the downstream
execution boundary; this phase intentionally does not call that executor.
