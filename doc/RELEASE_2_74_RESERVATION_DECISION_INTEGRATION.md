# Phase 2.74 — Reservation → Decision Admission Integration

## Purpose

Bind an already-admitted Phase 2.73 capital/risk reservation to an already-admitted Phase 2.67 DecisionAdmission without reimplementing either upstream boundary.

## Contract

The integration requires, by default:

- an `ADMITTED` decision;
- an active `RESERVED` reservation;
- exact source `decision_id` binding;
- exact strategy ID/version binding;
- exact decision risk amount versus reserved risk amount;
- matching account scope;
- reservation and admission provenance fingerprints;
- a valid reservation expiry and explicit point-in-time expiry check.

Missing or conflicting evidence fails closed. The resulting `DecisionReservationBinding` carries the decision fingerprint, reservation fingerprint, Phase 2.73 source snapshot fingerprint, Phase 2.73 admission fingerprint, capital/risk reservation amounts, and its own deterministic binding fingerprint.

## Provenance

The binding is designed to be carried into the Phase 2.68 decision journal/provenance layer. It does not mutate the immutable decision journal entry and does not manufacture execution or outcome evidence.

## Safety boundary

This phase does not:

- create an `ExecutionRequest`;
- authorize execution;
- access broker credentials;
- communicate with Deriv;
- place, modify, close, or cancel trades;
- change reservations;
- bypass risk, permissions, executor, execution gateway, reconciliation, monitoring, or safety shutdown.

`execution_authorized` is permanently `False` in the integration result.
