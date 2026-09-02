"""
APEX / BENVIN Market Data Service

Phase 2.3 - Unified Market Data Service

The service sits between APEX and external market-data
providers.

Responsibilities:

    1. Validate Forex pairs.
    2. Select the provider.
    3. Retrieve current market data.
    4. Retrieve historical market data.
    5. Normalize provider data.
    6. Manage short-lived quote caching.
    7. Return standardized results.

The service does NOT:

    - generate trading signals
    - recommend entries
    - recommend exits
    - calculate position sizes
    - execute trades
    - modify trading accounts
    - make trading decisions
"""

from datetime import datetime, timezone

import requests

from .cache import MarketDataCache
from .history import HistoricalMarketData
from .models import ForexQuote, MarketDataError
from .provider import (
    MarketDataProvider,
    YahooFinanceProvider,
    normalize_forex_pair,
)


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_RANGE = "1d"
DEFAULT_INTERVAL = "5m"

DEFAULT_CACHE_TTL = 15


# ============================================================
# SERVICE
# ============================================================

class MarketDataService:
    """
    Main market-data service.

    APEX should interact with this service rather than
    directly communicating with an external market-data
    provider.

    The service provides a unified entry point for:

        - current Forex quotes
        - historical Forex market data
    """

    def __init__(
        self,
        provider: MarketDataProvider | None = None,
        cache: MarketDataCache | None = None
    ):
        self.provider = (
            provider
            if provider is not None
            else YahooFinanceProvider()
        )

        self.cache = (
            cache
            if cache is not None
            else MarketDataCache(
                ttl_seconds=DEFAULT_CACHE_TTL
            )
        )

        # ----------------------------------------------------
        # HISTORICAL MARKET DATA ENGINE
        # ----------------------------------------------------
        #
        # Reuse the same provider selected by this service.
        #
        # This keeps quote and historical retrieval under
        # the same provider configuration.
        #

        self.history = HistoricalMarketData(
            provider=self.provider
        )

    # ========================================================
    # UTC TIME
    # ========================================================

    @staticmethod
    def _utc_now():
        """
        Return current UTC timestamp.
        """

        return (
            datetime.now(
                timezone.utc
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z"
            )
        )

    # ========================================================
    # GET FOREX QUOTE
    # ========================================================

    def get_forex_quote(
        self,
        pair,
        *,
        data_range=DEFAULT_RANGE,
        interval=DEFAULT_INTERVAL,
        use_cache=True
    ):
        """
        Retrieve the latest Forex quote.

        Returns a standardized dictionary.

        The returned price originates from the provider,
        not from the LLM.
        """

        normalized_pair = normalize_forex_pair(
            pair
        )

        if normalized_pair is None:

            return MarketDataError(
                market="forex",
                pair=(
                    str(pair)
                    if pair is not None
                    else None
                ),
                error=(
                    "Invalid Forex pair. "
                    "Use a six-letter pair such as EURUSD."
                )
            ).to_dict()

        # ----------------------------------------------------
        # CACHE
        # ----------------------------------------------------

        if use_cache:

            cached = self.cache.get(
                normalized_pair,
                interval=interval,
                data_range=data_range
            )

            if cached is not None:
                return cached

        # ----------------------------------------------------
        # PROVIDER
        # ----------------------------------------------------

        try:

            provider_result = (
                self.provider.get_forex_quote(
                    normalized_pair,
                    data_range=data_range,
                    interval=interval
                )
            )

            candle = provider_result[
                "candle"
            ]

            quote = ForexQuote(
                pair=normalized_pair,
                base_currency=normalized_pair[:3],
                quote_currency=normalized_pair[3:],
                provider_symbol=provider_result[
                    "provider_symbol"
                ],
                provider=provider_result[
                    "provider"
                ],
                interval=provider_result[
                    "interval"
                ],
                data_range=provider_result[
                    "range"
                ],
                price=candle.close,
                candle=candle,
                currency=provider_result.get(
                    "currency"
                ),
                exchange_timezone=provider_result.get(
                    "exchange_timezone"
                ),
                market_state=provider_result.get(
                    "market_state"
                ),
                retrieved_at=self._utc_now()
            )

            result = quote.to_dict()

            # ------------------------------------------------
            # CACHE
            # ------------------------------------------------

            if use_cache:

                self.cache.set(
                    normalized_pair,
                    result,
                    interval=interval,
                    data_range=data_range
                )

            return result

        except requests.Timeout:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=(
                    "The market-data provider "
                    "timed out."
                )
            ).to_dict()

        except requests.ConnectionError:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=(
                    "Could not connect to the "
                    "market-data provider."
                )
            ).to_dict()

        except requests.HTTPError as error:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=(
                    f"Market provider HTTP error: {error}"
                )
            ).to_dict()

        except requests.RequestException as error:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=(
                    f"Market provider request failed: {error}"
                )
            ).to_dict()

        except ValueError as error:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=str(error)
            ).to_dict()

        except Exception as error:

            return MarketDataError(
                market="forex",
                pair=normalized_pair,
                provider=self.provider.name,
                error=(
                    f"Unexpected market-data error: {error}"
                )
            ).to_dict()

    # ========================================================
    # GET FOREX HISTORY
    # ========================================================

    def get_forex_history(
        self,
        pair,
        *,
        data_range="1d",
        interval="5m",
        limit=500
    ):
        """
        Retrieve validated historical Forex market data.

        Historical validation remains inside the dedicated
        HistoricalMarketData engine.

        This method provides the unified service-level entry
        point for APEX/BENVIN.
        """

        return self.history.get_forex_history(
            pair,
            data_range=data_range,
            interval=interval,
            limit=limit
        )

    # ========================================================
    # TECHNICAL ANALYSIS
    # ========================================================

    def analyze_forex_history(
        self,
        pair,
        *,
        data_range="1d",
        interval="5m",
        limit=500,
        **indicator_options
    ):
        """
        Retrieve validated historical Forex data and calculate
        deterministic technical indicators.

        The analysis layer does not generate trade signals or
        execute trading actions.
        """

        from .analysis import TechnicalAnalysisEngine

        history_result = self.get_forex_history(
            pair,
            data_range=data_range,
            interval=interval,
            limit=limit
        )

        if not history_result.get("success", False):
            return {
                "success": False,
                "market": "forex",
                "analysis": "technical",
                "error": "Historical market data retrieval failed.",
                "details": history_result,
            }

        return TechnicalAnalysisEngine().analyze_history(
            history_result,
            **indicator_options
        )

    # ========================================================
    # MARKET DATA HEALTH CHECK
    # ========================================================

    def check_market_data(self):
        """
        Check market-data service/provider health.
        """

        result = self.get_forex_quote(
            "EURUSD",
            use_cache=False
        )

        return {
            "success": bool(
                result.get(
                    "success",
                    False
                )
            ),
            "provider": self.provider.name,
            "test_pair": "EURUSD",
            "result": result,
        }

    # ========================================================
    # HISTORICAL MARKET DATA HEALTH CHECK
    # ========================================================

    def check_market_history(self):
        """
        Check historical market-data retrieval and
        validation.
        """

        return self.history.check_market_history()