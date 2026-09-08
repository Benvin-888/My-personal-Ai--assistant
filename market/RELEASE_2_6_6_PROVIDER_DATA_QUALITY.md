# APEX / BENVIN — Phase 2.6.6

## Provider-Normalized Data Quality & Comparison

Phase 2.6.6 adds a provider-neutral quality layer for already-normalized market data.

### Added

- `market/data_quality.py`
- `market/test_data_quality.py`
- `market/RELEASE_2_6_6_PROVIDER_DATA_QUALITY.md`

### Purpose

The unified market service can now be followed by a deterministic quality gate before research, analytics, or later execution components consume data.

The quality layer evaluates:

- tick structure
- positive prices
- timestamps
- chronological ordering
- duplicate timestamps
- provider-symbol consistency
- OHLC relationships
- candle chronology
- explicit cross-provider point-in-time price comparison
- timestamp tolerance
- relative price tolerance

### Important semantics

This phase does not decide which provider is correct. A comparison only states whether two observations are temporally and numerically within explicitly supplied tolerances.

It does not:

- retrieve market data
- modify provider data
- fabricate missing observations
- fill empty intervals
- generate signals
- select strategies
- calculate position size
- access accounts
- place trades

### Profitability relevance

Reliable profitability research requires trustworthy inputs. This phase provides a deterministic place to detect malformed, inconsistent, stale-by-comparison, or structurally invalid data before it reaches later analysis and forward-testing layers.

It deliberately does not claim that data-quality agreement produces profitable trading results.

### Validation

The dedicated test suite contains 17 tests covering valid data, invalid OHLC/tick structures, ordering, duplicates, mixed symbols, dispatch, and cross-provider comparison behavior.
