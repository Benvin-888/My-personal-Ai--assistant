# APEX Market

APEX / BENVIN market-data, analysis, strategy-research, risk, backtesting, and robustness toolkit.

## Safety boundary
This package is research infrastructure. It does not access broker accounts, place orders, or authorize live execution.

## Install

```bash
python -m pip install -r requirements.txt
```

For editable package installation with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

## Test

Deterministic tests are the default:

```bash
python -m pytest -q
```

Live market-data integration tests are explicitly marked and can be run with:

```bash
python -m pytest -q -m integration
```

The integration suite requires network/provider availability and should not be used as the only CI gate.

## Version

The authoritative version is `market.version`. The backtest package re-exports it for compatibility.
