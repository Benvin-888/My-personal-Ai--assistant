"""Tests for Phase 2.6.1 Deriv WebSocket Market Foundation."""

import json

import pytest

from market.deriv import DerivProviderError, DerivWebSocketProvider


class FakeConnection:
    def __init__(self, response):
        self.response = response
        self.sent = []
        self.closed = False

    def send(self, payload):
        self.sent.append(json.loads(payload))

    def recv(self):
        return json.dumps(self.response)

    def close(self):
        self.closed = True


def connection_factory_for(response, captured):
    def factory(url, timeout):
        connection = FakeConnection(response)
        captured.append({
            "url": url,
            "timeout": timeout,
            "connection": connection,
        })
        return connection
    return factory


def test_active_symbols_returns_normalized_records():
    captured = []
    provider = DerivWebSocketProvider(
        app_id="12345",
        connection_factory=connection_factory_for(
            {
                "active_symbols": [
                    {"symbol": "frxEURUSD", "display_name": "EUR/USD"},
                    "invalid-row",
                ]
            },
            captured,
        ),
    )

    result = provider.get_active_symbols()

    assert result == (
        {"symbol": "frxEURUSD", "display_name": "EUR/USD"},
    )
    assert captured[0]["connection"].sent == [
        {"active_symbols": "brief"}
    ]
    assert "app_id=12345" in captured[0]["url"]
    assert captured[0]["connection"].closed is True


def test_forex_pair_to_provider_symbol_discovers_symbol():
    captured = []
    provider = DerivWebSocketProvider(
        connection_factory=connection_factory_for(
            {
                "active_symbols": [
                    {"symbol": "frxGBPUSD", "display_name": "GBP/USD"},
                    {"symbol": "frxEURUSD", "display_name": "EUR/USD"},
                ]
            },
            captured,
        ),
    )

    assert provider.forex_pair_to_provider_symbol("eur/usd") == "frxEURUSD"


def test_latest_tick_returns_standardized_tick_data():
    captured = []
    provider = DerivWebSocketProvider(
        connection_factory=connection_factory_for(
            {
                "tick": {
                    "epoch": 1760000000,
                    "quote": "1.17345",
                }
            },
            captured,
        ),
    )

    result = provider.get_latest_tick("frxEURUSD")

    assert result["provider"] == "Deriv"
    assert result["provider_symbol"] == "frxEURUSD"
    assert result["timestamp"] == 1760000000
    assert result["timestamp_utc"].endswith("Z")
    assert result["price"] == pytest.approx(1.17345)
    assert captured[0]["connection"].sent == [
        {"ticks": "frxEURUSD", "subscribe": 0}
    ]


def test_health_check_uses_public_ping():
    captured = []
    provider = DerivWebSocketProvider(
        connection_factory=connection_factory_for(
            {"ping": "pong"},
            captured,
        ),
    )

    result = provider.health_check()

    assert result["success"] is True
    assert result["provider"] == "Deriv"
    assert result["status"] == "HEALTHY"
    assert result["latency_ms"] >= 0
    assert captured[0]["connection"].sent == [{"ping": 1}]


def test_deriv_api_error_is_raised():
    provider = DerivWebSocketProvider(
        connection_factory=connection_factory_for(
            {
                "error": {
                    "code": "InvalidSymbol",
                    "message": "Unknown symbol",
                }
            },
            [],
        ),
    )

    with pytest.raises(DerivProviderError, match="InvalidSymbol"):
        provider.get_latest_tick("missing")


def test_phase_261_does_not_fabricate_ohlc_data():
    provider = DerivWebSocketProvider(
        connection_factory=lambda url, timeout: None,
    )

    with pytest.raises(DerivProviderError, match="not available"):
        provider.get_forex_quote("EURUSD")

    with pytest.raises(DerivProviderError, match="historical retrieval"):
        provider.get_forex_history("EURUSD")
