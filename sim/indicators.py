def ema(values, period):
    out = [None] * len(values)
    k = 2.0 / (period + 1)
    current = None
    for i, value in enumerate(values):
        current = value if current is None else value * k + current * (1 - k)
        if i >= period - 1:
            out[i] = current
    return out


def rsi(closes, period):
    out = [None] * len(closes)
    if len(closes) <= period:
        return out
    gain = loss = 0.0
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        gain += max(change, 0.0)
        loss += max(-change, 0.0)
    gain /= period
    loss /= period
    out[period] = _rsi(gain, loss)
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = (gain * (period - 1) + max(change, 0.0)) / period
        loss = (loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = _rsi(gain, loss)
    return out


def _rsi(gain, loss):
    if loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def atr(candles, period):
    out = [None] * len(candles)
    if len(candles) < period:
        return out
    ranges = []
    for i, c in enumerate(candles):
        if i == 0:
            ranges.append(c["h"] - c["l"])
        else:
            prev_close = candles[i - 1]["c"]
            ranges.append(max(c["h"] - c["l"], abs(c["h"] - prev_close), abs(c["l"] - prev_close)))
    value = sum(ranges[:period]) / period
    out[period - 1] = value
    for i in range(period, len(candles)):
        value = (value * (period - 1) + ranges[i]) / period
        out[i] = value
    return out


def prior_high(candles, period):
    out = [None] * len(candles)
    for i in range(period, len(candles)):
        out[i] = max(c["h"] for c in candles[i - period:i])
    return out


def prior_low(candles, period):
    out = [None] * len(candles)
    for i in range(period, len(candles)):
        out[i] = min(c["l"] for c in candles[i - period:i])
    return out


class Series:
    def __init__(self, pair, interval, candles):
        self.pair = pair
        self.interval = interval
        self.candles = candles
        self.closes = [c["c"] for c in candles]
        self._cache = {}

    def get(self, name, period):
        key = (name, period)
        if key not in self._cache:
            if name == "ema":
                values = ema(self.closes, period)
            elif name == "rsi":
                values = rsi(self.closes, period)
            elif name == "atr":
                values = atr(self.candles, period)
            elif name == "high":
                values = prior_high(self.candles, period)
            elif name == "low":
                values = prior_low(self.candles, period)
            else:
                raise KeyError(name)
            self._cache[key] = values
        return self._cache[key]
