# APEX / BENVIN — Phase 2.20

## Paper Trading Performance & Evaluation Engine

Phase 2.20 adds a deterministic measurement layer on top of the Phase 2.19 paper-trading simulator.

### Purpose

The system now answers a more important economic question:

> After realistic paper execution friction, did the simulated strategy actually produce evidence of a viable trading result?

This phase measures the completed `PaperTradingResult`. It does **not** create trades, optimize a strategy, select parameters, access a broker, place orders, or authorize execution.

### New files

- `market/paper_performance.py`
- `market/test_paper_performance.py`
- `market/RELEASE_2_20_PAPER_PERFORMANCE_EVALUATION.md`

### Changed file

- `market/version.py` → `2.20.0`

### Economic metrics

The evaluator measures:

- initial and ending equity
- net P&L
- gross profit and gross loss
- total transaction costs
- return and return percentage
- trade count and win/loss/breakeven rates
- profit factor
- expectancy
- average win/loss and payoff ratio
- average R-multiple
- best/worst trade
- maximum drawdown
- recovery factor
- transaction-cost burden relative to gross profit
- average/median trade duration and duration dispersion
- long/short trade counts and P&L
- exit-status counts
- rejected entries

### Group evidence

The evaluator accepts optional, externally supplied labels keyed by `trade_id`. This allows future paper evidence to be grouped by dimensions such as:

- forex session
- market regime
- symbol
- timeframe
- strategy variant

The evaluator does not infer those labels or pretend that a trade contains context that was not supplied.

### Economic classification

`PaperPerformancePolicy` provides conservative measurement thresholds. The result can be:

- `PASS` — sufficient sample and all required economic checks pass
- `FAIL` — sufficient sample but one or more required checks fail
- `INSUFFICIENT_DATA` — sample is below the configured minimum

A passing evaluation is evidence for further research only. It is **not** a profitability guarantee and is not permission to trade.

### Safety boundary

Phase 2.20 has:

- no broker connection
- no account access
- no credentials
- no order placement
- no execution authorization
- no strategy optimization
- no candidate selection

The source Phase 2.19 paper evidence fingerprint is preserved in the evaluation metadata, and the evaluation itself receives a deterministic SHA-256 evidence fingerprint.

### Profitability objective

This phase strengthens APEX's profitability discipline by measuring **net economics after friction**, not just whether a strategy produces signals or gross wins. Small samples are explicitly treated as insufficient rather than successful.

A future promotion decision should continue to require out-of-sample, walk-forward, statistical, cohort, correlation, and forward-paper evidence rather than relying on one aggregate paper result.
