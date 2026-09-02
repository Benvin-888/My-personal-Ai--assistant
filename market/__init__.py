"""
APEX / BENVIN Market Package

Phase 2:
    Market Intelligence Foundation.

This package contains controlled market-data
components.

IMPORTANT:

    Market tools retrieve external market data.

    They do NOT:
        - place trades
        - modify broker accounts
        - execute trading strategies
        - make trading decisions
        - claim that a trade should be taken

Those capabilities will be built separately
and protected by their own security boundaries.

The package initializer intentionally does not
import market-data modules automatically.

This prevents module-loading side effects when
individual market modules are executed directly.
"""