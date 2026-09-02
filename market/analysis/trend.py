"""Deterministic trend indicators for APEX."""

from math import isfinite


def _clean(values):
    return [
        float(v)
        for v in values
        if isinstance(v, (int, float))
        and not isinstance(v, bool)
        and isfinite(float(v))
    ]


def sma(values, period):
    """Simple moving average series; None until enough observations exist."""
    if not isinstance(period, int) or isinstance(period, bool) or period <= 0:
        raise ValueError("period must be a positive integer")

    result = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        if all(v is not None for v in window):
            result[i] = sum(window) / period
    return result


def ema(values, period):
    """Exponential moving average using the standard SMA seed."""
    if not isinstance(period, int) or isinstance(period, bool) or period <= 0:
        raise ValueError("period must be a positive integer")

    result = [None] * len(values)
    if len(values) < period:
        return result

    seed_window = values[:period]
    if any(v is None for v in seed_window):
        return result

    result[period - 1] = sum(seed_window) / period
    multiplier = 2.0 / (period + 1.0)

    for i in range(period, len(values)):
        value = values[i]
        if value is None or result[i - 1] is None:
            continue
        result[i] = ((value - result[i - 1]) * multiplier) + result[i - 1]

    return result


def linear_slope(values, lookback=5):
    """Least-squares slope of the latest valid values."""
    if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback <= 1:
        raise ValueError("lookback must be an integer greater than one")

    window = list(values[-lookback:])
    valid = [v for v in window if v is not None]

    if len(valid) < 2:
        return None

    n = len(valid)
    x_mean = (n - 1) / 2.0
    y_mean = sum(valid) / n
    numerator = sum(
        (x - x_mean) * (y - y_mean)
        for x, y in enumerate(valid)
    )
    denominator = sum(
        (x - x_mean) ** 2
        for x in range(n)
    )

    return numerator / denominator if denominator else 0.0


def classify_trend(closes, ema_fast, ema_slow, *, slope_lookback=5):
    """
    Classify trend from price/EMA alignment and fast-EMA slope.

    This is descriptive market analysis only. It does not create a
    trading signal or recommendation.
    """
    if not closes:
        return "INSUFFICIENT_DATA"

    price = closes[-1]

    fast_series = ema_fast if isinstance(ema_fast, list) else [ema_fast]
    slow_series = ema_slow if isinstance(ema_slow, list) else [ema_slow]

    fast = fast_series[-1] if fast_series else None
    slow = slow_series[-1] if slow_series else None

    if price is None or fast is None or slow is None:
        return "INSUFFICIENT_DATA"

    slope = linear_slope(
        fast_series,
        lookback=slope_lookback
    )

    if price > fast > slow:
        if slope is not None and slope < 0:
            return "MIXED"
        return "BULLISH"

    if price < fast < slow:
        if slope is not None and slope > 0:
            return "MIXED"
        return "BEARISH"

    return "NEUTRAL"
