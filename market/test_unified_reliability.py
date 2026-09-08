"""Phase 2.6.7 integration tests for unified reliability monitoring."""

from datetime import datetime, timezone, timedelta

from market.provider_registry import ProviderAdapter, ProviderCapabilities, ProviderRegistry
from market.reliability import FreshnessPolicy, ProviderReliabilityMonitor
from market.unified import UnifiedMarketDataService


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeQuoteProvider:
    name = "Fake Quote"

    def get_forex_quote(self, pair, *, data_range="1d", interval="5m"):
        return {
            "provider": self.name,
            "provider_symbol": f"{pair}=FAKE",
            "pair": pair,
            "interval": interval,
            "range": data_range,
            "candle": {
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "open": 1.2,
                "high": 1.3,
                "low": 1.1,
                "close": 1.25,
            },
        }


class FailingQuoteProvider(FakeQuoteProvider):
    name = "Failing Quote"

    def get_forex_quote(self, pair, *, data_range="1d", interval="5m"):
        raise RuntimeError("provider unavailable")


class FakeTickProvider:
    name = "Fake Tick"

    def forex_pair_to_provider_symbol(self, pair):
        return f"fx{pair}"

    def get_latest_tick(self, provider_symbol):
        return {
            "provider": self.name,
            "provider_symbol": provider_symbol,
            "timestamp": 1767225600,
            "timestamp_utc": "2026-01-01T00:00:00Z",
            "price": 1.5,
            "retrieved_at": "2026-01-01T00:00:01Z",
        }

    def health_check(self):
        return {"success": True, "provider": self.name, "status": "HEALTHY"}


def service(provider, capabilities):
    return UnifiedMarketDataService(
        ProviderRegistry(
            [ProviderAdapter(name=provider.name, provider=provider, capabilities=capabilities)]
        )
    )


def test_quote_records_success_and_attaches_freshness():
    svc = service(FakeQuoteProvider(), ProviderCapabilities(quote=True))
    svc._utc_now = lambda: BASE + timedelta(seconds=1)
    result = svc.get_forex_quote("EURUSD")
    snap = svc.reliability_snapshot("Fake Quote")

    assert result["freshness"]["status"] == "FRESH"
    assert snap["total_checks"] == 1
    assert snap["successful_checks"] == 1
    assert snap["failed_checks"] == 0
    assert snap["average_latency_ms"] is not None


def test_quote_failure_records_failed_check():
    svc = service(FailingQuoteProvider(), ProviderCapabilities(quote=True))
    result = svc.get_forex_quote("EURUSD")
    snap = svc.reliability_snapshot("Failing Quote")

    assert result["success"] is False
    assert snap["total_checks"] == 1
    assert snap["failed_checks"] == 1
    assert snap["consecutive_failures"] == 1


def test_latest_tick_records_success_and_attaches_freshness():
    svc = service(FakeTickProvider(), ProviderCapabilities(latest_tick=True))
    svc._utc_now = lambda: BASE + timedelta(seconds=1)
    result = svc.get_latest_tick("EURUSD")
    snap = svc.reliability_snapshot("Fake Tick")

    assert result["freshness"]["status"] == "FRESH"
    assert snap["successful_checks"] == 1


def test_health_check_records_provider_result():
    svc = service(FakeTickProvider(), ProviderCapabilities(health=True))
    result = svc.health_check()
    snap = svc.reliability_snapshot("Fake Tick")

    assert result["success"] is True
    assert snap["total_checks"] == 1
    assert snap["successful_checks"] == 1


def test_reliability_snapshot_all_is_available():
    monitor = ProviderReliabilityMonitor()
    svc = UnifiedMarketDataService(
        ProviderRegistry(
            [
                ProviderAdapter(
                    name="B", provider=object(), capabilities=ProviderCapabilities()
                ),
                ProviderAdapter(
                    name="A", provider=object(), capabilities=ProviderCapabilities()
                ),
            ]
        ),
        reliability_monitor=monitor,
    )
    monitor.record_check("B", success=True, checked_at=BASE)
    monitor.record_check("A", success=True, checked_at=BASE)
    snapshots = svc.reliability_snapshot()
    assert [item["provider"] for item in snapshots] == ["A", "B"]


def test_custom_freshness_policy_is_used_for_quote():
    svc = service(FakeQuoteProvider(), ProviderCapabilities(quote=True))
    svc.freshness_policy = FreshnessPolicy(0.0 + 0.1, 1.0, 2.0)
    result = svc.assess_observation_freshness(
        {"provider": "Fake Quote", "timestamp_utc": "2026-01-01T00:00:00Z"},
        assessed_at=BASE + timedelta(seconds=1.5),
    )
    assert result["freshness"]["status"] == "VERY_STALE"


def test_direct_freshness_assessment_remains_available():
    svc = service(FakeQuoteProvider(), ProviderCapabilities(quote=True))
    result = svc.assess_observation_freshness(
        {"provider": "Fake Quote", "timestamp_utc": "2026-01-01T00:00:00Z"},
        assessed_at=BASE + timedelta(seconds=3),
    )
    assert result["freshness"]["status"] == "FRESH"


def test_monitor_is_injected_not_replaced():
    monitor = ProviderReliabilityMonitor()
    svc = UnifiedMarketDataService(
        ProviderRegistry(),
        reliability_monitor=monitor,
    )
    assert svc.reliability_monitor is monitor
