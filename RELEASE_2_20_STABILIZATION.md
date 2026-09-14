# BENVIN Phase 2.20 — Stabilized Build

This build contains the Phase 2.20 deep-audit fixes.

## Fixed

- Corrected paper-trading transaction-cost accounting so each fill is counted exactly once.
- Preserved the original planned entry price separately from the actual filled entry price.
- Made candle chronology validation timezone-aware and based on actual instants rather than timestamp strings.
- Rejected naive candle timestamps that do not include timezone information.
- Unified market, research, backtest, and package metadata on version `2.20.0`.
- Updated setuptools package discovery so the project wheel can be built from the source tree.
- Expanded pytest discovery to include assistant-core regression tests.
- Fixed contextual filesystem-path recovery for wrapped `last_tool_result` values.
- Made memory and context persistence repository-relative instead of dependent on the process working directory.
- Changed memory/context writes to atomic temporary-file replacement.
- Replaced the old root-level memory demo script with isolated automated tests.
- Removed generated caches/build artifacts from the distribution package.

## Validation

- Python compilation: PASS
- Automated tests: **664 passed, 4 deselected**
- Package version consistency: PASS (`2.20.0`)
- Wheel build with installed build dependencies: PASS

The four deselected tests are integration tests requiring live external services/network access and remain intentionally excluded by the project's default pytest configuration.
