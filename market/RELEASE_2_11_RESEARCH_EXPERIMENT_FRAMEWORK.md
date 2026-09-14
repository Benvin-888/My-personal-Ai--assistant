# APEX / BENVIN Phase 2.11

## Research Experiment & Cross-Market Validation Foundation

Phase 2.11 introduces a deterministic research coordination layer on top of
Phases 2.9 and 2.10.

### Purpose

APEX can now represent a research case explicitly, including:

- dataset identity and provenance;
- Forex symbol and timeframe;
- strategy identifier and parameters;
- risk parameters;
- execution assumptions;
- deterministic seed;
- dataset content fingerprint when available;
- experiment fingerprint.

Completed cases can be validated through the existing Phase 2.10 promotion
gate and aggregated across symbols and intervals.

### Architecture boundary

The experiment framework does **not**:

- download market data;
- select or optimize parameters;
- place or authorize trades;
- access broker accounts;
- connect to Deriv or any other broker;
- replace the risk-aware backtest engine;
- replace the Phase 2.9 research engine;
- replace the Phase 2.10 validation gate.

Instead, an external runner supplies a `StrategyResearchReport` for each
`ResearchExperimentSpec`. This keeps orchestration separate from data access
and strategy execution.

### Evidence aggregation

`CrossMarketResearchSummary` reports:

- total and completed cases;
- validation-pass fraction;
- profitable-case fraction;
- coverage by symbol;
- coverage by timeframe;
- per-symbol and per-timeframe profitability/validation breadth;
- deterministic evidence fingerprint.

A profitable aggregate does not constitute a profitability guarantee. The
purpose is to expose whether an apparent edge survives broader testing.

### Important limitation

Phase 2.11 is a foundation, not a statistical-selection system. It does not
perform parameter optimization, multiple-testing correction, deflated Sharpe
analysis, confidence intervals, or automatic strategy promotion. Those are
future research-hardening concerns and should be added only with explicit,
testable contracts.
