# Phase 2.50 — MongoDB Trade Evidence Cohort & Attribution Analytics

## Purpose

Phase 2.50 extends the read-only MongoDB evidence analytics layer so APEX can determine where and under what market conditions observed trade outcomes occurred.

The layer groups persisted trade evidence by explicit contextual dimensions and reuses the Phase 2.49 performance summary contract for each cohort.

## Default attribution dimensions

- `strategy_id`
- `strategy_version`
- `symbol`
- `timeframe`
- `regime`
- `session`

Callers can provide a smaller or different ordered set of dimensions. Missing values are retained explicitly as `<missing>` rather than silently discarded.

## Architecture

```text
MongoDB Trade Evidence
        ↓
Read-only Query Layer
        ↓
Cohort / Attribution Layer
        ↓
Performance Summary
```

The implementation does not create trades, authorize trades, access broker credentials, call Deriv execution endpoints, or bypass Risk → Permissions → Executor → Execution Gateway.

## Economic interpretation

Phase 2.50 does not claim that a cohort is profitable merely because its aggregate P&L is positive. It exposes observed evidence so later phases can evaluate sample size, costs, uncertainty, drawdown, robustness, and out-of-sample/forward validity.

`realized_pnl` remains the only explicit P&L input used by the Phase 2.49 summary layer. Missing or invalid P&L remains excluded from P&L metrics while the evidence record remains present in cohort counts.

## Version

Project version: `2.50.0`

Release: `MongoDB Trade Evidence Cohort & Attribution Analytics`
