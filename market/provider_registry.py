"""
APEX / BENVIN Provider Registry

Phase 2.6.5 - Unified Multi-Provider Market Service

A small capability-aware registry that lets APEX select market-data
providers without coupling consumers to a specific vendor.

This registry is intentionally market-data-only. It has no trading,
account, authentication, or strategy authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


class ProviderRegistryError(RuntimeError):
    """Raised when provider registration or selection is invalid."""


@dataclass(frozen=True)
class ProviderCapabilities:
    """Explicit capabilities exposed by a provider adapter."""

    quote: bool = False
    history: bool = False
    latest_tick: bool = False
    live_ticks: bool = False
    health: bool = False
    extra: frozenset[str] = field(default_factory=frozenset)

    def supports(self, capability: str) -> bool:
        if not isinstance(capability, str) or not capability.strip():
            return False
        capability = capability.strip().lower()
        if capability == "quote":
            return self.quote
        if capability == "history":
            return self.history
        if capability == "latest_tick":
            return self.latest_tick
        if capability == "live_ticks":
            return self.live_ticks
        if capability == "health":
            return self.health
        return capability in self.extra

    def as_dict(self) -> dict[str, Any]:
        return {
            "quote": self.quote,
            "history": self.history,
            "latest_tick": self.latest_tick,
            "live_ticks": self.live_ticks,
            "health": self.health,
            "extra": sorted(self.extra),
        }


@dataclass(frozen=True)
class ProviderAdapter:
    """Provider plus its explicitly declared market-data operations."""

    name: str
    provider: Any
    capabilities: ProviderCapabilities
    aliases: tuple[str, ...] = ()
    priority: int = 100
    handlers: dict[str, Callable[..., Any]] = field(default_factory=dict, compare=False, repr=False)

    def matches(self, identifier: str) -> bool:
        if not isinstance(identifier, str):
            return False
        target = identifier.strip().casefold()
        return target == self.name.casefold() or target in {
            alias.casefold() for alias in self.aliases
        }

    def supports(self, capability: str) -> bool:
        return self.capabilities.supports(capability)

    def operation(self, capability: str) -> Callable[..., Any] | None:
        return self.handlers.get(capability)


class ProviderRegistry:
    """Thread-light, deterministic registry for provider adapters."""

    def __init__(self, providers: Iterable[ProviderAdapter] | None = None):
        self._providers: dict[str, ProviderAdapter] = {}
        if providers:
            for provider in providers:
                self.register(provider)

    def register(self, adapter: ProviderAdapter, *, replace: bool = False) -> None:
        if not isinstance(adapter, ProviderAdapter):
            raise TypeError("adapter must be a ProviderAdapter.")
        key = adapter.name.strip().casefold()
        if not key:
            raise ProviderRegistryError("Provider name cannot be empty.")
        if key in self._providers and not replace:
            raise ProviderRegistryError(
                f"Provider '{adapter.name}' is already registered."
            )
        self._providers[key] = adapter

    def unregister(self, identifier: str) -> ProviderAdapter:
        adapter = self.get(identifier)
        del self._providers[adapter.name.casefold()]
        return adapter

    def get(self, identifier: str) -> ProviderAdapter:
        if not isinstance(identifier, str) or not identifier.strip():
            raise ProviderRegistryError("Provider identifier must be a non-empty string.")
        for adapter in self._providers.values():
            if adapter.matches(identifier):
                return adapter
        raise ProviderRegistryError(f"Unknown market-data provider '{identifier}'.")

    def find_capable(self, capability: str) -> tuple[ProviderAdapter, ...]:
        matches = [
            adapter
            for adapter in self._providers.values()
            if adapter.supports(capability)
        ]
        return tuple(sorted(matches, key=lambda item: (item.priority, item.name.casefold())))

    def select(
        self,
        capability: str,
        *,
        provider: str | None = None,
    ) -> ProviderAdapter:
        if provider is not None:
            adapter = self.get(provider)
            if not adapter.supports(capability):
                raise ProviderRegistryError(
                    f"Provider '{adapter.name}' does not support '{capability}'."
                )
            return adapter

        matches = self.find_capable(capability)
        if not matches:
            raise ProviderRegistryError(
                f"No registered provider supports '{capability}'."
            )
        return matches[0]

    def list(self) -> tuple[ProviderAdapter, ...]:
        return tuple(sorted(self._providers.values(), key=lambda item: (item.priority, item.name.casefold())))

    def describe(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "name": adapter.name,
                "aliases": list(adapter.aliases),
                "priority": adapter.priority,
                "capabilities": adapter.capabilities.as_dict(),
            }
            for adapter in self.list()
        )
