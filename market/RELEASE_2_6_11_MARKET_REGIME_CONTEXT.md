# APEX / BENVIN — Phase 2.6.11 Market Regime & Context Engine

## Purpose

Phase 2.6.11 adds a deterministic, provider-neutral market regime and context layer between technical/strategy intelligence and the future trade-opportunity contract.

The component describes the market environment. It does not turn that description into a trade, risk decision, stop-loss, take-profit, position size, or execution authorization.

## Inputs

- Existing successful Technical Analysis snapshots.
- Optional Market Operational State supplied by a lower layer.
- No network calls.
- No provider-specific logic.

## Regime dimensions

- Trend: bullish, bearish, mixed, neutral, or unknown.
- Momentum: positive, negative, neutral, or unknown.
- Volatility: low, moderate, high, or unknown.
- Trend strength/context: directional, transitional, non-directional, or unknown.
- Momentum alignment/divergence with trend.
- Volatility context: compressed, normal, expanded, or unknown.
- Price location within the available Bollinger range.
- Normalized ATR relative to price when available.

## Overall descriptive regimes

- `BULLISH_TREND`
- `BEARISH_TREND`
- `BULLISH_TRANSITION`
- `BEARISH_TRANSITION`
- `RANGE`
- `HIGH_VOLATILITY`
- `LOW_VOLATILITY`
- `MIXED`
- `UNKNOWN`

The classification is deliberately descriptive. It is not a profitability claim and does not imply that a particular strategy should trade in the regime.

## Operational-state integration

Operational state is optional by default. When supplied and marked unusable, regime assessment is blocked. A policy can explicitly require operational state or permit degraded state for analytical research.

This layer does not redefine or override the Market Operational State contract.

## Point-in-time and research requirements

All regime outputs are derived from the supplied snapshot. The engine does not retrieve newer data or mutate historical observations. This keeps the component suitable for later historical replay, walk-forward testing, and out-of-sample research.

## Intentionally excluded

- Entry/exit signals.
- Stop-loss/take-profit calculations.
- Risk/reward decisions.
- Position sizing.
- Account/equity access.
- Order creation or execution.
- Provider failover.
- Profitability guarantees.

## Next phase

The next planned layer is **2.6.12 Trade Opportunity Contract**, which will explicitly bridge strategy/ensemble evidence and market context to the future Risk Engine without embedding risk or execution decisions inside the strategy layer.
