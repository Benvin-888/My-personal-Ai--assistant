# BENVIN / APEX — Phase 2.6.12 Trade Opportunity Contract

## Purpose

Phase 2.6.12 introduces the explicit bridge between strategy/ensemble evidence and a candidate trade opportunity.

The contract answers:

> **Given the strategy conclusion and the current market context, is there a sufficiently evidenced candidate opportunity worth passing to the later risk layer?**

It does not answer:

> **How much should we risk, where should the stop/target be, or should an order be executed?**

Those responsibilities remain outside this phase.

## Files added

- `market/opportunity.py`
- `market/test_opportunity.py`
- `market/RELEASE_2_6_12_TRADE_OPPORTUNITY_CONTRACT.md`

No existing market files are modified by this phase.

## Contract inputs

The assessment consumes already-produced, point-in-time observations:

1. **Strategy ensemble**
   - pair
   - interval
   - timestamp
   - LONG/SHORT/NEUTRAL decision
   - ensemble score
   - agreement/conflict/confidence
   - strategy contribution evidence
2. **Market regime context**
   - descriptive regime
   - analysis usability
3. **Forex session context**
   - session phase
   - active sessions
4. **Market operational state**
   - operational status
   - analysis usability

The contract checks market identity and, where supplied, timestamp consistency across these observations.

## Opportunity semantics

The default policy requires:

- successful ensemble evaluation
- non-neutral ensemble decision
- usable/evaluated regime context
- evaluated session context
- operational state permitting analysis

The session is **context, not an assumed source of edge**. `OFF_SESSION` is therefore not automatically rejected. `SINGLE_SESSION` and `OVERLAP` are preserved as factual context.

The contract does not rank London, New York, Tokyo, Sydney, or any overlap by presumed profitability. Session profitability must be established later through realistic, out-of-sample research.

## Statuses

- `CANDIDATE` — all required evidence passes policy.
- `REJECTED` — sufficient information exists, but one or more admission conditions fail.
- `INSUFFICIENT_DATA` — reserved for future explicit insufficient-evidence workflows.
- `INVALID_INPUT` — supplied input cannot represent a valid opportunity observation.
- `ERROR` — unexpected assessment failure.

## Explicit non-responsibilities

This phase does **not**:

- calculate SL/TP
- calculate risk per trade
- calculate position size
- calculate account exposure
- authorize an order
- call a broker
- execute an order
- mutate trading/account state
- claim profitability

The next major boundary is the risk layer.

## Profitability discipline

A candidate opportunity is not a promise of profit.

The architecture deliberately keeps session, regime, strategy, and operational evidence separate so later research can measure profitability by:

- currency pair
- timeframe
- strategy/ensemble configuration
- market regime
- Forex session / overlap
- transaction costs and slippage
- out-of-sample periods
- walk-forward stability
- risk assumptions

Only evidence from robust testing should influence future session or opportunity policies.

## Verification

Dedicated Phase 2.6.12 tests cover:

- candidate creation
- serialization
- neutral/failed ensemble rejection
- score/agreement policies
- required regime/session/operational evidence
- off-session and overlap context
- degraded operational policy
- cross-component pair/interval/timestamp consistency
- LONG/SHORT preservation
- strategy contribution snapshots
- engine/function equivalence
- input and policy validation
- point-in-time metadata
- immutability and audit-context preservation

The implementation is deterministic and performs no network I/O.

## Next phase

The next major phase should be the **Risk Management Foundation**. It should consume `CANDIDATE` opportunities and produce a separate, auditable trade-plan/risk decision containing stop-loss, take-profit, risk budget, position sizing, exposure controls, and rejection reasons.
