# APEX / BENVIN Phase 2.28 — Live-Readiness Safety Audit

## Purpose

Phase 2.28 establishes a credential-free safety gate before any future consideration of live execution. It audits the existing execution boundary without contacting Deriv, storing credentials, or authorizing a live order.

## Safety properties

- The audit can never authorize `LIVE` execution.
- No broker network calls are made by the audit.
- No token or secret is persisted or returned in audit results.
- Demo execution remains bounded to one explicitly confirmed execution per controller.
- Runtime credentials may be supplied only through secure runtime configuration; source configuration containing secret values fails the audit.
- The Deriv REST endpoint must use HTTPS.
- This phase does not create signals, risk decisions, orders, positions, or live adapters.

## Credentials decision

Do **not** put API tokens into the project files or chat. For the next controlled demo connection, configure the existing environment variables locally:

- `DERIV_DEMO_ACCOUNT_ID`
- `DERIV_AUTH_TOKEN`
- `DERIV_APP_ID` (required for PAT authentication)

Deriv's current documentation states that PAT-authenticated REST requests require both the Bearer token and `Deriv-App-ID`; the OTP endpoint then returns a short-lived WebSocket URL for the selected account. The OTP is valid for 120 seconds and single-use. Live and demo WebSocket endpoints are distinct.

## Promotion rule

Passing this audit is **not** permission to trade live. Live execution remains disabled until a separate, explicit future architecture and safety decision is made and verified.
