# APEX / BENVIN Phase 2.38 — Deriv Live Broker Reconciliation

## Status

**Built and verified. No live order was placed during this phase.**

Phase 2.38 adds a read-only broker-side reconciliation boundary for real Deriv contracts returned by Phase 2.37.

## Purpose

A Phase 2.37 `CONFIRMED` response means the authenticated `buy` call returned a valid contract identifier and buy price. It is not treated as the final authoritative position state.

Phase 2.38 obtains fresh broker state through `proposal_open_contract` and compares it with the approved execution request/outcome and explicit Deriv contract specification.

Deriv's current API documentation requires authentication for `proposal_open_contract`, identifies `contract_id`, `contract_type`, and `currency` as required response fields, and documents numeric fields such as `buy_price` as `string | number`. The implementation therefore parses numeric strings and does not require optional display/symbol fields that are not guaranteed by the current response schema.

## Safety properties

- LIVE requests only.
- Only `CONFIRMED` Phase 2.37 outcomes can enter reconciliation.
- Account scope must match the configured real account.
- Authenticated WebSocket URL must be real-scoped.
- Reconciliation uses read-only `proposal_open_contract` only.
- The response `msg_type` must be exactly `proposal_open_contract`.
- Contract ID, contract type, currency, and buy price are checked.
- If the broker supplies an underlying symbol, it is checked against the approved contract; the current API response does not make this field mandatory.
- Numeric broker values may be returned as either JSON numbers or numeric strings.
- `MATCHED` is the only verified state.
- `MISMATCH`, `UNKNOWN`, and `INVALID_INPUT` are never treated as successful execution.
- Only a matched broker state may enter the provider-neutral position store.
- No buy, sell, cancel, modify, or retry operation exists in this module.
- Credentials are never returned in result payloads.

## Profitability relevance

This phase does not attempt to improve profitability directly. Its purpose is to ensure that any future live-trading performance measurement is based on **broker-confirmed state**, not assumptions made by the strategy, LLM, gateway, or adapter.

That is essential for later economic evaluation: actual fills, broker state, realized outcomes, costs, and forward performance must be measured separately from research signals and backtest assumptions.

## Verification

- Dedicated Phase 2.38 tests: **15 passed**
- Market suite: **934 passed, 4 deselected**
- Full project suite: **943 passed, 4 deselected**
- Python compilation: **COMPILE_OK**

Phase 2.38 does **not** autonomously trade and does not enable live execution. It closes the broker-state verification gap after a future/controlled live execution.
