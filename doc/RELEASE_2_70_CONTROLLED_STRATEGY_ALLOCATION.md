# Phase 2.70 — Controlled Strategy Allocation

Phase 2.70 adds a deterministic allocation boundary between strategy lifecycle/eligibility and decision admission.

It evaluates explicit strategy allocation and risk-budget requests against configurable portfolio-level limits, lifecycle eligibility, concentration, and optional strategy-correlation constraints.

The module does **not** select the best strategy, predict returns, authorize broker execution, access credentials, create ExecutionRequests, or place/modify/cancel trades. Missing required allocation/risk/correlation information is not interpreted as zero.
