# Phase 2.76 — Execution Contract Integrity

## Purpose

Phase 2.76 hardens the Phase 2.75 decision-to-execution-request bridge. It
turns the bridge from a structural materialization layer into an integrity
boundary that verifies the exact execution terms against authoritative
upstream decision, reservation, and explicitly approved execution-contract
evidence.

## New controls

- Exact symbol binding to the admitted decision.
- Direction normalization and exact LONG/SHORT ↔ BUY/SELL binding.
- Exact positive quantity binding to the admitted decision.
- Explicit approved broker, execution mode, account scope, currency, order
  type, contract type, and stake policy.
- Approved stake must match the reserved risk amount when specified.
- Reservation fingerprint verification from the immutable binding fields.
- Decision fingerprint verification covering the decision's execution-relevant
  fields, timing, stages, evidence, and safety state.
- Decision/reservation binding fingerprint verification.
- Explicit execution-contract fingerprint carried into the candidate.
- Request, decision, and reservation expiry checks using timezone-aware
  timestamps.
- Immutable candidate remains `execution_authorized=False`.

## Decision fingerprint correction

The Phase 2.67 decision fingerprint previously covered the admission status,
stages, reasons, safety state, and evidence but did not explicitly cover the
execution-relevant decision terms. Phase 2.76 expands that fingerprint to
include symbol, timeframe, strategy identity/version, direction, quantity,
risk amount, observed/expiry timestamps, stages, blocking reasons, evidence,
and safety state.

Decision expiry is now represented as an actual ISO-8601 timestamp derived
from the configured decision TTL rather than a descriptive status string.

## Safety boundary

Phase 2.76 does not:

- place, modify, cancel, or close a broker order;
- contact Deriv;
- read credentials;
- authorize broker execution;
- resize a trade;
- choose a trade;
- bypass Validator, Permissions, Executor, Execution Gateway, or
  reconciliation.

The resulting candidate is still only an execution admission candidate.

## Verification

- Dedicated bridge/security tests: 22 passed.
- Decision/reservation/bridge integration regression: 79 passed.
- Full market suite: 1309 passed, 5 deselected.
- Full project suite: 1315 passed, 5 deselected.
- Python compile check: passed.

## Next phase

Phase 2.77 should create the single authoritative Execution Coordinator and
Execution Dispatch Ticket. It should not bypass the new integrity boundary or
introduce a second execution route.
