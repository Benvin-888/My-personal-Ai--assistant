# APEX / BENVIN Phase 2.9 — Strategy Research & Robustness

## Status
Implemented as a measurement and research layer on top of the verified Phase 2.8 risk-aware backtesting foundation.

## Objectives
Phase 2.9 is intended to answer a more important question than whether a strategy can produce a profitable historical backtest:

> Is the observed edge stable enough, across time, parameters, market regimes, sessions, and plausible trade-order variation, to justify further research?

Profitability remains the project objective, but Phase 2.9 makes no profitability guarantee and does not select a strategy automatically.

## Included
- Baseline risk-aware performance summary.
- Chronological in-sample / out-of-sample split.
- Rolling walk-forward evaluation of supplied historical runs.
- Parameter stability comparison across explicitly supplied configurations.
- Regime-group stability when trade metadata contains a regime label.
- Forex-session stability when trade metadata contains a session label.
- Seeded Monte Carlo bootstrap of historical risk multiples.
- Immutable, serializable research results and warnings.

## Safety / correctness boundaries
- No live trading.
- No broker/API execution.
- No authentication or account access.
- No look-ahead data is introduced by the research calculations.
- Phase 2.9 does not optimize parameters or silently choose the best configuration.
- Research subsets are analytical views; the authoritative equity curve remains the Phase 2.8 replay result.
- Monte Carlo uses a fixed seed when reproducibility is required.

## Interpretation
A positive backtest is evidence, not proof of future profitability. Stronger evidence requires convergence across:

1. realistic friction;
2. out-of-sample performance;
3. walk-forward test windows;
4. parameter stability;
5. regime stability;
6. session stability;
7. drawdown and risk behavior;
8. Monte Carlo trade-order robustness.

A strategy should not advance to paper/demo execution merely because one metric or one optimized configuration looks strong.

## Future 2.9.x work
Potential extensions include richer parameter-grid runners, time-based (rather than trade-count) walk-forward splits, deflated/selection-aware statistics, multiple-testing controls, bootstrap confidence intervals, cross-pair validation, and robustness reports that combine execution assumptions with strategy/risk parameter perturbations.
