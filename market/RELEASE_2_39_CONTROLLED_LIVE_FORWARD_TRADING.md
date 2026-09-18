# BENVIN/APEX Phase 2.39 — Controlled Live Forward Trading

Phase 2.39 adds a one-shot, fail-closed orchestration layer over the Phase 2.37
Deriv live execution adapter and Phase 2.38 broker reconciliation.

## Purpose

This phase is for **controlled forward evidence**, not autonomous trading.
It accepts only an already-created LIVE `ExecutionRequest` and an explicit
`DerivContractSpec`. It does not generate signals, select strategies, alter
risk sizing, or translate a Forex TradePlan into a broker contract.

## Hard controls

- live-forward policy is disabled by default;
- explicit per-execution confirmation is required;
- one execution per controller instance by default;
- candidate ID and source-evidence fingerprint are required;
- plan freshness is enforced;
- maximum stake is enforced;
- maximum risk fraction is enforced;
- minimum reward/risk is enforced as a forward-evidence quality gate;
- contract symbol must match the approved TradePlan pair;
- execution must return `CONFIRMED`;
- broker reconciliation must return `MATCHED` before the controller reports success;
- unknown or mismatched broker state is never promoted to a verified trade;
- credentials are never included in serialized results.

## Profitability objective

The controller is intentionally a **measurement and control layer**. A live
trade being technically successful is not evidence of profitability. Future
phases must record realized P&L, costs, payout/return, drawdown, strategy,
regime, session, and forward degradation before increasing risk or relaxing
these controls.

## Safety

The test suite uses injected fake execution/reconciliation components. No real
broker trade is performed by the Phase 2.39 test suite.
