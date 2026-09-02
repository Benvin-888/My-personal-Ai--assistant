"""
APEX / BENVIN Market Data Cache

Phase 2 - Market Intelligence Foundation

Provides a small in-memory cache for market-data results.

Purpose:

    Avoid unnecessary repeated provider requests during
    short periods of time.

IMPORTANT:

    This cache is NOT a source of truth.

    External market data remains the authoritative source.

    The cache will eventually be replaceable with a more
    sophisticated persistence/cache layer if required.
"""

import time


# ============================================================
# CACHE
# ============================================================

class MarketDataCache:
    """
    Simple time-based in-memory market-data cache.
    """

    def __init__(
        self,
        ttl_seconds=15
    ):
        if not isinstance(
            ttl_seconds,
            (int, float)
        ):
            raise ValueError(
                "TTL must be numeric."
            )

        if ttl_seconds < 0:
            raise ValueError(
                "TTL cannot be negative."
            )

        self.ttl_seconds = ttl_seconds

        self._data = {}

    # ========================================================
    # KEY
    # ========================================================

    @staticmethod
    def _make_key(
        pair,
        interval,
        data_range
    ):
        return (
            str(pair).upper(),
            str(interval),
            str(data_range)
        )

    # ========================================================
    # GET
    # ========================================================

    def get(
        self,
        pair,
        *,
        interval,
        data_range
    ):
        """
        Return cached data if it is still fresh.
        """

        key = self._make_key(
            pair,
            interval,
            data_range
        )

        entry = self._data.get(
            key
        )

        if entry is None:
            return None

        timestamp, value = entry

        age = time.monotonic() - timestamp

        if age > self.ttl_seconds:

            self._data.pop(
                key,
                None
            )

            return None

        return value

    # ========================================================
    # SET
    # ========================================================

    def set(
        self,
        pair,
        value,
        *,
        interval,
        data_range
    ):
        """
        Store market data in the cache.
        """

        key = self._make_key(
            pair,
            interval,
            data_range
        )

        self._data[key] = (
            time.monotonic(),
            value
        )

    # ========================================================
    # DELETE
    # ========================================================

    def delete(
        self,
        pair,
        *,
        interval,
        data_range
    ):
        """
        Remove one cached entry.
        """

        key = self._make_key(
            pair,
            interval,
            data_range
        )

        self._data.pop(
            key,
            None
        )

    # ========================================================
    # CLEAR
    # ========================================================

    def clear(self):
        """
        Remove all cached market data.
        """

        self._data.clear()

    # ========================================================
    # SIZE
    # ========================================================

    def size(self):
        """
        Return the number of cached entries.
        """

        return len(
            self._data
        )