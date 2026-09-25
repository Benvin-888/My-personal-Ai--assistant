# Phase 2.24 — Deriv Demo Connectivity & Controlled Execution

## Purpose

Phase 2.24 verifies the broker-facing Deriv demo boundary before any autonomous
forward trading is considered. It uses the current Deriv Options API workflow:
REST OTP authentication followed by a demo-scoped WebSocket, active-symbol
discovery, `contracts_for`, proposal validation, and an explicitly confirmed
demo purchase.

## Safety boundary

- Demo account only.
- Real-account WebSocket URLs are rejected.
- Credentials are loaded at runtime; they are never stored in source.
- No live trading is supported.
- Purchase requires `confirm_purchase=True` and a positive policy ceiling.
- No autonomous trading loop is introduced.
- No strategy can bypass the Phase 2.22 execution boundary through this module.
- Tests use mocked transport and never contact Deriv.
- The module records demo purchase evidence but does not claim live execution.

## API compatibility

The implementation follows Deriv's current API field names, including
`underlying_symbol` for symbols. Active-symbol discovery is performed before
contract/proposal operations so APEX does not assume that a market is available.

## Important distinction

APEX's Forex `TradePlan` remains a risk-management object. Deriv Options
contracts use proposal/buy semantics. Phase 2.24 therefore requires an explicit
`DerivContractSpec` and validates its Deriv symbol independently. It does not
invent a mapping from `EURUSD` to a Deriv instrument.

## Controlled sequence

1. Obtain an authenticated demo WebSocket URL through the REST OTP endpoint.
2. Reject any real-account URL.
3. Discover active symbols.
4. Validate the intended Deriv underlying symbol.
5. Validate available contract types with `contracts_for`.
6. Request and validate a proposal.
7. Do not buy unless explicit demo confirmation is supplied.
8. If explicitly confirmed, purchase the proposal subject to the demo price ceiling.
9. Return structured evidence and close the session.

## Tests

Dedicated test file: `market/test_deriv_demo_control.py`.

All dedicated tests use an injected fake transport. No Deriv credentials or
network access are required for the test suite.
