# Phase 2.67 — Controlled Live Decision Admission Pipeline

Phase 2.67 introduces the deterministic orchestration boundary for a single point-in-time trading candidate.

## Responsibilities

- Build an immutable `DecisionContext` from already-produced upstream evidence.
- Evaluate existing market, opportunity, economic-edge, eligibility, portfolio, risk, monitoring, degradation, and safety results.
- Require a fresh final safety re-check before admission.
- Enforce configurable decision freshness/TTL.
- Produce an auditable `DecisionAdmission` with ordered stage results, blocking reasons, provenance fingerprints, and safety state.
- Treat abstention/rejection/blocking as explicit outcomes.

## Safety boundary

`DecisionAdmission` is **not** an `ExecutionRequest` and never grants broker authority. `execution_authorized` is permanently false. No credentials or broker I/O are used. The module does not calculate strategy edge, portfolio exposure, risk, degradation, or safety inference; those remain owned by their existing phases.

## Admission invariant

A candidate is `ADMITTED` only when every required gate passes, the decision is fresh, and the final safety re-check is armed. A stale, invalid, insufficient, degraded, rejected, or safety-blocked candidate cannot become execution-admissible.
