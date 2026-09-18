# BENVIN / APEX Phase 2.37 — Deriv Live Execution Adapter

Phase 2.37 introduces the first broker-specific **real-account execution adapter** for Deriv.

## Safety contract

The adapter is fail-closed and requires, in order:

1. `ExecutionMode.LIVE`.
2. Provider-neutral `ExecutionGateway` admission with `ExecutionAdapterCapability.LIVE`.
3. Adapter-local `live_enabled=True`.
4. Explicit per-execution `explicit_live_confirmation=True`.
5. Independently verified real Deriv authentication and balance identity.
6. A real-scoped authenticated WebSocket URL.
7. An explicit `DerivContractSpec`; no implicit TradePlan-to-Deriv translation.
8. Exact contract symbol match to the risk-approved TradePlan pair.
9. Proposal success and positive ask price.
10. Only then may the authenticated `buy` call occur.

A `CONFIRMED` result requires a valid Deriv `buy` response containing a contract ID and positive buy price. The result is represented by the Phase 2.36.2 strict `ExecutionOutcome` contract.

## Deliberate limitations

- No sell, cancel, or contract-update operation is included.
- No automatic strategy or opportunity decision is made here.
- Brain/main.py cannot directly invoke Deriv; this adapter is a Market execution component.
- Phase 2.38 must perform broker-side post-fill verification/reconciliation.
- Tests use fake transports and do **not** place a real trade.
- The environment switch `APEX_LIVE_EXECUTION_ENABLED` defaults to disabled.

## Verification target

The dedicated Phase 2.37 suite must pass without any broker order being placed during testing.
