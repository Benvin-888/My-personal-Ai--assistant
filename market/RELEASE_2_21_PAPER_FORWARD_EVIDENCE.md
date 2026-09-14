# BENVIN / APEX — Phase 2.21

## Paper Trading Forward Evidence

Phase 2.21 establishes a deterministic evidence layer over completed Phase 2.20 paper-performance evaluations.

It measures repeated chronological observations, accumulated trade evidence, period pass/positive-return consistency, aggregate economics, drawdown, recent performance, and recent-vs-earlier degradation. It also rejects duplicate evidence and overlapping observation periods.

Default evidence-quality gates require at least 3 observation periods, 30 total trades, at least two-thirds passing and positive-return periods, a recent pass fraction of at least 50%, maximum drawdown of 20%, and recent return retaining at least 25% of earlier positive return.

This phase does not fetch data, access brokers, read accounts, place orders, authorize execution, optimize parameters, or select strategies. Results are immutable and SHA-256 fingerprinted. These thresholds are engineering evidence controls, not profitability guarantees.

Progression: `Paper simulation → paper performance → forward evidence → execution gateway → Deriv demo`.
