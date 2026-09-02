"""
APEX / BENVIN Technical Analysis Engine

Phase 2.3 - Technical Analysis Foundation

Consumes validated historical Forex candles and calculates deterministic
technical indicators.

This module does NOT:
    - generate trade signals
    - recommend trades
    - place trades
    - calculate position sizes
    - modify accounts
"""

from math import isfinite

from .models import TechnicalAnalysis
from .trend import classify_trend, ema, sma
from .momentum import classify_momentum, macd, rsi
from .volatility import atr, bollinger_bands, classify_volatility


class TechnicalAnalysisEngine:
    """Calculate a deterministic technical-analysis snapshot."""

    def analyze_history(
        self,
        history,
        *,
        ema_fast_period=20,
        ema_slow_period=50,
        sma_period=20,
        rsi_period=14,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        atr_period=14,
        bollinger_period=20,
        bollinger_stddevs=2.0,
        trend_slope_lookback=5,
    ):
        if not isinstance(history, dict):
            return self._error("history must be a dictionary")

        if not history.get("success", False):
            return self._error(
                "Cannot analyze unsuccessful historical market data"
            )

        candles = history.get("candles")

        if not isinstance(candles, list) or not candles:
            return self._error(
                "Historical market data contains no candles"
            )

        try:
            self._validate_parameters(
                ema_fast_period,
                ema_slow_period,
                sma_period,
                rsi_period,
                macd_fast,
                macd_slow,
                macd_signal,
                atr_period,
                bollinger_period,
                bollinger_stddevs,
                trend_slope_lookback,
            )

            closes = [
                self._candle_value(candle, "close")
                for candle in candles
            ]
            highs = [
                self._candle_value(candle, "high")
                for candle in candles
            ]
            lows = [
                self._candle_value(candle, "low")
                for candle in candles
            ]

            if any(
                value is None
                for value in closes + highs + lows
            ):
                return self._error(
                    "Historical candles contain invalid OHLC values"
                )

            ema_fast = ema(closes, ema_fast_period)
            ema_slow = ema(closes, ema_slow_period)
            sma_values = sma(closes, sma_period)
            rsi_values = rsi(closes, rsi_period)

            macd_line, macd_signal_line, macd_histogram = macd(
                closes,
                macd_fast,
                macd_slow,
                macd_signal,
            )

            atr_values = atr(candles, atr_period)

            bb_middle, bb_upper, bb_lower = bollinger_bands(
                closes,
                bollinger_period,
                float(bollinger_stddevs),
            )

            latest = len(candles) - 1
            timestamp = self._timestamp(candles[latest])

            indicators = {
                "sma": self._indicator(
                    "sma",
                    sma_period,
                    sma_values[latest],
                    timestamp,
                ),
                "ema_fast": self._indicator(
                    "ema",
                    ema_fast_period,
                    ema_fast[latest],
                    timestamp,
                ),
                "ema_slow": self._indicator(
                    "ema",
                    ema_slow_period,
                    ema_slow[latest],
                    timestamp,
                ),
                "rsi": self._indicator(
                    "rsi",
                    rsi_period,
                    rsi_values[latest],
                    timestamp,
                ),
                "macd": {
                    "fast_period": macd_fast,
                    "slow_period": macd_slow,
                    "signal_period": macd_signal,
                    "line": macd_line[latest],
                    "signal": macd_signal_line[latest],
                    "histogram": macd_histogram[latest],
                    "timestamp_utc": timestamp,
                    "valid": macd_histogram[latest] is not None,
                },
                "atr": self._indicator(
                    "atr",
                    atr_period,
                    atr_values[latest],
                    timestamp,
                ),
                "bollinger_bands": {
                    "period": bollinger_period,
                    "stddevs": float(bollinger_stddevs),
                    "middle": bb_middle[latest],
                    "upper": bb_upper[latest],
                    "lower": bb_lower[latest],
                    "timestamp_utc": timestamp,
                    "valid": bb_middle[latest] is not None,
                },
            }

            trend = classify_trend(
                closes,
                ema_fast,
                ema_slow,
                slope_lookback=trend_slope_lookback,
            )

            momentum = classify_momentum(
                rsi_values[latest],
                macd_histogram[latest],
            )

            band_width = None

            if (
                bb_upper[latest] is not None
                and bb_lower[latest] is not None
            ):
                band_width = (
                    bb_upper[latest]
                    - bb_lower[latest]
                )

            volatility = classify_volatility(
                atr_values[latest],
                closes[-1],
                band_width,
            )

            return TechnicalAnalysis(
                pair=str(history.get("pair", "UNKNOWN")),
                interval=str(
                    history.get("interval", "UNKNOWN")
                ),
                candle_count=len(candles),
                provider=history.get("provider"),
                source_range=history.get("range"),
                latest_timestamp_utc=timestamp,
                trend=trend,
                momentum=momentum,
                volatility=volatility,
                indicators=indicators,
                metadata={
                    "calculation": "deterministic_python",
                    "latest_close": closes[-1],
                    "retrieved_at": history.get("retrieved_at"),
                    "indicator_warmup_requirement": max(
                        ema_slow_period,
                        macd_slow + macd_signal - 1,
                        rsi_period + 1,
                        atr_period,
                        bollinger_period,
                    ),
                    "trend_slope_lookback": trend_slope_lookback,
                },
            ).to_dict()

        except ValueError as error:
            return self._error(str(error))

        except Exception as error:
            return self._error(
                f"Unexpected technical-analysis error: {error}"
            )

    @staticmethod
    def _validate_parameters(
        ema_fast_period,
        ema_slow_period,
        sma_period,
        rsi_period,
        macd_fast,
        macd_slow,
        macd_signal,
        atr_period,
        bollinger_period,
        bollinger_stddevs,
        trend_slope_lookback,
    ):
        periods = [
            ema_fast_period,
            ema_slow_period,
            sma_period,
            rsi_period,
            macd_fast,
            macd_slow,
            macd_signal,
            atr_period,
            bollinger_period,
            trend_slope_lookback,
        ]

        if any(
            not isinstance(period, int)
            or isinstance(period, bool)
            or period <= 0
            for period in periods
        ):
            raise ValueError(
                "Indicator periods must be positive integers"
            )

        if trend_slope_lookback <= 1:
            raise ValueError(
                "trend_slope_lookback must be greater than one"
            )

        if macd_slow <= macd_fast:
            raise ValueError(
                "MACD slow period must be greater than fast period"
            )

        if (
            not isinstance(bollinger_stddevs, (int, float))
            or isinstance(bollinger_stddevs, bool)
            or not isfinite(float(bollinger_stddevs))
            or bollinger_stddevs <= 0
        ):
            raise ValueError(
                "bollinger_stddevs must be a positive finite number"
            )

    @staticmethod
    def _candle_value(candle, field):
        value = (
            candle.get(field)
            if isinstance(candle, dict)
            else getattr(candle, field, None)
        )

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            return None

        value = float(value)

        return value if isfinite(value) else None

    @staticmethod
    def _timestamp(candle):
        if isinstance(candle, dict):
            return candle.get("timestamp_utc")
        return getattr(candle, "timestamp_utc", None)

    @staticmethod
    def _indicator(name, period, value, timestamp):
        return {
            "name": name,
            "period": period,
            "value": value,
            "timestamp_utc": timestamp,
            "valid": value is not None,
        }

    @staticmethod
    def _error(message):
        return {
            "success": False,
            "market": "forex",
            "analysis": "technical",
            "error": message,
        }


_analysis_engine = TechnicalAnalysisEngine()


def analyze_forex_history(history, **kwargs):
    """Public technical-analysis API for an existing history result."""
    return _analysis_engine.analyze_history(history, **kwargs)
