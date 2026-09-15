# APEX / BENVIN Phase 2.26 — Broker Reconciliation & Position State

## Purpose
Introduce a provider-neutral broker-confirmed position/contract state model and a read-only Deriv demo reconciler.

## Safety boundary
- No buy, sell, cancel, modify, or order-placement operation exists in this phase.
- Only broker-confirmed reconciliation results can enter the authoritative in-memory position store.
- Mismatched/unknown observations are never promoted to position state.
- The implementation remains explicitly demo-scoped.
- Live account execution remains unsupported.

## Deriv source
The Deriv adapter reads `proposal_open_contract` for a known contract ID and validates the returned contract ID, contract type, currency, and lifecycle information.

## Next
Phase 2.27 can build controlled demo forward-trading state management on top of this reconciled broker state, without bypassing the Execution Gateway.
