# Phase 2.55 — Profitability Validation Framework

## Purpose

Phase 2.55 adds a deterministic validation gate over persisted trade evidence.
It answers whether the available evidence satisfies explicit economic, cost,
risk, data-quality, and minimum-sample requirements before the project moves
into statistical robustness work.

## Design boundary

This phase is descriptive validation, not statistical significance testing.
Phase 2.56 is responsible for statistical robustness, and Phase 2.57 is
responsible for out-of-sample and walk-forward evidence.

The validator never assumes missing transaction costs or risk are zero. It does
not infer profitability from trade status, and it does not claim causality or
future performance.

## Default gates

- at least 30 realized-P&L records
- 100% cost coverage
- 100% risk coverage
- positive realized P&L
- profit factor at least 1.0
- non-negative expectancy
- non-negative P&L-to-risk ratio
- no inconsistent economic records
- no invalid evidence records
- no incomplete evidence records

All thresholds are explicit and configurable through
`ProfitabilityValidationCriteria`.

## Outcomes

- `VALID`: all configured gates pass.
- `INSUFFICIENT_EVIDENCE`: the evidence is not sufficient for this validation
action under the configured criteria.
- `INVALID_EVIDENCE`: the evidence contains data-integrity failures beyond the
configured invalid-record tolerance.

A `VALID` result is not a guarantee of profitability, statistical significance,
or future performance. It means only that the supplied evidence passed the
specified deterministic checks.

## Safety

The module is read-only. It cannot place, modify, cancel, or authorize trades;
access broker credentials; or bypass the existing risk, permissions, executor,
execution-gateway, reconciliation, or live-control boundaries.
