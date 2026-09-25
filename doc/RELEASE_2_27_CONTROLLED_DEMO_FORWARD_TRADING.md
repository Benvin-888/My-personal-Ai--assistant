# APEX / BENVIN Phase 2.27 — Controlled Demo Forward Trading

## Purpose

Phase 2.27 connects the existing risk, Execution Gateway, Deriv demo adapter,
verification, and broker reconciliation boundaries into a deliberately bounded
forward-demo workflow.

## Safety boundary

- DEMO mode only.
- Exactly one explicitly confirmed purchase per controller instance.
- Requires an already-approved `ExecutionRequest`.
- Does not create signals or risk decisions.
- Does not support LIVE mode.
- Every successful purchase must be broker-verified and reconciled before it is
  considered forward evidence.
- No unattended loop, scheduler, optimizer, or autonomous trading is added.

## Flow

`approved TradePlan -> Execution Gateway -> Deriv DEMO -> broker verification -> reconciliation -> forward evidence`

## Verification

Dedicated tests exercise confirmation, mode enforcement, one-shot limits,
verification/reconciliation requirements, demo-only guarantees, broker state,
and duplicate protection.
