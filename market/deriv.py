"""
APEX / BENVIN Deriv WebSocket Market Provider

Phase 2.6.1 - Deriv WebSocket Market Foundation

Responsibilities:

    1. Connect to Deriv's public WebSocket API.
    2. Discover active market symbols.
    3. Resolve normalized Forex pairs to Deriv symbols.
    4. Retrieve the latest Forex tick.
    5. Return raw market information without trading authority.
    6. Keep provider communication behind the existing market layer.

This module does NOT:

    - authenticate a trading account
    - access balances or portfolios
    - place orders
    - sell contracts
    - modify any Deriv account
    - make trading decisions

Historical tick retrieval and tick-to-candle aggregation are later phases.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from .provider import MarketDataProvider, normalize_forex_pair


PROVIDER_NAME = "Deriv"
DEFAULT_ENDPOINT = "wss://ws.derivws.com/websockets/v3"
DEFAULT_APP_ID = "1089"
DEFAULT_TIMEOUT = 15


class DerivProviderError(RuntimeError):
    """Raised when Deriv WebSocket market communication fails."""


class DerivWebSocketProvider(MarketDataProvider):
    """
    Read-only Deriv market-data provider.

    The provider uses the public WebSocket market API and intentionally
    exposes only market-data operations in this phase.
    """

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        app_id: str | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: int | float = DEFAULT_TIMEOUT,
        connection_factory: Callable[..., Any] | None = None,
    ):
        resolved_app_id = app_id or os.getenv("DERIV_APP_ID") or DEFAULT_APP_ID

        if not isinstance(resolved_app_id, str) or not resolved_app_id.strip():
            raise ValueError("Deriv app_id must be a non-empty string.")

        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("Deriv endpoint must be a non-empty string.")

        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("Deriv timeout must be a positive number.")

        self.app_id = resolved_app_id.strip()
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.connection_factory = connection_factory
        self._request_lock = threading.Lock()

    @staticmethod
    def _utc_now() -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _connection_url(self) -> str:
        separator = "&" if "?" in self.endpoint else "?"
        return f"{self.endpoint}{separator}app_id={self.app_id}"

    def _default_connection_factory(self):
        try:
            import websocket
        except ImportError as exc:
            raise DerivProviderError(
                "Deriv WebSocket support requires the 'websocket-client' package. "
                "Install it with: pip install websocket-client"
            ) from exc

        return websocket.create_connection

    def _send_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or not payload:
            raise ValueError("Deriv request payload must be a non-empty dictionary.")

        factory = self.connection_factory or self._default_connection_factory()

        with self._request_lock:
            connection = None
            try:
                connection = factory(
                    self._connection_url(),
                    timeout=self.timeout,
                )
                connection.send(json.dumps(payload))
                raw_response = connection.recv()
            except DerivProviderError:
                raise
            except Exception as exc:
                raise DerivProviderError(
                    f"Deriv WebSocket request failed: {exc}"
                ) from exc
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass

        try:
            response = json.loads(raw_response)
        except (TypeError, json.JSONDecodeError) as exc:
            raise DerivProviderError(
                "Deriv returned an invalid JSON response."
            ) from exc

        if not isinstance(response, dict):
            raise DerivProviderError(
                "Deriv returned an unexpected response structure."
            )

        error = response.get("error")
        if isinstance(error, dict):
            code = error.get("code", "UnknownError")
            message = error.get("message", "Unknown Deriv API error.")
            raise DerivProviderError(f"Deriv API error {code}: {message}")

        return response

    def get_active_symbols(self, *, market: str | None = None) -> tuple[dict[str, Any], ...]:
        """Return active symbols available from Deriv's public market API."""

        payload: dict[str, Any] = {
            "active_symbols": "brief",
        }

        if market is not None:
            if not isinstance(market, str) or not market.strip():
                raise ValueError("market must be a non-empty string when provided.")
            payload["product_type"] = market.strip()

        response = self._send_request(payload)
        symbols = response.get("active_symbols")

        if not isinstance(symbols, list):
            raise DerivProviderError(
                "Deriv response did not contain an active_symbols list."
            )

        normalized_symbols = [
            item for item in symbols
            if isinstance(item, dict)
        ]

        return tuple(normalized_symbols)

    @staticmethod
    def _symbol_pair_candidate(symbol: dict[str, Any]) -> str | None:
        """Extract a six-letter Forex pair candidate from a Deriv symbol record."""

        for key in ("symbol", "display_name", "underlying_symbol"):
            value = symbol.get(key)
            if not isinstance(value, str):
                continue

            normalized = normalize_forex_pair(value)
            if normalized is not None:
                return normalized

        return None

    def forex_pair_to_provider_symbol(self, pair: str) -> str | None:
        """
        Resolve a normalized APEX Forex pair to a currently active Deriv symbol.

        Symbol discovery is used instead of hard-coding broker symbol names.
        """

        normalized_pair = normalize_forex_pair(pair)
        if normalized_pair is None:
            return None

        exact_matches: list[str] = []

        for symbol in self.get_active_symbols():
            candidate = self._symbol_pair_candidate(symbol)
            provider_symbol = symbol.get("symbol")

            if candidate == normalized_pair and isinstance(provider_symbol, str):
                exact_matches.append(provider_symbol)

        if not exact_matches:
            return None

        return sorted(exact_matches)[0]

    @staticmethod
    def _coerce_timestamp(value: Any) -> int:
        if isinstance(value, bool):
            raise DerivProviderError("Deriv tick epoch must be numeric.")

        if isinstance(value, (int, float)):
            return int(value)

        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError as exc:
                raise DerivProviderError(
                    "Deriv tick epoch is invalid."
                ) from exc

        raise DerivProviderError("Deriv tick epoch is missing.")

    @staticmethod
    def _coerce_price(value: Any) -> float:
        if isinstance(value, bool):
            raise DerivProviderError("Deriv tick quote must be numeric.")

        try:
            price = float(value)
        except (TypeError, ValueError) as exc:
            raise DerivProviderError(
                "Deriv tick quote is invalid."
            ) from exc

        if price <= 0:
            raise DerivProviderError("Deriv tick quote must be positive.")

        return price

    @staticmethod
    def _timestamp_to_utc(epoch: int) -> str:
        return (
            datetime.fromtimestamp(epoch, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def get_latest_tick(self, provider_symbol: str) -> dict[str, Any]:
        """Retrieve one latest public tick without opening a subscription stream."""

        if not isinstance(provider_symbol, str) or not provider_symbol.strip():
            raise ValueError("provider_symbol must be a non-empty string.")

        response = self._send_request(
            {
                "ticks": provider_symbol.strip(),
                "subscribe": 0,
            }
        )

        tick = response.get("tick")
        if not isinstance(tick, dict):
            raise DerivProviderError(
                "Deriv response did not contain a tick object."
            )

        epoch = self._coerce_timestamp(tick.get("epoch"))
        quote = self._coerce_price(tick.get("quote"))

        return {
            "provider": self.name,
            "provider_symbol": provider_symbol.strip(),
            "timestamp": epoch,
            "timestamp_utc": self._timestamp_to_utc(epoch),
            "price": quote,
            "raw_tick": tick,
            "retrieved_at": self._utc_now(),
        }

    def health_check(self) -> dict[str, Any]:
        """Perform a public, read-only Deriv API health check using ping."""

        started = time.monotonic()
        response = self._send_request({"ping": 1})
        latency_ms = round((time.monotonic() - started) * 1000, 3)

        if response.get("ping") != "pong":
            raise DerivProviderError(
                "Deriv health check returned an unexpected response."
            )

        return {
            "success": True,
            "provider": self.name,
            "status": "HEALTHY",
            "latency_ms": latency_ms,
            "checked_at": self._utc_now(),
        }

    # ----------------------------------------------------------------
    # Existing MarketDataProvider compatibility
    # ----------------------------------------------------------------

    def get_forex_quote(self, pair, *, data_range="1d", interval="5m"):
        """
        Not implemented in Phase 2.6.1.

        Deriv currently enters APEX as a tick-first provider. Converting ticks
        into the standardized OHLC quote model belongs to the later live candle
        engine phase, so this method intentionally does not fabricate candles.
        """

        raise DerivProviderError(
            "Deriv standardized OHLC quotes are not available in Phase 2.6.1. "
            "Use get_latest_tick() for read-only tick data."
        )

    def get_forex_history(self, pair, *, data_range="1d", interval="5m"):
        """Reserved for the later Deriv historical tick-data phase."""

        raise DerivProviderError(
            "Deriv historical retrieval is not available in Phase 2.6.1."
        )
