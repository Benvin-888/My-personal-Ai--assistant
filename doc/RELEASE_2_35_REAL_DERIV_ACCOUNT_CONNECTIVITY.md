# BENVIN/APEX Phase 2.35 — Real Deriv Account Connectivity

## Purpose

Phase 2.35 introduces the real-account connectivity foundation needed to move APEX toward controlled live operation.

It authenticates a real Deriv Options account through the current REST OTP flow, verifies that the returned WebSocket URL is scoped to the real endpoint, and performs a read-only `balance` request.

## Explicit boundary

- No order is created.
- No `buy`, `sell`, `cancel`, or contract-management operation is performed.
- No execution authority is granted.
- Credential values are never returned in result objects or summaries.
- Demo and real WebSocket endpoints are explicitly separated.

## Runtime configuration

The runtime environment uses:

- `DERIV_REAL_ACCOUNT_ID`
- `DERIV_APP_ID`
- `DERIV_PAT`

The PAT and App ID are used only at runtime. They must not be committed to source control or sent through chat.

## Verification

Dedicated Phase 2.35 tests validate configuration, real-endpoint enforcement, OTP handling, read-only balance verification, error handling, and secret-safe summaries.

Actual real-account connectivity is intentionally a separate user-run step after the code package is installed and verified.
