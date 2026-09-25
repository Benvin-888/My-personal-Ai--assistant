# Phase 2.68 — Complete Decision Provenance & Decision Journal

## Purpose

Preserve an immutable, point-in-time record of what APEX knew for every decision, then attach later execution/reconciliation/forward/P&L outcomes without rewriting the original decision snapshot.

## Boundary

2.68 is an evidence and provenance layer. It does not authorize execution, place/cancel/modify trades, select strategies, predict profitability, reset safety locks, or allow an LLM to make broker decisions.

## Core separation

1. **DecisionJournalEntry** — immutable decision-time snapshot.
2. **DecisionOutcomeLink** — later outcome references and realized P&L; it cannot mutate the original entry.

Unknown values remain unknown; missing realized P&L is not converted to zero.

## Persistence

The phase provides an in-memory repository for deterministic testing/local use and a MongoDB repository using separate `decision_journal` and `decision_outcomes` collections. Repeated identical writes are idempotent; conflicting rewrites are rejected.

## Next capability

The journal becomes the empirical bridge for later strategy lifecycle and controlled allocation work: admitted/rejected decisions can be compared with the exact evidence and controls available at decision time, without hindsight contamination.
