# APEX / BENVIN Phase 2.15 — Research Cohort & Coverage Integrity

Phase 2.15 adds a deterministic research-cohort contract on top of the experiment, validation, robustness, statistics, and promotion layers.

## Purpose

Prevent weak or duplicated evidence from being presented as meaningful cross-market/timeframe coverage. A cohort is a pre-assembled set of `ResearchExperimentResult` objects. The framework audits coverage; it does not choose candidates or optimize parameters.

## Gates

Default checks require:
- at least 3 completed cases;
- at least 2 distinct symbols;
- at least 1 distinct interval;
- minimum case coverage per symbol and interval;
- at least 2 symbol/timeframe coverage cells;
- unique dataset IDs;
- unique dataset content fingerprints when supplied;
- a locked holdout.

These are conservative evidence-integrity defaults, not profitability guarantees.

## Safety / architecture

Phase 2.15 performs no data fetching, optimization, broker access, order placement, execution authorization, or candidate selection. It reports whether a supplied cohort has sufficient structural coverage for downstream promotion evidence.

## Scope boundary

Phase 2.15 does not silently infer that different symbols or intervals are statistically independent. It only verifies declared coverage and dataset identity. Statistical dependence and portfolio correlation remain separate research concerns.
