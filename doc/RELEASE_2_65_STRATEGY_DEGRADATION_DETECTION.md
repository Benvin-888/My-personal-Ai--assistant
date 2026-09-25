# Phase 2.65 — Strategy Degradation Detection

APEX now has a deterministic evidence-monitoring boundary that compares a
current prospective evidence cohort against a previously validated baseline.

## Purpose

Detect material deterioration in observed strategy economics without claiming
future performance, selecting a preferred strategy, or authorizing execution.

## Safety and evidence rules

- Current and baseline cohorts must use the same strategy/version, symbol, and timeframe.
- Evidence classes are isolated; the default comparison class is `FORWARD`.
- Minimum sample sizes are enforced before degradation is assessed.
- Missing costs and risk are never treated as zero.
- Cost and risk coverage are explicit gates.
- Degradation thresholds are configurable; no hidden score or ranking is used.
- Results are descriptive evidence, not a profitability guarantee.
- The assessment cannot authorize execution and does not connect to a broker.

## Metrics

The engine compares observed net expectancy, win rate, profit factor, and
P&L-to-risk when the required evidence is available. A non-positive current
expectancy or P&L-to-risk against a positive validated baseline is treated as
material deterioration. Threshold breaches produce `DEGRADED`; insufficient
samples or incomplete economics produce `INSUFFICIENT_DATA`.

## Relationship to 2.66

Phase 2.65 only detects and records degradation. It does not automatically
stop trading. Phase 2.66 is the separate safety-shutdown/control layer that
may consume this evidence together with operational and risk conditions.
