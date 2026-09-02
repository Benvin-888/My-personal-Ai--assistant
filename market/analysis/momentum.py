"""Deterministic momentum indicators for APEX."""

from math import isfinite


def rsi(closes, period=14):
    """Wilder-style RSI series."""
    if not isinstance(period, int) or isinstance(period, bool) or period <= 0:
        raise ValueError("period must be a positive integer")

    result = [None] * len(closes)

    if len(closes) <= period:
        return result

    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    result[period] = _rsi_value(avg_gain, avg_loss)

    for i in range(period + 1, len(closes)):
        gain = gains[i - 1]
        loss = losses[i - 1]

        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        result[i] = _rsi_value(avg_gain, avg_loss)

    return result


def _rsi_value(avg_gain, avg_loss):
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    if avg_gain == 0:
        return 0.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(closes, fast_period=12, slow_period=26, signal_period=9):
    """Return MACD line, signal line, and histogram series."""
    if (
        not isinstance(fast_period, int)
        or isinstance(fast_period, bool)
        or fast_period <= 0
        or not isinstance(slow_period, int)
        or isinstance(slow_period, bool)
        or slow_period <= fast_period
        or not isinstance(signal_period, int)
        or isinstance(signal_period, bool)
        or signal_period <= 0
    ):
        raise ValueError("invalid MACD periods")

    from .trend import ema

    fast = ema(closes, fast_period)
    slow = ema(closes, slow_period)

    line = [None] * len(closes)

    for i in range(len(closes)):
        if fast[i] is not None and slow[i] is not None:
            line[i] = fast[i] - slow[i]

    valid_macd = [value for value in line if value is not None]
    signal_compact = ema(valid_macd, signal_period)

    signal = [None] * len(closes)
    compact_index = 0

    for i, value in enumerate(line):
        if value is not None:
            signal[i] = signal_compact[compact_index]
            compact_index += 1

    histogram = [None] * len(closes)

    for i in range(len(closes)):
        if line[i] is not None and signal[i] is not None:
            histogram[i] = line[i] - signal[i]

    return line, signal, histogram


def classify_momentum(rsi_value, macd_histogram):
    """Classify momentum descriptively from RSI and MACD histogram."""
    if rsi_value is None or macd_histogram is None:
        return "INSUFFICIENT_DATA"

    if rsi_value >= 60 and macd_histogram > 0:
        return "POSITIVE"

    if rsi_value <= 40 and macd_histogram < 0:
        return "NEGATIVE"

    return "NEUTRAL"
