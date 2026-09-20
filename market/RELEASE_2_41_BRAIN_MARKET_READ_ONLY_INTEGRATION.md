# Phase 2.41 — Brain/Market Read-Only Integration Boundary

Phase 2.41 introduces the controlled interface that BENVIN `brain.py` / `main.py` can use to request deterministic Market Intelligence.

## Safety boundary

The interface is read-only. It cannot:

- authorize execution;
- create an execution request;
- place, modify, cancel, or sell a broker contract;
- access broker credentials;
- bypass Risk, Permissions, Executor, or the Execution Gateway.

Brain supplies structured market evidence and receives a deterministic `MarketIntelligenceSnapshot`.

## Purpose

This is the first integration boundary between BENVIN orchestration and the Market package. It deliberately does not make `brain.py` a trader. Future wiring should call this interface and keep all execution authority outside Brain.

## Economic objective

The interface preserves the evidence fingerprint, strategy identity, market regime, Forex session, operational state, and point-in-time context needed to connect research evidence with later forward-trading results and evaluate real economic expectancy.
