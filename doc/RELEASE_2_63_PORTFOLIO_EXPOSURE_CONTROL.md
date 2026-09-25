# BENVIN/APEX Phase 2.63 — Portfolio & Exposure Control

Phase 2.63 adds a deterministic portfolio/exposure assessment boundary.

## Purpose

Evaluate whether a proposed exposure can coexist with the existing portfolio under explicitly configured risk, symbol, strategy, currency, concentration, and correlation constraints.

## Safety boundary

This phase is assessment-only. It does not:

- place, modify, cancel, or close broker orders;
- access credentials;
- communicate with Deriv;
- authorize execution;
- select trades for maximum return;
- predict future correlation.

An `APPROVED` assessment is an input to the downstream risk/permissions/executor chain, not an execution authorization.

## Evidence discipline

Risk and exposure are explicit inputs. Missing required exposure data is not silently treated as zero. Correlation is used only when supplied; it can be required explicitly by configuration.

## Downstream architecture

2.62 Limited-Live Eligibility → 2.63 Portfolio & Exposure Control → Risk Approval → Permissions → Executor → Execution Gateway → Broker → Reconciliation
