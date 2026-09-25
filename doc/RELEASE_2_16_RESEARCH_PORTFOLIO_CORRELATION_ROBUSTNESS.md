# APEX / BENVIN Phase 2.16 — Research Portfolio / Correlation Robustness

Phase 2.16 prevents multi-symbol research from receiving false diversification credit when symbols are highly correlated.

## Added
- `market/research/portfolio.py`
- `market/research/test_portfolio.py`
- updated `market/research/__init__.py`
- research version `2.16.0`

## Controls
- externally supplied pairwise correlation evidence
- minimum sample size
- complete symbol-pair coverage
- maximum absolute pair correlation
- weighted average absolute correlation (advisory)
- research risk concentration (advisory)
- correlation-adjusted effective symbol count (advisory)
- deterministic evidence fingerprint

Correlation evidence is never fetched or inferred by this module. Negative correlation is not automatically treated as diversification for the ceiling checks. Risk weights are research exposure weights, not broker orders or execution instructions.

No optimization, market fetching, broker access, order placement, execution authorization, or profitability guarantee is introduced.
