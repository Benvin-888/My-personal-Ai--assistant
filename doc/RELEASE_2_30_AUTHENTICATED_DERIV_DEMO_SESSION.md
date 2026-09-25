# Phase 2.30 — Authenticated Deriv Demo Session Validation

Phase 2.30 is the first authenticated, account-scoped Deriv demo session validation layer.

## Scope

- Explicitly model PAT vs OAuth authentication intent.
- Require `DERIV_APP_ID` for the PAT environment flow.
- Obtain the authenticated WebSocket URL through the existing OTP transport.
- Require `wss://` and `/ws/demo`.
- Reject `/ws/real` and public WebSocket URLs.
- Prove the authenticated session with the read-only `balance` request.
- Return only verification metadata; do not return credential values or the balance amount.
- Open and close the WebSocket for a one-shot validation.
- No proposal, buy, sell, cancel, contract update, or autonomous loop.

Deriv documents `balance` as an authentication-required WebSocket endpoint, so a successful balance response provides stronger evidence of an authenticated session than merely opening the WebSocket. citeturn1search0turn1search6

## Safety boundary

A successful Phase 2.30 result means APEX established an authenticated **demo** session and completed one read-only account request. It does not authorize trading and does not constitute live-readiness.

## Credentials

Keep credentials only in the local environment. Never put PATs, OAuth tokens, OTPs, or authenticated WebSocket URLs into source control, project archives, screenshots, or chat.
