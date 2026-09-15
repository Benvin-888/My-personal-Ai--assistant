# Phase 2.25 — Deriv Demo Execution Verification

## Purpose

Phase 2.25 verifies that a deliberately controlled Deriv demo purchase was
actually represented by the broker as the expected contract. It is a
verification/reconciliation step only: it does not place, modify, sell, or
cancel orders.

## Verification boundary

- Requires a successful Phase 2.24 demo purchase result.
- Uses `proposal_open_contract` to retrieve broker-side contract state.
- Verifies the returned contract ID against the purchase receipt.
- Verifies contract type and currency against the explicit `DerivContractSpec`.
- Accepts current Deriv numeric fields whether returned as strings or numbers.
- Records buy price, payout, and sold state when supplied.
- Demo only; live execution is always reported as false.
- No autonomous trading loop is introduced.
- Tests use mocked transport and do not contact Deriv.

## Why this phase exists

A successful `buy` response alone is not enough for a safe execution pipeline.
APEX must be able to ask the broker for the resulting open contract and verify
that the broker-side state matches what APEX believes it purchased.

## Current Deriv API alignment

The implementation follows the current `proposal_open_contract` workflow and
expects the new API's required `contract_id`, `contract_type`, and `currency`
fields. Legacy `loginid` fields are not used.

## Tests

Dedicated test file: `market/test_deriv_demo_verification.py`.

All tests use an injected fake transport. No credentials or live/demo network
access are required by the test suite.
