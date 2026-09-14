# BENVIN/APEX Phase 2.21 — Stabilized Repair

This build repairs the uploaded project snapshot while preserving the verified Phase 2.21 market stack.

## Repair scope

- Restored the canonical `market/__init__.py` so importing `market` has no research-module side effects.
- Restored the complete market foundation through Phase 2.8, including risk-aware backtesting.
- Reapplied the canonical Phase 2.9–2.21 research and paper-trading overlays in order.
- Restored unified package version metadata to `2.21.0`.
- Preserved the assistant core and user project files from the supplied snapshot outside the repaired market stack.
- Removed generated Python caches from the repaired distribution.

## Safety

No broker credentials, live orders, demo execution, or execution authorization are introduced by this repair.

## Verification

The reconstructed market suite passes all deterministic tests. Four live Yahoo Finance integration tests are intentionally excluded by the default pytest configuration and require external network access.

The user's Windows verification remains authoritative; the last reported verified Phase 2.21 result is **675 passed, 4 deselected**.
