# Phase 2.58 — Regime & Session Stability Engine

Phase 2.58 measures whether recorded economic evidence is reasonably consistent across declared market regimes, Forex sessions, and regime×session cohorts.

## Scope

- Descriptive regime stability analysis.
- Descriptive Forex-session stability analysis.
- Regime × session matrix analysis.
- Explicit sample adequacy per cohort.
- Explicit transaction-cost and risk coverage.
- Evidence-class separation; historical, simulated, forward, and live evidence are never silently combined.
- Deterministic evidence fingerprinting.
- Missing regime/session labels remain explicit as `<missing>`.

## Safety boundary

This phase is read-only. It does not optimize parameters, select a preferred regime or session, rank strategies, predict future performance, connect to a broker, authorize execution, or place/modify/cancel trades.

`STABLE`, `UNSTABLE`, and `CONCENTRATED` are descriptive evidence classifications only. They are not profitability guarantees or trading recommendations.
