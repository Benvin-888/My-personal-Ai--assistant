# Phase 2.52 — Economic Performance Engine

Adds a deterministic, read-only economic performance layer over persisted trade evidence.

## Purpose

Move APEX from simple P&L reporting toward economically grounded evidence analysis while preserving an important rule: **missing costs are not assumed to be zero**.

## Capabilities

- Uses explicit `realized_pnl` as the authoritative recorded net outcome when available.
- Recognizes explicit `gross_pnl` and cost fields: `total_costs`, `transaction_cost`, `slippage_cost`, and `financing_cost`.
- Derives gross-minus-cost net P&L only when both gross P&L and explicit costs are available.
- Measures cost coverage and unpriced evidence separately from profitability.
- Flags inconsistency when recorded realized P&L differs from explicitly derivable gross-minus-cost P&L beyond tolerance.
- Retains deterministic win rate, profit factor, expectancy, and aggregate realized P&L metrics.
- Never infers costs, outcomes, or profitability from status fields.
- Has no execution, broker, credential, risk-approval, or order authority.

## Boundary

`MongoTradeEvidenceQuery → Economic Performance Engine → EconomicPerformanceSummary`

The engine is analysis-only and must remain downstream of evidence persistence. It does not alter stored evidence.
