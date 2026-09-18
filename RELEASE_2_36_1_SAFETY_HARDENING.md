# BENVIN/APEX Phase 2.36.1 — Safety Hardening

Phase 2.36.1 is a corrective hardening release from the Phase 2.36 audit. It does not add live order placement.

## Changes
- Require Deriv authenticated WebSocket responses to explicitly report `msg_type == "balance"` before accepting balance verification.
- Require the balance payload to contain a numeric, non-negative balance value.
- Require a non-empty currency.
- Require the broker-reported `loginid` to match the configured real account ID.
- Treat malformed or mismatched balance responses as not authenticated and not balance-verified.
- Align package/project version metadata at `2.36.0` and remove the stale `2.21.0` regression expectation.
- Add regression coverage for malformed balance identity and message types.

## Verification
- Full suite: **899 passed, 4 deselected**
- Market suite: **890 passed, 4 deselected**
- Python compilation: **168/168 files compiled**

## Live-trading status
No live order execution was added or enabled. The real-account module remains read-only.
