"""Tests for explicit market provider selection."""

import pytest

from .oanda import OANDAProvider
from .provider import YahooFinanceProvider
from .provider_factory import create_market_data_provider


def test_create_yahoo_provider():
    provider = create_market_data_provider("yahoo")
    assert isinstance(provider, YahooFinanceProvider)


def test_create_oanda_provider():
    provider = create_market_data_provider(
        "oanda",
        api_token="token",
        account_id="account",
        environment="practice",
    )
    assert isinstance(provider, OANDAProvider)
    assert provider.environment == "practice"


def test_provider_name_is_case_insensitive():
    provider = create_market_data_provider(
        "OANDA",
        api_token="token",
        account_id="account",
    )
    assert isinstance(provider, OANDAProvider)


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        create_market_data_provider("unknown")
