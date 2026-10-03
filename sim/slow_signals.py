"""Fixed, low-turnover spot signals shared by historical and forward paper bots.

All methods take a decision time ``t`` and use only hourly candles closed at or
before ``t``. The opening candle at ``t`` and later candles are never inspected.
"""

import bisect
import math
import statistics


HOUR_MS = 3_600_000
PAIRS = tuple("I-%s_INR" % coin for coin in ("BTC", "ETH", "SOL", "XRP"))


class History:
    def __init__(self, pair, rows):
        self.pair = pair
        self.rows = rows
        self.times = [row["t"] for row in rows]
        if not rows:
            raise ValueError("%s has no candles" % pair)
        for i, row in enumerate(rows):
            try:
                t = int(row["t"])
                o, h, l, c, v = (float(row[k]) for k in ("o", "h", "l", "c", "v"))
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError("%s candle %d has an invalid field" % (pair, i)) from exc
            if (t % HOUR_MS or min(o, h, l, c) <= 0 or v < 0 or
                    not all(math.isfinite(x) for x in (o, h, l, c, v)) or
                    h < max(o, c) or l > min(o, c) or
                    (i and t != rows[i - 1]["t"] + HOUR_MS)):
                raise ValueError("%s candle %d is malformed or the series has a gap" % (pair, i))

    def index(self, t):
        """Index of the candle that opens at t, which need not have closed yet."""
        return bisect.bisect_left(self.times, t)

    def opening(self, t):
        i = self.index(t)
        if i == len(self.times) or self.times[i] != t:
            raise ValueError("%s has no opening candle at %d" % (self.pair, t))
        return self.rows[i]

    def closed(self, t, hours):
        i = self.index(t)
        if i < hours or self.rows[i - 1]["t"] + HOUR_MS != t:
            raise ValueError("%s lacks %d completed hours at %d" % (self.pair, hours, t))
        return self.rows[i - hours:i]

    def return_over(self, t, hours):
        bars = self.closed(t, hours + 1)
        return bars[-1]["c"] / bars[0]["c"] - 1


def _liquid(history, t):
    # A trailing, observable filter; the execution audit checks the NEXT hour separately.
    return statistics.median(c["v"] * c["c"] for c in history.closed(t, 24)) >= 50_000


def _trend(history, t):
    closes = [row["c"] for row in history.closed(t, 30 * 24)]
    return (history.return_over(t, 30 * 24) > 0 and
            closes[-1] >= statistics.mean(closes) and _liquid(history, t))


def targets(name, histories, t, held):
    """Target weights for one shared wallet, with no forward-looking inputs."""
    if name == "cash":
        return {}
    if name == "hold_btc":
        return {PAIRS[0]: 1.0}
    if name == "hold_equal":
        return {pair: 0.25 for pair in PAIRS}
    if name == "btc_sma30":
        h = histories[PAIRS[0]]
        closes = [row["c"] for row in h.closed(t, 30 * 24)]
        return {PAIRS[0]: 0.95} if closes[-1] >= statistics.mean(closes) and _liquid(h, t) else {}
    if name == "tsmom30":
        return {pair: 0.25 for pair in PAIRS if _trend(histories[pair], t)}
    if name == "crossmom7":
        ranked = sorted(((histories[p].return_over(t, 7 * 24), p) for p in PAIRS
                         if _liquid(histories[p], t)), key=lambda x: (-x[0], x[1]))
        positive = [pair for value, pair in ranked if value > 0]
        chosen = [pair for pair in held if pair in positive[:3]]
        for pair in positive:
            if len(chosen) >= 2:
                break
            if pair not in chosen:
                chosen.append(pair)
        return {pair: 0.45 for pair in chosen[:2]}
    if name == "donchian20_10":
        desired = {}
        for pair in PAIRS:
            h = histories[pair]
            bars = h.closed(t, 20 * 24 + 1)
            latest = bars[-1]
            prior_high = max(row["h"] for row in bars[:-1])
            prior_low = min(row["l"] for row in bars[-(10 * 24 + 1):-1])
            if pair in held:
                if latest["c"] >= prior_low:
                    desired[pair] = 0.25
            elif latest["c"] > prior_high and _liquid(h, t):
                desired[pair] = 0.25
        return desired
    raise KeyError(name)


# The first three are controls. The four rules below were fixed before the historical screen.
POLICIES = {
    "cash": None,
    "hold_btc": None,
    "hold_equal": None,
    "btc_sma30": 24,
    "tsmom30": 24,
    "crossmom7": 7 * 24,
    "donchian20_10": 24,
}
