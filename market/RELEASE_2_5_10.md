# APEX / BENVIN Market Package — Release 2.5.10

## Point-in-Time Backtest Execution Semantics

This release hardens the backtest pipeline against same-bar execution bias.

### Core rule

A completed candle **N** may generate a signal only from information available at candle N. With the default `NEXT_BAR_OPEN` execution policy, that signal is executed at candle **N+1 open**. The execution frame is recorded separately from the signal frame.

### Included

- Market data foundation and historical Forex data
- Technical analysis foundation
- Strategy engine, registry, factory, and ensemble
- Historical replay
- Position and trade simulation
- Execution friction
- Performance metrics
- Backtest reporting
- Backtest orchestration
- Backtest integrity validation
- Explicit signal/execution timing metadata

### Validation

- Backtest suite: 89 passed
- Strategy suite: 99 passed
- Technical-analysis suite: 18 passed
- Full non-network market suite: 206 passed
- Full market suite: 225 passed, with 4 Yahoo Finance live-data tests unable to connect from the validation environment

The Yahoo connectivity failures are external-provider/network failures, not backtest-engine failures.

## Profitability status

This release improves economic validity but does **not** establish profitability. Profitability still requires realistic provider data, bid/ask execution, variable spread/slippage, financing/overnight costs, risk and position sizing, out-of-sample and walk-forward testing, robustness/stress testing, and paper trading before any live broker execution.
