# Phase 2.48.1 — MongoDB Trade Evidence Query Layer Correction

Corrections to the Phase 2.48 package:

- Align the query-layer fake MongoDB database with the production default database name (`benvin`).
- Restore `__release__` metadata in backtest and research version modules so package imports remain compatible with the existing package initializers.
- Preserve project version `2.48.0`; this is a corrective patch and does not advance the phase version.
- No broker, execution, risk, or trading authority is added.
