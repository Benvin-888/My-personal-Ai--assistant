# BENVIN/APEX Phase 2.62 — Limited-Live Eligibility Gate

## Purpose

Provide a deterministic, auditable gate for deciding whether supplied evidence is sufficient to **consider** a separately controlled limited-live deployment.

Eligibility is not execution authorization. The module has no broker connectivity, credentials, order methods, retry loop, or execution capability.

## Gates

- Forward sample adequacy and realized-P&L sample adequacy.
- Explicit forward cost coverage.
- Explicit forward risk coverage.
- OOS evidence status.
- Statistical robustness status.
- Regime/session stability analysis.
- Economic-edge candidate status.
- Optional forward-degradation limit.
- Optional maximum observed risk amount.
- Operational readiness as a separate blocking gate.

## Evidence hierarchy

Historical, simulated, OOS, forward, and live evidence remain distinct. The gate does not merge them or infer missing evidence.

## Safety

`ELIGIBLE` means the configured evidence gates are satisfied. It does **not** create an `ExecutionRequest`, authorize a broker action, or bypass Risk → Permissions → Executor → Execution Gateway.

## Determinism

Criteria, evidence, and the resulting assessment receive SHA-256 fingerprints. Inputs containing invalid or non-finite values are rejected.
