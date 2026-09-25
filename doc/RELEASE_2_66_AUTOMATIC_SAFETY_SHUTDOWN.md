# Phase 2.66 — Automatic Safety Shutdown & Execution Admission Lock

APEX now has a deterministic, fail-closed safety boundary that can revoke new
live execution admission when critical operational, reconciliation, risk,
portfolio, eligibility, or strategy-degradation conditions are observed.

## Core invariant

Once a configured critical condition is detected, APEX can prevent new live
execution deterministically, preserve the reason for the lock, and require
explicit validated re-admission before execution admission can be restored.

## Safety rules

- This phase never places, modifies, cancels, or closes broker positions.
- It never reads broker credentials or connects directly to Deriv.
- Safety uncertainty fails closed.
- Unknown execution outcomes and unreconciled state block new live execution.
- Strategy degradation may use a narrower strategy scope; operational failures
  may escalate to account or system scope.
- A shutdown lock is latched; recovery of a failed condition does not
  automatically re-arm execution.
- Reset enters `RESET_PENDING` and still does not authorize execution.
- Re-arming requires explicit validation and an explicit reset decision.
- The LLM/Brain cannot override, reset, or authorize the safety lock.
- No hidden score, optimization, future-performance prediction, or trade
  selection is performed.

## State machine

`ARMED -> TRIGGERED -> LOCKED -> RESET_PENDING -> ARMED`

The final transition is represented as an explicit validation result only;
this module does not mutate broker or executor state.

## Shutdown scopes

- `STRATEGY`
- `SYMBOL`
- `PORTFOLIO`
- `ACCOUNT`
- `SYSTEM`

## Inputs

The boundary can consume live-monitoring conditions from 2.64, strategy
Degradation from 2.65, portfolio/risk state, eligibility state, and explicit
safety triggers. It keeps those evidence sources separate and records their
fingerprints.

## Relationship to execution

The safety assessment is an admission signal, not an execution instruction.
The intended architecture is:

`Eligibility -> Portfolio Exposure -> Risk/Permissions -> Safety Admission -> Executor -> Execution Gateway`

A future integration may enforce the safety lock at the final execution
admission point. This phase itself has no broker authority.
