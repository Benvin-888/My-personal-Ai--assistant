# APEX / BENVIN — Phase 2.31

## Authenticated Demo Session Manager

Phase 2.31 adds an explicit lifecycle manager around the Phase 2.30 authenticated Deriv demo-session validator.

### Scope

- Explicit disconnected / connecting / authenticated / reconnecting / failed / expired lifecycle states.
- Idempotent connect while authenticated.
- Explicit disconnect and expiry transitions.
- Controlled reconnect with a deterministic reconnect counter.
- Authentication is performed only through the Phase 2.30 read-only session validator.
- Demo-only WebSocket enforcement remains delegated to the authenticated session layer.
- No trading, order, position, or live-execution authority is introduced.
- Safe summaries never expose credentials or authenticated WebSocket URLs.

### Compatibility correction

The manager constructs `DerivDemoAuthenticatedSession` using its keyword-only constructor and invokes its existing `validate(config)` contract. It does not invent a separate `authenticate()` API. The manager also maps the Phase 2.30 result fields `websocket_demo_scoped` and `authenticated_request_verified` into its lifecycle state, rather than assuming result fields that do not exist.

The manager makes the effective authentication method explicit: PAT is the default and requires an App ID; OAuth does not. Missing PAT App-ID configuration is rejected before authentication.

### Verification target

Dedicated Phase 2.30 + 2.31 tests: 28 passed.

Full market suite should be run on the user's authoritative Windows environment before this phase is considered user-verified.
