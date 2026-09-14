# Phase 2.14 — Research Evidence & Promotion Pipeline

## Purpose

Phase 2.14 combines the evidence produced by the research stack into a single deterministic, auditable promotion decision.

It integrates:

- Phase 2.10 research validation
- Phase 2.11 experiment and cross-market evidence
- Phase 2.12 temporal and execution-robustness evidence
- Phase 2.13 statistical validation and selection-bias controls

The output is a **research promotion decision**, not a trading signal, broker instruction, paper-order instruction, or execution authorization.

## Default promotion gates

A candidate/cohort must provide:

1. At least 3 completed experiments.
2. At least 2 distinct symbols.
3. At least 1 distinct timeframe.
4. At least 67% profitable experiment cases.
5. At least 67% Phase 2.10 validation passes.
6. A passing Phase 2.10 validation result.
7. A passing Phase 2.13 statistical result.
8. A locked holdout before selection.
9. At least 3 temporal walk-forward windows with at least 67% profitable test windows.
10. At least 3 completed robustness scenarios with at least 67% profitable scenarios.

Independent confirmation remains optional by default and can be made mandatory through policy.

## Anti-selection-bias design

The pipeline consumes an already assembled evidence bundle. It deliberately does not rank or select a winner from raw candidates. Candidate selection must happen under a separately auditable holdout/selection process.

## Promotion states

- `PROMOTE_PAPER` — evidence clears the configured research gate.
- `HOLD` — evidence exists but one or more required gates fail.
- `INSUFFICIENT_DATA` — reserved for future explicit data-availability handling.
- `REJECT` — reserved for future explicit rejection policy.
- `INVALID_INPUT` — reserved for future explicit invalid-input reporting.

A `PROMOTE_PAPER` result does **not** mean the strategy is profitable in live trading or safe for broker execution. It means the supplied research evidence clears this research gate.

## Safety boundaries

This phase performs no:

- market-data fetching
- parameter optimization
- candidate winner selection
- broker access
- authentication
- order placement
- account mutation
- execution authorization

Execution remains behind a future explicit gateway and must never be inferred from research promotion.
