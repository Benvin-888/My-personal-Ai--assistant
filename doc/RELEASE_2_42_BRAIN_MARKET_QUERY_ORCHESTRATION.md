# Phase 2.42 — Brain → Market Read-Only Query Orchestration

Phase 2.42 makes the Phase 2.41 Brain/Market boundary executable as a controlled read-only query path.

## Flow

`brain.py → structured market_read intent → main.py → BrainMarketQueryService → Unified Market Data → Technical Analysis → Regime → Session → Operational State → Market Intelligence → Brain/main`

## Safety

- No execution request is created.
- No live broker execution path is called.
- No Deriv credentials are read.
- No buy/sell/cancel/modify operation is exposed.
- `execution_authorized` remains false throughout the path.
- Market evidence remains point-in-time and fingerprinted.

## Scope

This phase establishes the real Brain → Market read-only plumbing. It is not a live trading automation phase. Provider selection, cost/slippage realism, risk approval, execution, reconciliation, and controlled forward trading remain separate boundaries.
