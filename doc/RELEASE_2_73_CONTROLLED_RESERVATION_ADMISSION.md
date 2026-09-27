# Phase 2.73 — Controlled Capital & Risk Reservation Admission

Adds a deterministic in-memory admission boundary on top of Phase 2.72.

The ledger prevents independently proposed reservations from oversubscribing
capital or risk capacity within one ledger instance. Admission is revision
checked, account scoped, decision bound, expiry aware, and fail-closed when
capacity data is missing or stale/inconsistent.

This phase does **not** persist to MongoDB, access a broker, read credentials,
create execution requests, authorize trades, or place/modify/cancel orders.
Execution authorization remains downstream of risk, permissions, executor,
execution gateway, safety admission, and broker reconciliation.
