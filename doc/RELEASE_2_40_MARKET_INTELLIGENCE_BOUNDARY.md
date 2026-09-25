# BENVIN/APEX Phase 2.40 — Market Intelligence Orchestration Boundary

Phase 2.40 introduces a deterministic, read-only `MarketIntelligenceEngine` and `MarketIntelligenceSnapshot` as the controlled interface between Market intelligence and the future BENVIN `brain.py` / `main.py` integration.

It combines technical analysis, configured strategy ensemble evidence, regime/session/operational context, and the existing Trade Opportunity contract. It performs no broker I/O, creates no execution request, and cannot authorize execution. Inputs must remain point-in-time consistent and the resulting evidence is fingerprinted for auditability.

The boundary is intentionally upstream of risk and execution. It is an architectural step toward measuring real opportunity quality and strategy/session/regime behavior without allowing conversational logic to bypass deterministic controls. It makes no profitability claim.
