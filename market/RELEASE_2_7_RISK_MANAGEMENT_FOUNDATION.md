# APEX / BENVIN — Phase 2.7 Risk Management Foundation

## Purpose

Phase 2.7 establishes the deterministic capital-protection layer between a
Trade Opportunity and any future execution gateway.

The architecture is:

```text
Trade Opportunity
       |
       v
 Risk Management
   |    |    |
 stop  target sizing
       |
       v
 exposure / loss controls
       |
       v
   TradePlan
       |
       v
 future execution gateway
```

A `TradePlan` is a risk-approved plan, **not an order and not execution
authorization**.

## Files added

- `market/risk.py`
- `market/test_risk.py`
- `market/RELEASE_2_7_RISK_MANAGEMENT_FOUNDATION.md`

No existing market files are modified in this foundation release.

## Core components

### RiskPolicy

Configurable controls for:

- default risk fraction
- maximum risk per trade
- maximum total open risk
- maximum daily loss
- maximum drawdown
- maximum consecutive losses
- minimum reward/risk ratio
- maximum open positions
- maximum position units

The defaults are conservative engineering defaults, not claims of a profitable
or universally optimal configuration.

### AccountSnapshot

Point-in-time equity and optional peak-equity information. Drawdown is derived
deterministically.

### ExposureSnapshot

Point-in-time portfolio risk information supplied by the caller:

- open risk
- daily realized P&L
- open-position count
- consecutive losses
- pair risk

The foundation does not invent correlation assumptions. Correlation-aware
portfolio controls can be added after reliable cross-pair exposure data exists.

### StopLossPolicy

Supports deterministic:

- price-distance stops
- fixed-pip stops
- ATR-multiple stops

### TakeProfitPolicy

Supports deterministic:

- price-distance targets
- fixed-pip targets
- reward/risk targets

### Position sizing

Position size is derived from:

```text
monetary risk budget
--------------------
stop distance × value per price unit
```

Signal score or confidence does **not** increase position size.

`value_per_price_unit` is explicitly supplied by the caller. This avoids
silently assuming an account currency or inventing FX conversion rates.

### RiskDecision

Possible outcomes:

- `APPROVED`
- `REJECTED`
- `INSUFFICIENT_DATA`
- `INVALID_INPUT`
- `ERROR`

Approved decisions contain an immutable `TradePlan` plus warnings and audit
metadata.

## Safety boundaries

This phase performs no:

- broker communication
- account reads/writes
- order placement
- order modification
- authentication
- execution authorization
- LLM-directed execution

The existing execution/security architecture remains unchanged.

## Profitability discipline

Risk management is not expected to manufacture a trading edge. Its purpose is
to prevent a potentially useful edge from being destroyed by excessive risk,
poor reward/risk geometry, concentration, or loss escalation.

Future research must test risk parameters together with strategy parameters,
transaction costs, slippage, execution assumptions, regimes, sessions,
out-of-sample periods, and drawdown behavior.

No default in this module should be interpreted as a guarantee of profitability.

## Next steps

Recommended follow-on work:

1. 2.7.x integrate opportunity and risk contracts more deeply.
2. Add explicit FX valuation/currency-conversion services using trusted market
   inputs rather than assumptions.
3. Add strategy-specific stop/target research without coupling it to execution.
4. Build risk-aware backtesting in Phase 2.8.
5. Test risk parameters out-of-sample and under adverse execution assumptions.
