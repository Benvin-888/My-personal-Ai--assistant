# Phase 2.29 — Deriv Demo Credential & Connectivity Gate

Phase 2.29 introduces a credential-aware but non-trading connectivity boundary.

## Scope

- Read Deriv demo credentials from local environment variables.
- Never persist or return secret token values.
- Obtain the authenticated WebSocket URL through the existing Deriv demo transport.
- Reject real-account WebSocket URLs.
- Reject non-demo WebSocket URLs.
- Open and close the demo WebSocket as a connectivity-only probe.
- Do not place, modify, sell, cancel, or otherwise execute a contract.

## Required environment variables

- `DERIV_DEMO_ACCOUNT_ID`
- `DERIV_AUTH_TOKEN`
- `DERIV_APP_ID` when using a PAT

Credentials must remain local to the user's machine and must not be committed to source control or included in project archives.

## Safety boundary

A successful Phase 2.29 result proves only that the configured credentials can obtain and connect to a Deriv demo WebSocket. It does not authorize trading and does not constitute live-readiness.
