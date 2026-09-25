# BENVIN/APEX Phase 2.56 — Statistical Robustness Engine

## Purpose

Phase 2.56 quantifies within-sample statistical uncertainty in economically relevant trade evidence. It complements Phase 2.55 Profitability Validation and deliberately does not perform out-of-sample testing, walk-forward validation, strategy optimization, or execution.

## Core capabilities

- sample adequacy assessment
- Wilson win-rate interval
- descriptive P&L distribution statistics
- reproducible bootstrap uncertainty for mean realized P&L
- P&L concentration analysis
- explicit cost/risk coverage reporting
- invalid/non-finite P&L handling
- dependence warning because trade independence is not established by this phase
- read-only adapter over an existing evidence query object's `find(filters)` method

## Statistical boundaries

Missing costs and missing risk are never treated as zero. Bootstrap output describes uncertainty under resampling of the observed sample; it is not a forecast and does not prove future profitability. Phase 2.57 remains responsible for out-of-sample and walk-forward evidence.

## Safety

No broker credentials, Deriv operations, order creation, execution authorization, TradePlan mutation, or strategy modification is introduced.

## Package layout

- `market/statistical_robustness.py`
- `market/test_statistical_robustness.py`
- `market/version.py`
- `market/backtest/version.py`
- `market/research/version.py`
- `tests/test_phase_220_regressions.py`
- `RELEASE_2_56_STATISTICAL_ROBUSTNESS_ENGINE.md`
