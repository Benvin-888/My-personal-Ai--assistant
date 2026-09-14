# BENVIN / APEX — Phase 2.17
## Final Research Evidence Integration & Promotion Integrity

Phase 2.17 creates the final deterministic research-evidence gate before a separate paper-trading infrastructure phase.

### Purpose

Phase 2.14 already combines research validation, experiments, temporal robustness, execution/cost scenarios, and statistical validation. Phase 2.15 adds cohort coverage integrity, and Phase 2.16 adds portfolio/correlation robustness.

Phase 2.17 does **not** replace those components. It verifies that all three evidence layers agree before a research candidate can receive the final `PROMOTE_PAPER` disposition:

1. Phase 2.14 promotion evidence passes.
2. Phase 2.15 cohort integrity passes.
3. Phase 2.16 portfolio/correlation robustness passes.
4. Candidate and cohort identities match.
5. Portfolio symbol coverage exactly matches the research cohort.
6. Nested evidence fingerprints are present and structurally valid.

### Safety boundary

This module is research-only. It:

- does not fetch market data;
- does not select a strategy or candidate;
- does not optimize parameters;
- does not access a broker;
- does not authenticate to a broker;
- does not place, modify, or cancel orders;
- does not authorize execution;
- does not authorize paper/demo execution by itself;
- never treats a passing research gate as a profitability guarantee.

`eligible_for_demo` is always `False`. A later paper-trading gateway must remain a separate controlled execution boundary.

### Profitability objective

The purpose is not to make APEX pass gates artificially. The final gate is intended to improve economic credibility by preventing incomplete, duplicated, or highly correlated evidence from being promoted as if it were independent robust evidence.

A passing result means only that the supplied evidence satisfied the explicit research-integrity policy. It does **not** prove future profitability.

### New files

- `market/research/final_evidence.py`
- `market/research/test_final_evidence.py`
- `market/research/RELEASE_2_17_FINAL_RESEARCH_EVIDENCE_INTEGRATION.md`

### Changed files

- `market/research/__init__.py`
- `market/research/version.py`

### Verification

Dedicated:

```powershell
python -m pytest market/research/test_final_evidence.py -q
```

Full market suite:

```powershell
python -m pytest market -q
```
