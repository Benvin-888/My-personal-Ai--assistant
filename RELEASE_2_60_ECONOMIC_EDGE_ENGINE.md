# BENVIN/APEX Phase 2.60 — Economic Edge Engine

Evaluates observed economic evidence for a declared evidence class and determines whether it is sufficient to be treated as an economic-edge candidate.

## Boundary

This layer is descriptive and validation-oriented. It does not predict future returns, optimize parameters, select regimes/sessions, authorize execution, communicate with a broker, or guarantee profitability. Missing costs and risk are never treated as zero, and evidence classes are never silently mixed.

## Inputs

- realized P&L
- explicit total or component transaction/slippage/financing costs
- explicit risk
- declared evidence class
- 2.56 statistical robustness status
- 2.57 OOS/walk-forward status

## Output

The engine reports observed net economics, cost/risk coverage, expectancy, expectancy-to-risk, cost burden, validation limitations, and a deterministic evidence fingerprint. `EDGE_CANDIDATE` means the declared criteria are satisfied by observed evidence; it is not a forecast or guarantee.
