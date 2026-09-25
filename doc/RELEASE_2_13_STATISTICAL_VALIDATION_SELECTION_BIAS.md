# Phase 2.13 — Statistical Validation & Selection-Bias Controls

## Purpose
Phase 2.13 adds deterministic, dependency-free statistical safeguards for research evidence. It complements Phases 2.9–2.12 without replacing their backtesting or validation logic.

## Components
- Bootstrap confidence intervals for sample means with deterministic seeds.
- Positive-bootstrap-fraction evidence measure.
- Bonferroni and Benjamini–Hochberg multiple-testing adjustments for supplied p-values.
- Selection-bias audit contract recording candidate count, selection metric, holdout locking, and independent confirmation.
- Statistical validation policy/result with immutable evidence fingerprints.

## Boundaries
This phase does not calculate p-values from trading returns, claim statistical significance from arbitrary assumptions, optimize parameters, fetch market data, access brokers, place orders, or authorize execution. Statistical inputs must come from an appropriate upstream analysis.

## Research principle
A strategy selected after trying many candidates must not be treated as though it were a single pre-specified test. Candidate count and holdout discipline are therefore explicit evidence fields. Multiple-testing corrections are available when valid p-values are supplied.

## Promotion
`eligible_for_research_promotion` means only that the configured statistical checks passed. It is not paper-trading approval, demo authorization, or a profitability guarantee.
