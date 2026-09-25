# Phase 2.12 — Temporal & Execution Robustness Foundation

## Purpose

Phase 2.12 strengthens APEX research by measuring robustness across calendar
 time and by defining explicit economic/execution perturbation scenarios.

## Added

- `TimeWalkForwardWindow`
- `TimeWalkForwardResult`
- `RobustnessScenarioSpec`
- `RobustnessScenarioResult`
- `RobustnessScenarioSummary`
- `ResearchRobustnessEngine`
- deterministic evidence fingerprints

## Time-based walk-forward

Phase 2.9 already provides trade-count walk-forward analysis. Phase 2.12 adds
calendar-time windows so sparse and dense trading periods are not treated as
equivalent merely because they contain the same number of trades.

The evaluator requires timezone-aware opportunity timestamps and creates
chronological, non-overlapping train/test calendar windows. Test performance
is measured using the train window's ending equity as the starting capital for
that test window.

## Scenario robustness

Scenario specifications make economic perturbations explicit:

- transaction-cost multiplier
- slippage multiplier
- risk-fraction multiplier

The framework does not itself alter a backtest. An external runner must apply
the scenario assumptions and return a measured `ResearchPerformance`. This
prevents the research layer from pretending that an existing result was
replayed under different costs when it was not.

## Safety boundaries

Phase 2.12:

- does not fetch market data
- does not optimize parameters
- does not select a winning scenario
- does not access broker accounts
- does not place orders
- does not authorize execution

It remains a research/evidence layer between historical backtesting and the
Phase 2.10 validation gate.

## Profitability objective

The purpose is not to maximize a single backtest result. APEX should prefer
an edge that remains economically positive under realistic time splits and
credible cost/slippage/risk perturbations. Scenario results are evidence, not
a guarantee of future profitability.
