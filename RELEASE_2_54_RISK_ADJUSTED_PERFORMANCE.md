# BENVIN/APEX Phase 2.54 — Risk-Adjusted Performance

## Purpose

Phase 2.54 adds descriptive risk-aware performance analytics over persisted trade evidence.
It extends the cost-aware economic accounting introduced in Phase 2.52 and the strategy
attribution introduced in Phase 2.53.

## Metrics

- realized P&L and standard outcome statistics
- explicit risk coverage
- total and average explicit risk
- P&L-to-explicit-risk ratio
- risk-adjusted expectancy using records with valid positive explicit risk
- realized-P&L path maximum drawdown
- realized-P&L drawdown ratio
- economic cost coverage and inconsistency counts

## Risk data policy

Risk is calculated only from explicitly supplied `risk_amount`, `max_risk`, or
`initial_risk`. Missing, invalid, or negative risk is not treated as zero.

The drawdown metric is explicitly the drawdown of the realized-P&L path. It is not
presented as an account-level drawdown estimate because persisted trade evidence may
not contain complete portfolio equity, concurrent-position, or capital information.

## Boundaries

This phase is read-only. It does not create trades, authorize execution, access broker
credentials, communicate with Deriv for order placement, or bypass the Risk -> Permissions
-> Executor -> Execution Gateway safety chain.

Risk-adjusted metrics are descriptive evidence, not proof of profitability, causality,
or future performance.
