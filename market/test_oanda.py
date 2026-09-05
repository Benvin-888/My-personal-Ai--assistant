"""Unit tests for the read-only OANDA provider."""

from unittest.mock import Mock

import pytest

from .models import Candle
from .oanda import OANDAConfigurationError, OANDAProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def make_provider(payload):
    session = Mock()
    session.get.return_value = FakeResponse(payload)
    return OANDAProvider(
        api_token="token",
        account_id="account",
        environment="practice",
        session=session,
    ), session


def test_symbol_conversion():
    assert OANDAProvider.forex_pair_to_provider_symbol("EURUSD") == "EUR_USD"
    assert OANDAProvider.forex_pair_to_provider_symbol("eur/usd") == "EUR_USD"
    assert OANDAProvider.forex_pair_to_provider_symbol("BAD") is None


def test_interval_mapping():
    assert OANDAProvider.interval_to_granularity("5m") == "M5"
    assert OANDAProvider.interval_to_granularity("1h") == "H1"
    assert OANDAProvider.interval_to_granularity("1d") == "D"
    assert OANDAProvider.interval_to_granularity("90m") is None


def test_missing_credentials_are_rejected():
    provider = OANDAProvider(
        api_token=None,
        account_id=None,
        environment="practice",
    )
    with pytest.raises(OANDAConfigurationError):
        provider.get_forex_quote("EURUSD")


def test_quote_uses_bid_ask_midpoint():
    payload = {
        "prices": [{
            "instrument": "EUR_USD",
            "time": "2026-09-07T12:00:00.000000000Z",
            "status": "tradeable",
            "bids": [{"price": "1.1000"}],
            "asks": [{"price": "1.1002"}],
        }]
    }
    provider, session = make_provider(payload)
    result = provider.get_forex_quote("EURUSD")

    assert isinstance(result["candle"], Candle)
    assert result["bid"] == 1.1
    assert result["ask"] == 1.1002
    assert result["candle"].close == pytest.approx(1.1001)
    assert result["spread"] == pytest.approx(0.0002)
    session.get.assert_called_once()


def test_history_normalizes_oanda_candles():
    payload = {
        "instrument": "EUR_USD",
        "granularity": "M5",
        "candles": [
            {
                "time": "2026-09-07T12:00:00.000000000Z",
                "complete": True,
                "volume": 10,
                "mid": {"o": "1.1000", "h": "1.1010", "l": "1.0990", "c": "1.1005"},
            },
            {
                "time": "2026-09-07T12:05:00.000000000Z",
                "complete": False,
                "volume": 11,
                "mid": {"o": "1.1005", "h": "1.1015", "l": "1.1000", "c": "1.1010"},
            },
        ],
    }
    provider, _ = make_provider(payload)
    result = provider.get_forex_history("EURUSD", data_range="1d", interval="5m")

    assert result["provider"] == "OANDA"
    assert result["provider_symbol"] == "EUR_USD"
    assert result["data"]["timestamp"] == ["2026-09-07T12:00:00.000000000Z"]
    assert result["data"]["indicators"]["quote"][0]["close"] == [1.1005]


def test_live_environment_uses_live_base_url():
    provider = OANDAProvider(
        api_token="token",
        account_id="account",
        environment="live",
    )
    assert provider.base_url == "https://api-fxtrade.oanda.com"
