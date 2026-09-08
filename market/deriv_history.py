"""
APEX / BENVIN Deriv Historical Tick Provider

Phase 2.6.2 - Deriv Historical Tick Data

This is an additive layer over the Phase 2.6.1 Deriv provider.

Responsibilities:
    - validate historical-tick request parameters
    - resolve a normalized Forex pair to a discovered Deriv symbol
    - request one-shot historical tick data
    - validate timestamps and prices
    - normalize timestamps to UTC
    - return deterministic chronological tick records

This module does NOT:
    - create OHLC candles
    - subscribe to a live stream
    - authenticate an account
    - read balances or portfolios
    - place or sell contracts
    - make trading decisions
"""

from __future__ import annotations

from typing import Any

from .deriv import DerivProviderError, DerivWebSocketProvider
from .provider import normalize_forex_pair
from .ticks import ForexTickHistory, HistoricalTick


MAX_HISTORICAL_TICKS = 5_000


class DerivHistoricalTickProvider:
    """
    Historical tick retrieval service built on the existing
    read-only DerivWebSocketProvider.
    """

    def __init__(
        self,
        provider: DerivWebSocketProvider | None = None,
        *,
        max_ticks: int = MAX_HISTORICAL_TICKS,
    ) -> None:
        if not isinstance(max_ticks, int) or isinstance(max_ticks, bool):
            raise ValueError("max_ticks must be an integer.")

        if max_ticks <= 0:
            raise ValueError("max_ticks must be greater than zero.")

        if max_ticks > MAX_HISTORICAL_TICKS:
            raise ValueError(
                f"max_ticks cannot exceed {MAX_HISTORICAL_TICKS}."
            )

        self.provider = provider or DerivWebSocketProvider()
        self.max_ticks = max_ticks

    @staticmethod
    def _validate_epoch(value: Any, field_name: str) -> int:
        if isinstance(value, bool):
            raise DerivProviderError(
                f"{field_name} must be an integer Unix timestamp."
            )

        if isinstance(value, int):
            epoch = value
        elif isinstance(value, float):
            if not value.is_integer():
                raise DerivProviderError(
                    f"{field_name} must contain a whole Unix timestamp."
                )
            epoch = int(value)
        elif isinstance(value, str):
            try:
                numeric = float(value.strip())
            except (TypeError, ValueError):
                raise DerivProviderError(
                    f"{field_name} must be a valid Unix timestamp."
                ) from None

            if not numeric.is_integer():
                raise DerivProviderError(
                    f"{field_name} must contain a whole Unix timestamp."
                )
            epoch = int(numeric)
        else:
            raise DerivProviderError(
                f"{field_name} must be a valid Unix timestamp."
            )

        if epoch < 0:
            raise DerivProviderError(
                f"{field_name} cannot be negative."
            )

        return epoch

    def _validate_request(
        self,
        pair: str,
        count: int | None,
        start: int | None,
        end: int | None,
    ) -> str:
        normalized = normalize_forex_pair(pair)

        if normalized is None:
            raise ValueError(
                "Invalid Forex pair. Use a six-letter pair such as EURUSD."
            )

        if count is not None:
            if not isinstance(count, int) or isinstance(count, bool):
                raise ValueError("count must be an integer.")
            if count <= 0:
                raise ValueError("count must be greater than zero.")
            if count > self.max_ticks:
                raise ValueError(
                    f"count cannot exceed {self.max_ticks}."
                )

        if start is not None:
            start = self._validate_epoch(start, "start")

        if end is not None:
            end = self._validate_epoch(end, "end")

        if start is not None and end is not None and start > end:
            raise ValueError("start cannot be greater than end.")

        if count is None and start is None and end is None:
            raise ValueError(
                "Historical tick retrieval requires count or a start/end range."
            )

        if start is not None and end is None:
            raise ValueError(
                "end is required when start is provided."
            )

        if end is not None and start is None:
            raise ValueError(
                "start is required when end is provided."
            )

        return normalized

    @staticmethod
    def _extract_history(response: dict[str, Any]) -> tuple[list[Any], list[Any]]:
        history = response.get("history")
        if not isinstance(history, dict):
            raise DerivProviderError(
                "Deriv response did not contain a history object."
            )

        times = history.get("times")
        prices = history.get("prices")

        if not isinstance(times, list) or not isinstance(prices, list):
            raise DerivProviderError(
                "Deriv historical response must contain times and prices lists."
            )

        if len(times) != len(prices):
            raise DerivProviderError(
                "Deriv historical response contains mismatched times and prices."
            )

        return times, prices

    @staticmethod
    def _coerce_price(value: Any) -> float:
        if isinstance(value, bool):
            raise DerivProviderError("Historical tick price is invalid.")

        try:
            price = float(value)
        except (TypeError, ValueError):
            raise DerivProviderError(
                "Historical tick price is invalid."
            ) from None

        if price <= 0:
            raise DerivProviderError(
                "Historical tick price must be greater than zero."
            )

        return price

    def get_forex_history(
        self,
        pair: str,
        *,
        count: int | None = None,
        start: int | None = None,
        end: int | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve historical Forex ticks.

        Exactly one request is made. The response is normalized into
        ForexTickHistory. No candles are constructed.
        """

        normalized = self._validate_request(
            pair,
            count,
            start,
            end,
        )

        provider_symbol = self.provider.forex_pair_to_provider_symbol(
            normalized
        )

        if not provider_symbol:
            raise DerivProviderError(
                f"No Deriv symbol was discovered for Forex pair {normalized}."
            )

        payload: dict[str, Any] = {
            "ticks_history": provider_symbol,
            "style": "ticks",
            "subscribe": 0,
        }

        if count is not None:
            payload["count"] = count

        if start is not None:
            payload["start"] = start

        if end is not None:
            payload["end"] = end

        response = self.provider._send_request(payload)
        times, prices = self._extract_history(response)

        ticks: list[HistoricalTick] = []

        for raw_time, raw_price in zip(times, prices):
            timestamp = self._validate_epoch(
                raw_time,
                "historical tick timestamp",
            )
            price = self._coerce_price(raw_price)

            ticks.append(
                HistoricalTick(
                    timestamp=timestamp,
                    timestamp_utc=self.provider._timestamp_to_utc(timestamp),
                    price=price,
                    provider=self.provider.name,
                    provider_symbol=provider_symbol,
                    raw_tick={
                        "epoch": raw_time,
                        "price": raw_price,
                    },
                )
            )

        ticks.sort(key=lambda tick: tick.timestamp)

        result = ForexTickHistory(
            pair=normalized,
            base_currency=normalized[:3],
            quote_currency=normalized[3:],
            provider_symbol=provider_symbol,
            provider=self.provider.name,
            ticks=tuple(ticks),
            requested_count=count,
            start_timestamp=start,
            end_timestamp=end,
            retrieved_at=self.provider._utc_now(),
        )

        return result.to_dict()
