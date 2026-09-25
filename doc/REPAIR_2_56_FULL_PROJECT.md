BENVIN/APEX Phase 2.56 — Full Project Repair

Repairs applied:
- Restored canonical market/__init__.py.
- Restored canonical market/models.py, including Candle and complete market models.
- Preserved Phase 2.50–2.56 evidence/analytics layers and Phase 2.56 Statistical Robustness Engine.
- Distribution excludes .git, .env, .pyc and __pycache__.

Verified in repair workspace:
- Phase 2.56 + version regression: 11 passed
- market suite: 1046 passed, 5 deselected
- full project suite: 1052 passed, 5 deselected
- market compileall: passed

Restore your existing .env separately. This archive does not contain credentials.
