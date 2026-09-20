from datetime import datetime, timezone, timedelta

from market.brain_market_service import (
    BrainMarketQuery,
    BrainMarketQueryError,
    BrainMarketQueryService,
)


BASE = datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc)


def history_payload():
    candles = []
    price = 1.1000
    for index in range(120):
        timestamp = BASE - timedelta(minutes=5 * (119 - index))
        close = price + index * 0.00002
        candles.append(
            {
                "timestamp": timestamp.timestamp(),
                "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
                "open": close - 0.00003,
                "high": close + 0.00004,
                "low": close - 0.00005,
                "close": close,
            }
        )
    return {
        "success": True,
        "market": "forex",
        "pair": "EURUSD",
        "provider": "TEST",
        "interval": "5m",
        "range": "1d",
        "retrieved_at": BASE.isoformat().replace("+00:00", "Z"),
        "candles": candles,
    }


class FakeMarketData:
    def get_forex_history(self, pair, *, provider=None, data_range="1d", interval="5m"):
        assert pair == "EURUSD"
        assert interval == "5m"
        return history_payload()

    def assess_observation_freshness(self, observation, *, assessed_at):
        return {
            "provider": observation["provider"],
            "freshness": {
                "status": "FRESH",
                "age_seconds": 60.0,
            },
        }

    def reliability_snapshot(self, provider=None):
        return {
            "provider": provider,
            "success_rate": 1.0,
            "consecutive_failures": 0,
            "total_checks": 1,
        }

    def assess_operational_state(self, **kwargs):
        return {
            "provider": kwargs["provider"],
            "pair": kwargs["pair"],
            "status": "HEALTHY",
            "analysis_usable": True,
            "freshness": "FRESH",
            "data_quality": "EXCELLENT",
            "data_quality_score": 100.0,
            "provider_health": None,
            "provider_health_success": None,
            "reliability_success_rate": 1.0,
            "reliability_consecutive_failures": 0,
            "reliability_total_checks": 1,
            "assessed_at": BASE.isoformat().replace("+00:00", "Z"),
        }


def test_query_normalizes_pair():
    query = BrainMarketQuery("q-1", "eur/usd")
    assert query.normalized_pair == "EURUSD"


def test_query_rejects_invalid_pair():
    try:
        BrainMarketQuery("q-1", "EUR")
    except BrainMarketQueryError:
        return
    raise AssertionError("invalid pair should be rejected")


def test_service_produces_read_only_market_result():
    result = BrainMarketQueryService(market_data=FakeMarketData()).evaluate(
        BrainMarketQuery("q-2", "EURUSD", "5m")
    )
    assert result.success is True
    payload = result.to_dict()
    assert payload["read_only"] is True
    assert payload["execution_authorized"] is False
    assert payload["market_intelligence"]["execution_authorized"] is False
    assert payload["market_intelligence"]["evidence_fingerprint"]


def test_service_does_not_require_broker_credentials():
    service = BrainMarketQueryService(market_data=FakeMarketData())
    assert not hasattr(service, "execute")
    assert not hasattr(service, "buy")
    assert not hasattr(service, "cancel")
    assert not hasattr(service, "sell")
