"""
APEX / BENVIN Unified Multi-Provider Market Service

Phase 2.6.5

This service is the provider-neutral market-data gateway for APEX.
It routes requests by explicit provider capability instead of making
higher layers depend on Yahoo Finance, Deriv, or any future provider.

The service deliberately does NOT:
    - authenticate trading accounts
    - read balances or portfolios
    - place/cancel/sell trades
    - select strategies
    - generate trading signals
    - calculate position size
    - make profitability claims

Market-data facts must originate from a registered provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any, Callable, Mapping

from .deriv import DerivWebSocketProvider
from .deriv_stream import DerivTickStream
from .models import MarketDataError
from .provider import YahooFinanceProvider, normalize_forex_pair
from .reliability import (
    FreshnessPolicy,
    ProviderReliabilityMonitor,
    assess_provider_observation,
)
from .operational_state import (
    MarketOperationalStateEngine,
    OperationalStatePolicy,
)
from .provider_registry import (
    ProviderAdapter,
    ProviderCapabilities,
    ProviderRegistry,
    ProviderRegistryError,
)


@dataclass(frozen=True)
class UnifiedServiceResult:
    """Optional diagnostic envelope for provider-routing operations."""

    success: bool
    provider: str | None
    operation: str
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "provider": self.provider,
            "operation": self.operation,
            "data": self.data,
            "error": self.error,
        }


class UnifiedMarketDataService:
    """Capability-aware gateway over multiple market-data providers."""

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        *,
        reliability_monitor: ProviderReliabilityMonitor | None = None,
        freshness_policy: FreshnessPolicy | None = None,
    ):
        self.registry = registry or ProviderRegistry()
        self.reliability_monitor = reliability_monitor or ProviderReliabilityMonitor()
        self.freshness_policy = freshness_policy or FreshnessPolicy()

    @classmethod
    def with_defaults(
        cls,
        *,
        yahoo: YahooFinanceProvider | None = None,
        deriv: DerivWebSocketProvider | None = None,
        include_yahoo: bool = True,
        include_deriv: bool = True,
    ) -> "UnifiedMarketDataService":
        """Create the standard APEX market-data registry.

        Yahoo is the current standardized OHLC provider. Deriv is the
        tick-first provider and therefore advertises tick/live capabilities,
        not fabricated OHLC capabilities.
        """

        registry = ProviderRegistry()

        if include_yahoo:
            yahoo_provider = yahoo or YahooFinanceProvider()
            registry.register(
                ProviderAdapter(
                    name="Yahoo Finance",
                    aliases=("yahoo", "yahoo finance"),
                    provider=yahoo_provider,
                    capabilities=ProviderCapabilities(
                        quote=True,
                        history=True,
                        health=False,
                    ),
                    priority=100,
                )
            )

        if include_deriv:
            deriv_provider = deriv or DerivWebSocketProvider()
            registry.register(
                ProviderAdapter(
                    name="Deriv",
                    aliases=("deriv",),
                    provider=deriv_provider,
                    capabilities=ProviderCapabilities(
                        latest_tick=True,
                        live_ticks=True,
                        health=True,
                    ),
                    priority=100,
                )
            )

        return cls(registry)

    @staticmethod
    def _invalid_pair(pair: Any) -> dict[str, Any] | None:
        normalized = normalize_forex_pair(pair)
        if normalized is None:
            return MarketDataError(
                market="forex",
                pair=str(pair) if pair is not None else None,
                error="Invalid Forex pair. Use a six-letter pair such as EURUSD.",
            ).to_dict()
        return None

    @staticmethod
    def _unsupported(provider: str, operation: str) -> dict[str, Any]:
        return MarketDataError(
            market="forex",
            provider=provider,
            error=f"Provider '{provider}' does not support '{operation}'.",
        ).to_dict()

    @staticmethod
    def _provider_failure(provider: str, operation: str, exc: Exception) -> dict[str, Any]:
        return MarketDataError(
            market="forex",
            provider=provider,
            error=f"Provider '{provider}' failed during {operation}: {exc}",
        ).to_dict()

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def _record_provider_check(
        self,
        provider: str,
        *,
        success: bool,
        started: float,
        checked_at: datetime | None = None,
    ) -> None:
        """Record an observed provider operation without changing its result."""
        self.reliability_monitor.record_check(
            provider,
            success=success,
            checked_at=checked_at or self._utc_now(),
            latency_ms=(time.monotonic() - started) * 1000,
        )

    def _attach_freshness(
        self,
        observation: Mapping[str, Any],
        *,
        assessed_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Return a copy of an observation with deterministic freshness metadata."""
        result = dict(observation)
        try:
            result["freshness"] = assess_provider_observation(
                result,
                assessed_at=assessed_at or self._utc_now(),
                policy=self.freshness_policy,
            )["freshness"]
        except Exception:
            # Freshness assessment must never destroy an otherwise valid market
            # observation. Missing/invalid timestamps remain explicitly unknown
            # or are surfaced by the standalone reliability API.
            pass
        return result

    def reliability_snapshot(self, provider: str | None = None) -> Any:
        """Return reliability statistics for one provider or all providers."""
        if provider is None:
            return tuple(
                snapshot.to_dict()
                for snapshot in self.reliability_monitor.snapshot_all()
            )
        adapter = self.registry.get(provider)
        return self.reliability_monitor.snapshot(adapter.name).to_dict()

    def assess_observation_freshness(
        self,
        observation: Mapping[str, Any],
        *,
        assessed_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Assess freshness of a normalized point-in-time provider observation."""
        return assess_provider_observation(
            observation,
            assessed_at=assessed_at or self._utc_now(),
            policy=self.freshness_policy,
        )

    def assess_operational_state(
        self,
        *,
        provider: str,
        pair: str | None = None,
        assessed_at: datetime | None = None,
        freshness: Mapping[str, Any] | None = None,
        data_quality: Mapping[str, Any] | None = None,
        provider_health: Mapping[str, Any] | None = None,
        reliability: Mapping[str, Any] | None = None,
        policy: OperationalStatePolicy | None = None,
    ) -> dict[str, Any]:
        """Assess unified market-data operational readiness.

        This method combines already-observed facts only. It performs no
        network I/O and never turns operational readiness into a trading
        authorization. When reliability is omitted, the service's own
        accumulated reliability snapshot for the selected provider is used.
        """
        adapter = self.registry.get(provider)
        engine = MarketOperationalStateEngine(policy)
        reliability_data = reliability
        if reliability_data is None:
            reliability_data = self.reliability_monitor.snapshot(adapter.name).to_dict()
        state = engine.assess(
            provider=adapter.name,
            pair=pair,
            assessed_at=assessed_at or self._utc_now(),
            freshness=freshness,
            data_quality=data_quality,
            provider_health=provider_health,
            reliability=reliability_data,
        )
        return state.to_dict()

    def describe_providers(self) -> tuple[dict[str, Any], ...]:
        return self.registry.describe()

    def get_provider(self, provider: str) -> Any:
        return self.registry.get(provider).provider

    def get_forex_quote(
        self,
        pair: str,
        *,
        provider: str | None = None,
        data_range: str = "1d",
        interval: str = "5m",
    ) -> dict[str, Any]:
        invalid = self._invalid_pair(pair)
        if invalid:
            return invalid

        try:
            adapter = self.registry.select("quote", provider=provider)
        except ProviderRegistryError as exc:
            return MarketDataError(
                market="forex",
                pair=normalize_forex_pair(pair),
                provider=provider,
                error=str(exc),
            ).to_dict()

        started = time.monotonic()
        try:
            result = adapter.provider.get_forex_quote(
                normalize_forex_pair(pair),
                data_range=data_range,
                interval=interval,
            )
            success = not (isinstance(result, Mapping) and result.get("success") is False)
            self._record_provider_check(adapter.name, success=success, started=started)
            if isinstance(result, Mapping) and "provider" in result:
                # Quote timestamps are nested inside the standardized candle.
                candle = result.get("candle")
                if isinstance(candle, Mapping) and candle.get("timestamp_utc"):
                    enriched = dict(result)
                    enriched["freshness"] = self.assess_observation_freshness(
                        {"provider": result["provider"], "timestamp_utc": candle["timestamp_utc"]}
                    )["freshness"]
                    return enriched
            return result
        except Exception as exc:
            self._record_provider_check(adapter.name, success=False, started=started)
            return self._provider_failure(adapter.name, "quote retrieval", exc)

    def get_forex_history(
        self,
        pair: str,
        *,
        provider: str | None = None,
        data_range: str = "1d",
        interval: str = "5m",
    ) -> dict[str, Any]:
        invalid = self._invalid_pair(pair)
        if invalid:
            return invalid

        try:
            adapter = self.registry.select("history", provider=provider)
        except ProviderRegistryError as exc:
            return MarketDataError(
                market="forex",
                pair=normalize_forex_pair(pair),
                provider=provider,
                error=str(exc),
            ).to_dict()

        started = time.monotonic()
        try:
            result = adapter.provider.get_forex_history(
                normalize_forex_pair(pair),
                data_range=data_range,
                interval=interval,
            )
            success = not (isinstance(result, Mapping) and result.get("success") is False)
            self._record_provider_check(adapter.name, success=success, started=started)
            return result
        except Exception as exc:
            self._record_provider_check(adapter.name, success=False, started=started)
            return self._provider_failure(adapter.name, "history retrieval", exc)

    def get_latest_tick(
        self,
        pair: str,
        *,
        provider: str | None = None,
    ) -> dict[str, Any]:
        invalid = self._invalid_pair(pair)
        if invalid:
            return invalid

        normalized = normalize_forex_pair(pair)
        try:
            adapter = self.registry.select("latest_tick", provider=provider)
        except ProviderRegistryError as exc:
            return MarketDataError(
                market="forex",
                pair=normalized,
                provider=provider,
                error=str(exc),
            ).to_dict()

        resolver = getattr(adapter.provider, "forex_pair_to_provider_symbol", None)
        getter = getattr(adapter.provider, "get_latest_tick", None)
        if not callable(resolver) or not callable(getter):
            return self._unsupported(adapter.name, "latest_tick")

        started = time.monotonic()
        try:
            provider_symbol = resolver(normalized)
            if not provider_symbol:
                self._record_provider_check(adapter.name, success=False, started=started)
                return self._provider_failure(
                    adapter.name,
                    "symbol resolution",
                    RuntimeError(f"No provider symbol found for {normalized}."),
                )
            result = getter(provider_symbol)
            success = not (isinstance(result, Mapping) and result.get("success") is False)
            self._record_provider_check(adapter.name, success=success, started=started)
            if isinstance(result, Mapping):
                return self._attach_freshness(result)
            return result
        except Exception as exc:
            self._record_provider_check(adapter.name, success=False, started=started)
            return self._provider_failure(adapter.name, "latest tick retrieval", exc)

    def health_check(self, *, provider: str | None = None) -> dict[str, Any]:
        try:
            adapter = self.registry.select("health", provider=provider)
        except ProviderRegistryError as exc:
            return {
                "success": False,
                "provider": provider,
                "status": "UNAVAILABLE",
                "error": str(exc),
            }

        checker = getattr(adapter.provider, "health_check", None)
        if not callable(checker):
            return {
                "success": False,
                "provider": adapter.name,
                "status": "UNAVAILABLE",
                "error": f"Provider '{adapter.name}' does not expose health_check().",
            }

        started = time.monotonic()
        try:
            result = checker()
            success = isinstance(result, Mapping) and result.get("success") is True
            self._record_provider_check(adapter.name, success=success, started=started)
            return result
        except Exception as exc:
            self._record_provider_check(adapter.name, success=False, started=started)
            return {
                "success": False,
                "provider": adapter.name,
                "status": "UNHEALTHY",
                "error": str(exc),
            }

    def create_live_tick_stream(
        self,
        pair: str,
        *,
        provider: str | None = None,
        **stream_options: Any,
    ) -> Any:
        """Create, but do not start, a live tick stream.

        The returned stream is provider-specific internally but selected
        through the unified market service. The caller owns lifecycle control.
        """

        invalid = self._invalid_pair(pair)
        if invalid:
            raise ValueError(invalid.get("error", "Invalid Forex pair."))

        normalized = normalize_forex_pair(pair)
        adapter = self.registry.select("live_ticks", provider=provider)
        resolver = getattr(adapter.provider, "forex_pair_to_provider_symbol", None)
        if not callable(resolver):
            raise ProviderRegistryError(
                f"Provider '{adapter.name}' cannot resolve Forex provider symbols."
            )

        provider_symbol = resolver(normalized)
        if not provider_symbol:
            raise ProviderRegistryError(
                f"Provider '{adapter.name}' has no active symbol for {normalized}."
            )

        if adapter.name.casefold() == "deriv":
            stream_options.setdefault("app_id", getattr(adapter.provider, "app_id", "1089"))
            stream_options.setdefault("endpoint", getattr(adapter.provider, "endpoint", ""))
            stream_options.setdefault("timeout", getattr(adapter.provider, "timeout", 15))
            stream_options.setdefault(
                "connection_factory",
                getattr(adapter.provider, "connection_factory", None),
            )
            return DerivTickStream(provider_symbol, **stream_options)

        factory = adapter.operation("live_ticks")
        if factory is None:
            raise ProviderRegistryError(
                f"Provider '{adapter.name}' declares live_ticks but has no stream factory."
            )
        return factory(normalized, provider_symbol=provider_symbol, **stream_options)


__all__ = [
    "UnifiedMarketDataService",
    "UnifiedServiceResult",
    "ProviderAdapter",
    "ProviderCapabilities",
    "ProviderRegistry",
    "ProviderRegistryError",
]
