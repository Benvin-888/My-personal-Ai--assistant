"""Tests for Phase 2.6.2 Deriv Historical Tick Data."""

import json

import pytest

from market.deriv import DerivProviderError, DerivWebSocketProvider
from market.deriv_history import DerivHistoricalTickProvider


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
        captured.append(
            {
                "url": url,
                "timeout": timeout,
                "connection": connection,
            }
        )
        return connection

    return factory


def connection_factory_for_sequence(responses, captured):
    queue = list(responses)

    def factory(url, timeout):
        if not queue:
            raise AssertionError("Unexpected extra WebSocket request.")

        connection = FakeConnection(queue.pop(0))
        captured.append(
            {
                "url": url,
                "timeout": timeout,
                "connection": connection,
            }
        )
        return connection

    return factory


def symbol_response(symbol="frxEURUSD", display_name="EUR/USD"):
    return {
        "active_symbols": [
            {
                "symbol": symbol,
                "display_name": display_name,
            }
        ]
    }


def test_historical_ticks_are_retrieved_and_normalized():
    captured = []
    provider = DerivWebSocketProvider(
        connection_factory=connection_factory_for_sequence(
            [
                symbol_response(),
                {
                    "history": {
                        "times": [
                            1760000002,
                            1760000000,
                            1760000001,
                        ],
                        "prices": [
                            "1.17347",
                            "1.17345",
                            "1.17346",
                        ],
                    }
                },
            ],
            captured,
        ),
    )

    history = DerivHistoricalTickProvider(provider).get_forex_history(
        "eur/usd",
        count=3,
    )

    assert history["success"] is True
    assert history["data_type"] == "historical_ticks"
    assert history["pair"] == "EURUSD"
    assert history["provider_symbol"] == "frxEURUSD"
    assert history["tick_count"] == 3
    assert [tick["timestamp"] for tick in history["ticks"]] == [
        1760000000,
        1760000001,
        1760000002,
    ]
    assert history["ticks"][0]["price"] == pytest.approx(1.17345)
    assert history["ticks"][0]["timestamp_utc"].endswith("Z")
    assert captured[0]["connection"].sent == [
        {"active_symbols": "brief"}
    ]
    assert captured[1]["connection"].sent == [
        {
            "ticks_history": "frxEURUSD",
            "style": "ticks",
            "subscribe": 0,
            "count": 3,
        }
    ]
    assert captured[1]["connection"].closed is True


def test_start_end_range_is_sent_without_fabricating_candles():
    captured = []
    provider = DerivWebSocketProvider(
        connection_factory=connection_factory_for_sequence(
            [
                symbol_response("frxGBPUSD", "GBP/USD"),
                {
                    "history": {
                        "times": [1760000000, 1760000060],
                        "prices": [1.17345, 1.17350],
                    }
                },
            ],
            captured,
        ),
    )

    history = DerivHistoricalTickProvider(provider).get_forex_history(
        "GBPUSD",
        start=1760000000,
        end=1760000060,
    )

    assert history["tick_count"] == 2
    assert "candles" not in history
    assert captured[1]["connection"].sent == [
        {
            "ticks_history": "frxGBPUSD",
            "style": "ticks",
            "subscribe": 0,
            "start": 1760000000,
            "end": 1760000060,
        }
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"count": 0},
        {"count": 5001},
        {"start": 100, "end": 99},
        {"start": 100},
        {"end": 100},
        {},
    ],
)
def test_invalid_historical_request_is_rejected(kwargs):
    provider = DerivHistoricalTickProvider(
        DerivWebSocketProvider(
            connection_factory=lambda url, timeout: None,
        )
    )

    with pytest.raises((ValueError, DerivProviderError)):
        provider.get_forex_history("EURUSD", **kwargs)


def test_mismatched_history_arrays_are_rejected():
    captured = []
    provider = DerivWebSocketProvider(
        connection_factory=connection_factory_for_sequence(
            [
                symbol_response(),
                {
                    "history": {
                        "times": [1760000000, 1760000001],
                        "prices": [1.17345],
                    }
                },
            ],
            captured,
        ),
    )

    with pytest.raises(
        DerivProviderError,
        match="mismatched",
    ):
        DerivHistoricalTickProvider(provider).get_forex_history(
            "EURUSD",
            count=2,
        )


def test_invalid_tick_price_is_rejected():
    provider = DerivWebSocketProvider(
        connection_factory=connection_factory_for_sequence(
            [
                symbol_response(),
                {
                    "history": {
                        "times": [1760000000],
                        "prices": [0],
                    }
                },
            ],
            [],
        ),
    )

    with pytest.raises(
        DerivProviderError,
        match="greater than zero",
    ):
        DerivHistoricalTickProvider(provider).get_forex_history(
            "EURUSD",
            count=1,
        )


def test_invalid_tick_timestamp_is_rejected():
    provider = DerivWebSocketProvider(
        connection_factory=connection_factory_for_sequence(
            [
                symbol_response(),
                {
                    "history": {
                        "times": ["not-a-timestamp"],
                        "prices": [1.17345],
                    }
                },
            ],
            [],
        ),
    )

    with pytest.raises(
        DerivProviderError,
        match="timestamp",
    ):
        DerivHistoricalTickProvider(provider).get_forex_history(
            "EURUSD",
            count=1,
        )


def test_deriv_api_error_is_preserved():
    provider = DerivWebSocketProvider(
        connection_factory=connection_factory_for_sequence(
            [
                symbol_response(),
                {
                    "error": {
                        "code": "InvalidSymbol",
                        "message": "Unknown symbol",
                    }
                },
            ],
            [],
        ),
    )

    with pytest.raises(DerivProviderError, match="InvalidSymbol"):
        DerivHistoricalTickProvider(provider).get_forex_history(
            "EURUSD",
            count=10,
        )
