# BENVIN/APEX Phase 2.53 — Strategy Attribution

## Purpose
Phase 2.53 adds deterministic, descriptive attribution of persisted trade evidence by **strategy identity and strategy version**.

The goal is to answer: **what outcomes are represented by each strategy/version cohort?**

This is attribution, not proof of causality. A strategy cohort's observed performance must not be interpreted as proof that the strategy caused the outcome without further controlled validation.

## Economic accounting

The attribution layer reuses the Phase 2.52 Economic Performance Engine rules:

- recorded `realized_pnl` remains the authoritative recorded net outcome;
- `gross_pnl - explicit costs` is derived only when both are available;
- missing costs are never assumed to be zero;
- cost coverage is reported per strategy cohort;
- inconsistent realized-versus-derived outcomes are surfaced;
- outcomes are never inferred from status alone.

## Attribution dimensions

Each evidence record is grouped by:

- `strategy_id`
- `strategy_version`

Missing identity values are retained as an explicit `<missing>` cohort instead of being silently discarded. Results are sorted deterministically by strategy ID and version.

## Safety boundary

This is a read-only evidence-analysis layer. It does not:

- place, modify, cancel, or close trades;
- create execution requests;
- authorize execution;
- access broker credentials;
- communicate with Deriv for trading;
- bypass Risk → Permissions → Executor → Execution Gateway.

## Next direction

Phase 2.54 should add risk-adjusted performance so strategy evidence can be compared using return, drawdown, volatility/risk, and other explicit risk characteristics before the project moves into the broader profitability-validation stage.
