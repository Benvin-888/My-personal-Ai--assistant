# Phase 2.18 — Paper Trading Readiness & Safety Gate

## Objective

Phase 2.18 establishes an explicit, deterministic readiness contract for an **isolated research-only paper-trading harness** after Phase 2.17 final research evidence.

The objective is not to start broker execution. The objective is to make the transition from research evidence to paper research measurable, auditable, economically realistic, and safe.

## Required readiness dimensions

1. Phase 2.17 final evidence must be `PROMOTE_PAPER` and `eligible_for_paper`.
2. Market data must be explicitly marked ready and within the configured freshness ceiling.
3. Risk configuration must be present and remain within conservative per-trade and total-risk ceilings.
4. Configured reward/risk must meet the readiness floor.
5. Point-in-time execution semantics must be verified.
6. No-lookahead verification must be explicit.
7. Transaction-cost/slippage friction must be available.
8. The paper environment must be explicitly isolated.
9. Broker execution must remain explicitly disabled.

## Profitability discipline

Passing this gate does **not** establish profitability. It only establishes that a strategy with sufficient research evidence has met the prerequisites for controlled paper research. Realistic spreads, slippage, costs, execution timing, drawdown, risk, and out-of-sample behavior remain central to evaluating economic viability.

## Safety boundary

This module:

- does not fetch market data;
- does not connect to Deriv or another broker;
- does not read credentials;
- does not place, modify, or cancel orders;
- does not authorize demo/live execution;
- does not select or optimize candidates;
- does not convert a research result into a broker instruction.

`ready_for_paper_research=True` is a readiness statement for an isolated research harness, **not execution authorization**.

## Next architectural step

After local verification, the next phase can define the paper-trading ledger/event contract and deterministic simulation lifecycle. That layer should remain broker-independent and should consume verified readiness rather than bypassing the research gate.
