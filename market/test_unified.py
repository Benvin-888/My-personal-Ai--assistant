"""Tests for Phase 2.6.5 unified multi-provider market service."""

from __future__ import annotations

import pytest

from market.provider_registry import (
    ProviderAdapter,
    ProviderCapabilities,
    ProviderRegistry,
    ProviderRegistryError,
)
from market.unified import UnifiedMarketDataService


class FakeQuoteProvider:
    name = "Fake Quote"

    def get_forex_quote(self, pair, *, data_range="1d", interval="5m"):
        return {
            "provider": self.name,
            "provider_symbol": f"{pair}=FAKE",
            "pair": pair,
            "interval": interval,
            "range": data_range,
            "price": 1.25,
        }

    def get_forex_history(self, pair, *, data_range="1d", interval="5m"):
        return {
            "provider": self.name,
            "pair": pair,
            "interval": interval,
            "range": data_range,
            "candles": [],
        }


class FakeTickProvider:
    name = "Fake Tick"

    def forex_pair_to_provider_symbol(self, pair):
        return f"fx{pair}"

    def get_latest_tick(self, provider_symbol):
        return {
            "provider": self.name,
            "provider_symbol": provider_symbol,
            "timestamp": 100,
            "price": 1.5,
        }

    def health_check(self):
        return {
            "success": True,
            "provider": self.name,
            "status": "HEALTHY",
        }


def test_registry_resolves_aliases():
    registry = ProviderRegistry()
    adapter = ProviderAdapter(
        name="Test Provider",
        aliases=("test",),
        provider=object(),
        capabilities=ProviderCapabilities(quote=True),
    )
    registry.register(adapter)

    assert registry.get("test") is adapter
    assert registry.get("TEST PROVIDER") is adapter


def test_registry_rejects_duplicate_provider():
    registry = ProviderRegistry()
    adapter = ProviderAdapter(
        name="Test",
        provider=object(),
        capabilities=ProviderCapabilities(quote=True),
    )
    registry.register(adapter)

    with pytest.raises(ProviderRegistryError):
        registry.register(adapter)


def test_registry_can_replace_provider():
    registry = ProviderRegistry()
    first = ProviderAdapter(
        name="Test",
        provider=object(),
        capabilities=ProviderCapabilities(quote=True),
    )
    second = ProviderAdapter(
        name="Test",
        provider=object(),
        capabilities=ProviderCapabilities(history=True),
    )
    registry.register(first)
    registry.register(second, replace=True)

    assert registry.get("Test") is second


def test_registry_selects_by_capability_and_priority():
    registry = ProviderRegistry()
    slow = ProviderAdapter(
        name="Slow",
        provider=object(),
        capabilities=ProviderCapabilities(quote=True),
        priority=200,
    )
    fast = ProviderAdapter(
        name="Fast",
        provider=object(),
        capabilities=ProviderCapabilities(quote=True),
        priority=10,
    )
    registry.register(slow)
    registry.register(fast)

    assert registry.select("quote").name == "Fast"


def test_registry_explicit_provider_must_support_capability():
    registry = ProviderRegistry()
    registry.register(
        ProviderAdapter(
            name="Ticks",
            provider=object(),
            capabilities=ProviderCapabilities(latest_tick=True),
        )
    )

    with pytest.raises(ProviderRegistryError):
        registry.select("history", provider="Ticks")


def test_registry_describe_is_deterministic():
    registry = ProviderRegistry()
    registry.register(
        ProviderAdapter(
            name="B",
            provider=object(),
            capabilities=ProviderCapabilities(history=True),
            priority=20,
        )
    )
    registry.register(
        ProviderAdapter(
            name="A",
            provider=object(),
            capabilities=ProviderCapabilities(quote=True),
            priority=10,
        )
    )

    description = registry.describe()
    assert [item["name"] for item in description] == ["A", "B"]
    assert description[0]["capabilities"]["quote"] is True


def test_unified_quote_routes_to_capable_provider():
    service = UnifiedMarketDataService(
        ProviderRegistry(
            [
                ProviderAdapter(
                    name="Fake Quote",
                    provider=FakeQuoteProvider(),
                    capabilities=ProviderCapabilities(quote=True, history=True),
                )
            ]
        )
    )

    result = service.get_forex_quote("eur/usd")

    assert result["provider"] == "Fake Quote"
    assert result["pair"] == "EURUSD"
    assert result["price"] == 1.25


def test_unified_history_routes_to_capable_provider():
    service = UnifiedMarketDataService(
        ProviderRegistry(
            [
                ProviderAdapter(
                    name="Fake Quote",
                    provider=FakeQuoteProvider(),
                    capabilities=ProviderCapabilities(history=True),
                )
            ]
        )
    )

    result = service.get_forex_history("GBPUSD")

    assert result["provider"] == "Fake Quote"
    assert result["pair"] == "GBPUSD"


