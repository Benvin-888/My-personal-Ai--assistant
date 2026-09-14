# Phase 2.23 — Deriv Demo Execution Adapter

## Purpose

Phase 2.23 adds the first broker-specific execution adapter behind the Phase 2.22 provider-neutral Execution Gateway.

The adapter is **demo-only**. It uses Deriv's current Options REST OTP flow and authenticated demo WebSocket for proposal and buy operations. It refuses real-account WebSocket URLs.

## Safety boundary

- Only `ExecutionMode.DEMO` is accepted.
- The adapter requires an explicit `DerivContractSpec`.
- A `TradePlan` is never silently translated into a Deriv contract.
- The contract symbol must exactly match the TradePlan pair.
- The Phase 2.22 gateway must validate the request before broker I/O.
- Credentials are supplied at runtime or through environment variables; they are never stored in source files.
- No live-account execution is supported.
- No account balance, portfolio, sell, cancel, or contract-update operations are included in this phase.
- Network transport is injectable for deterministic tests.

## Deriv API basis

The current Deriv API uses a REST OTP endpoint to obtain a short-lived authenticated WebSocket URL, then uses the authenticated WebSocket for trading operations. Demo and real WebSocket endpoints are distinct. The adapter accepts only a demo-scoped URL.

## Important product-model distinction

APEX's `TradePlan` is a risk-managed Forex plan with entry/stop/target semantics. Deriv's current Options API trades contracts using proposal/buy semantics. Because those are not identical instruments, Phase 2.23 intentionally requires an explicit `DerivContractSpec` rather than pretending that an APEX stop-loss/take-profit plan is automatically equivalent to a Deriv contract.

## Tests

Dedicated test file: `market/test_deriv_demo.py`.

All network operations are mocked in the dedicated tests; no real account or order is used by the test suite.
