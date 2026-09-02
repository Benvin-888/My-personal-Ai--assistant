"""Deterministic volatility indicators for APEX."""

from math import sqrt


def true_range(candles):
    """Calculate true range from validated candle dictionaries/objects."""
    result = [None] * len(candles)
    previous_close = None
    for i, candle in enumerate(candles):
        high = _value(candle, "high")
        low = _value(candle, "low")
        close = _value(candle, "close")
        if high is None or low is None or close is None:
            continue
        if previous_close is None:
            result[i] = high - low
        else:
            result[i] = max(high - low, abs(high - previous_close), abs(low - previous_close))
        previous_close = close
    return result


def atr(candles, period=14):
    """Wilder-style Average True Range series."""
    if period <= 0:
        raise ValueError("period must be greater than zero")
    tr = true_range(candles)
    result = [None] * len(candles)
    if len(tr) < period or any(v is None for v in tr[:period]):
        return result
    current = sum(tr[:period]) / period
    result[period - 1] = current
    for i in range(period, len(tr)):
        if tr[i] is None:
            continue
        current = ((current * (period - 1)) + tr[i]) / period
        result[i] = current
    return result


def bollinger_bands(closes, period=20, stddevs=2.0):
    """Return middle, upper and lower Bollinger Band series."""
    if period <= 0 or stddevs <= 0:
        raise ValueError("period and stddevs must be greater than zero")
    middle = [None] * len(closes)
    upper = [None] * len(closes)
    lower = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        mean = sum(window) / period
        variance = sum((value - mean) ** 2 for value in window) / period
        deviation = sqrt(variance)
        middle[i] = mean
        upper[i] = mean + (stddevs * deviation)
        lower[i] = mean - (stddevs * deviation)
    return middle, upper, lower


def classify_volatility(atr_value, close, band_width):
    if atr_value is None or close is None or band_width is None or close == 0:
        return "INSUFFICIENT_DATA"
    normalized_atr = atr_value / abs(close)
    normalized_band = band_width / abs(close)
    if normalized_atr >= 0.01 or normalized_band >= 0.04:
        return "HIGH"
    if normalized_atr <= 0.003 and normalized_band <= 0.015:
        return "LOW"
    return "MODERATE"


def _value(candle, field):
    if isinstance(candle, dict):
        value = candle.get(field)
    else:
        value = getattr(candle, field, None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
