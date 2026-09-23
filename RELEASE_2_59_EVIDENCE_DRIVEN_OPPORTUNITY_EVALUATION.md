# BENVIN/APEX Phase 2.59 — Evidence-Driven Opportunity Evaluation

Phase 2.59 adds a deterministic, read-only opportunity qualification layer.

## Purpose

Evaluate whether a declared point-in-time market observation is sufficiently
well-defined and supported by relevant prior evidence to become a structured
`TradeOpportunity`.

## Boundaries

- Point-in-time integrity is mandatory.
- Evidence must be chronologically available at or before the opportunity timestamp.
- Evidence is matched by strategy/version, symbol/timeframe, regime, session, and evidence class.
- Historical, simulated, forward, and live evidence are never silently mixed.
- Cost and risk coverage remain explicit; missing values are not treated as zero.
- Small relevant samples are reported as limitations rather than promoted to certainty.
- The result is not an economic-edge claim.
- No strategy or parameter optimization is performed.
- No regime/session selection is performed.
- No prediction of future returns is produced.
- No execution request, broker action, credential access, or trade authorization is provided.

## Statuses

- `INVALID`
- `INSUFFICIENT_EVIDENCE`
- `INCOMPLETE`
- `QUALIFIED`
- `QUALIFIED_WITH_LIMITATIONS`

`QUALIFIED` means the declared structural and evidence requirements were met.
It does not mean the opportunity is profitable or guaranteed to succeed.

## Verification

The user's Windows verification is authoritative. Run the dedicated test,
version regression, full market suite, full project suite, and compile check.
