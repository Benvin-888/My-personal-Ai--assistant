"""
APEX / BENVIN Market Provider Factory

Phase 2.6.1 - OANDA Provider Foundation

Creates explicitly selected market-data providers without
coupling the MarketDataService to a specific vendor.

Supported providers:
    - yahoo
    - oanda

No provider created by this module has trading/order authority.
"""

from .oanda import OANDAProvider
from .provider import MarketDataProvider, YahooFinanceProvider


SUPPORTED_PROVIDERS = {
    "yahoo": YahooFinanceProvider,
    "yahoo_finance": YahooFinanceProvider,
    "oanda": OANDAProvider,
}


def create_market_data_provider(name="yahoo", **kwargs) -> MarketDataProvider:
    """Create a market-data provider by explicit provider name."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Provider name must be a non-empty string.")

    key = name.strip().lower()
    provider_class = SUPPORTED_PROVIDERS.get(key)

    if provider_class is None:
        supported = ", ".join(sorted(set(SUPPORTED_PROVIDERS)))
        raise ValueError(
            f"Unsupported market provider '{name}'. Supported: {supported}."
        )

    return provider_class(**kwargs)