def test_unified_latest_tick_resolves_provider_symbol():
    service = UnifiedMarketDataService(
        ProviderRegistry(
            [
                ProviderAdapter(
                    name="Fake Tick",
                    provider=FakeTickProvider(),
                    capabilities=ProviderCapabilities(latest_tick=True, health=True),
                )
            ]
        )
    )

    result = service.get_latest_tick("EURUSD")

    assert result["provider"] == "Fake Tick"
    assert result["provider_symbol"] == "fxEURUSD"


def test_unified_health_routes_to_provider():
    service = UnifiedMarketDataService(
        ProviderRegistry(
            [
                ProviderAdapter(
                    name="Fake Tick",
                    provider=FakeTickProvider(),
                    capabilities=ProviderCapabilities(health=True),
                )
            ]
        )
    )

    result = service.health_check()
    assert result["success"] is True
    assert result["status"] == "HEALTHY"


def test_invalid_pair_is_rejected_before_provider_call():
    service = UnifiedMarketDataService(
        ProviderRegistry(
            [
                ProviderAdapter(
                    name="Fake Quote",
                    provider=FakeQuoteProvider(),
                    capabilities=ProviderCapabilities(quote=True),
                )
            ]
        )
    )

    result = service.get_forex_quote("NOT_A_PAIR")

    assert result["success"] is False
    assert "Invalid Forex pair" in result["error"]


def test_missing_capability_returns_structured_error():
    service = UnifiedMarketDataService(
        ProviderRegistry(
            [
                ProviderAdapter(
                    name="Fake Quote",
                    provider=FakeQuoteProvider(),
                    capabilities=ProviderCapabilities(quote=True),
                )
            ]
        )
    )

    result = service.get_latest_tick("EURUSD")

    assert result["success"] is False
    assert "latest_tick" in result["error"]


def test_explicit_provider_selection_overrides_priority():
    low = FakeQuoteProvider()
    high = FakeQuoteProvider()
    low.name = "Low"
    high.name = "High"

    registry = ProviderRegistry(
        [
            ProviderAdapter(
                name="Low",
                provider=low,
                capabilities=ProviderCapabilities(quote=True),
                priority=1,
            ),
            ProviderAdapter(
                name="High",
                provider=high,
                capabilities=ProviderCapabilities(quote=True),
                priority=100,
            ),
        ]
    )
    service = UnifiedMarketDataService(registry)

    result = service.get_forex_quote("EURUSD", provider="High")

    assert result["provider"] == "High"


def test_unknown_provider_returns_structured_error():
    service = UnifiedMarketDataService(
        ProviderRegistry(
            [
                ProviderAdapter(
                    name="Fake",
                    provider=FakeQuoteProvider(),
                    capabilities=ProviderCapabilities(quote=True),
                )
            ]
        )
    )

    result = service.get_forex_quote("EURUSD", provider="Missing")

    assert result["success"] is False
    assert "Unknown market-data provider" in result["error"]


def test_default_registry_exposes_separate_provider_capabilities(monkeypatch):
    monkeypatch.setattr("market.unified.YahooFinanceProvider", lambda: FakeQuoteProvider())
    monkeypatch.setattr("market.unified.DerivWebSocketProvider", lambda: FakeTickProvider())

    service = UnifiedMarketDataService.with_defaults()
    descriptions = {item["name"]: item for item in service.describe_providers()}

    assert descriptions["Yahoo Finance"]["capabilities"]["quote"] is True
    assert descriptions["Deriv"]["capabilities"]["latest_tick"] is True
    assert descriptions["Deriv"]["capabilities"]["live_ticks"] is True
    assert descriptions["Deriv"]["capabilities"]["quote"] is False


def test_default_registry_does_not_fabricate_deriv_ohlc_capability(monkeypatch):
    monkeypatch.setattr("market.unified.YahooFinanceProvider", lambda: FakeQuoteProvider())
    monkeypatch.setattr("market.unified.DerivWebSocketProvider", lambda: FakeTickProvider())

    service = UnifiedMarketDataService.with_defaults()
    result = service.get_forex_quote("EURUSD", provider="Deriv")

    assert result["success"] is False
    assert "quote" in result["error"]


def test_provider_registry_unregisters_provider():
    registry = ProviderRegistry()
    adapter = ProviderAdapter(
        name="Test",
        provider=object(),
        capabilities=ProviderCapabilities(quote=True),
    )
    registry.register(adapter)

    removed = registry.unregister("Test")

    assert removed is adapter
    with pytest.raises(ProviderRegistryError):
        registry.get("Test")
