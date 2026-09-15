# BENVIN / APEX — Phase 2.32
## Authenticated Demo Operational Control

Phase 2.32 strengthens the Phase 2.31 authenticated Deriv demo session manager with a deterministic operational-control layer.

### Added
- lifecycle health snapshot via `DerivDemoSessionManager.health()`
- explicit reconnect budget with `max_reconnects`
- `reconnect_allowed` guard
- deterministic injectable clock for operational-age evidence
- transition timestamp tracking
- safe operational health included in `safe_summary()`
- dedicated operational-control tests

### Safety boundaries
- health inspection performs no network request
- no trading operation is introduced
- no live execution authority is introduced
- credentials and authorization tokens are never returned by operational summaries
- real/demo endpoint enforcement remains in the Phase 2.30 authenticated session
- authenticated state means the last controlled authenticated validation succeeded; it does not claim continuous broker connectivity

### Verification target
Run:

```powershell
python -m pytest market/test_deriv_demo_session.py market/test_deriv_demo_session_manager.py market/test_deriv_demo_session_operational_control.py -v
```

Then run the complete market suite:

```powershell
python -m pytest market -v
```
