# APEX / BENVIN Phase 2.10 — Research Validation & Promotion Gate

## Purpose

Phase 2.10 converts Phase 2.9 strategy-research evidence into an explicit,
deterministic validation decision. It is a **research gate**, not a trading
authorization system.

## Validation evidence

The default policy checks:

1. minimum historical trade sample;
2. positive baseline result;
3. maximum baseline drawdown;
4. chronological out-of-sample performance and generalization;
5. walk-forward window count and profitable-window fraction;
6. parameter stability breadth;
7. Monte Carlo positive-terminal fraction and ruin fraction;
8. transaction-cost burden.

Regime and Forex-session stability are supported as optional evidence by
default and can be made mandatory through policy.

## Promotion semantics

- `PASS` + `eligible_for_paper=True` means the supplied research evidence
  cleared the configured research gates.
- `eligible_for_demo=True` additionally requires regime and session stability
  evidence to be present.
- Neither flag authorizes broker access, order placement, or real-money trading.
- No optimization, parameter selection, broker I/O, credentials, or execution
  occurs in this module.

## Auditability

Every validation result contains the applied policy, individual checks,
failures/warnings, and a deterministic SHA-256 evidence fingerprint over the
research report and policy.

## Profitability principle

A strategy is not promoted because of one high return or one optimized
configuration. The gate favors convergence across realistic costs,
out-of-sample behavior, walk-forward consistency, parameter breadth, risk,
and trade-order robustness.
