# Phase 2.69 — Strategy Lifecycle Management

## Purpose

Manage the auditable lifecycle of a strategy from research idea through validation, forward evidence, eligibility, controlled limited-live observation, monitoring, degradation, suspension, and retirement.

## Core rule

Lifecycle management consumes evidence from earlier APEX phases. It does not manufacture evidence, predict profitability, allocate capital, or authorize broker execution.

## Stages

`IDEA → RESEARCH → VALIDATING → FORWARD → ELIGIBLE → LIMITED_LIVE → MONITORING`

A strategy can move backward when new evidence requires revalidation. `DEGRADED` and `SUSPENDED` are explicit states; `RETIRED` is terminal.

## Safety boundary

2.69 has no broker credentials and no buy/sell/execute/authorize capability. Entry into `ELIGIBLE` or `LIMITED_LIVE` is lifecycle state, not execution permission. Capital allocation remains a later controlled capability.

## Evidence gates

Configurable criteria require the appropriate upstream evidence before progression. Missing evidence fails the relevant gate rather than being interpreted as a positive or zero value. Criteria versions and evidence fingerprints are carried into each lifecycle state.

## Provenance

Lifecycle states are fingerprinted and the in-memory history is append-only. This creates a durable strategy-state history that can be joined with the Phase 2.68 Decision Journal without rewriting historical decisions.
