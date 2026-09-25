# APEX / BENVIN — Phase 2.8 Risk-Aware Backtesting

## Purpose

Phase 2.8 extends the existing point-in-time backtesting foundation into a
risk-aware historical simulation layer. The engine evaluates what would have
happened when a `TradeOpportunity` was converted into a Phase 2.7 risk-approved
`TradePlan`, sized from account equity, and replayed with deterministic
execution friction and stop/target handling.

## Core guarantees

- Signal/opportunity information is generated from candle N only.
- Directional execution occurs at candle N+1 open.
- The opportunity provider receives only the historical prefix through N.
- Stop/target evaluation begins on the entry candle and uses only that candle's
  OHLC and later candles.
- When both SL and TP are touched in one bar, the default is conservative
  stop-first handling; the policy is explicit and configurable.
- Spread, slippage, variable transaction costs, and fixed execution costs are
  represented through the existing deterministic friction model.
- Position quantity comes from Phase 2.7 monetary risk sizing, not signal
  confidence or score.
- Risk controls are re-evaluated at the historical entry point using simulated
  equity, daily P&L, drawdown, and loss streak state.
- The engine is single-position for this first 2.8 release. It does not stack
  trades or infer cross-pair correlation.
- No broker, account, network, authentication, or live order I/O occurs.

## New API

`market/backtest/risk_aware.py` provides:

- `RiskAwareBacktestConfig`
- `RiskAwareBacktestEngine`
- `RiskAwareBacktestResult`
- `RiskAwareTrade`
- `RiskAwareEvent`
- `IntrabarPolicy`
- `run_risk_aware_backtest`

The caller supplies two deterministic functions:

1. `opportunity_provider(frame)` — creates a point-in-time
   `TradeOpportunity` from frame N.
2. `level_provider(opportunity, frame, next_bar_open)` — supplies stop and
   target levels without access to future OHLC data. The next-bar open is the
   only future value intentionally exposed because it is the simulated
   execution price.

## Economic interpretation

The output reports net P&L after modeled friction, drawdown, win/loss
statistics, profit factor, average risk multiple, risk rejections, stop/target
outcomes, transaction costs, and any risk-budget breaches.

These metrics are research evidence, not a profitability guarantee. A strong
2.8 result is only a starting point for out-of-sample, walk-forward,
parameter-stability, regime, and execution-robustness research.

## Deliberate scope limits

- No live trading or broker execution.
- No tick replay yet; the architecture leaves room for a future tick-replay
  implementation.
- No portfolio correlation model yet.
- No automatic stop/target policy selection; callers provide levels so the
  research assumption remains explicit.
- No claim that the default risk policy or any session is profitable.

## Verification

- Dedicated Phase 2.8 tests: 20 passed.
- Backtest package suite in the reconstructed Phase 2.7 environment: 109 passed.
- Full market-suite reconstruction remains affected only by external Yahoo Finance connectivity tests; those failures are outside the Phase 2.8 engine.
