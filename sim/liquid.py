"""Two bots added on 1 Oct 2026 after the backtests in docs/research.md: the most traded coins held as a basket, and the
same basket held only while BTC is above its 30-day average."""
import bisect
import statistics

from .bots import BTC, HOUR_MS, Bot, coin

DAY_MS = 24 * HOUR_MS
COINS = 5
KEEP = 10
EVERY_H = 72
VOLUME_DAYS = 30
TREND_DAYS = 30


class LiquidBasket(Bot):
    key = "liquid5_hold"
    title = "Liquid 5, held"
    rules = ("Holds the 5 coins with the most CoinDCX INR volume (the median day of the last 30) in equal parts, passing "
             "over any whose smallest order is more than its share for the next one. Every 3 days it sells a coin that has "
             "dropped out of the 10 most traded and fills the gap. The yardstick for the trend-filtered version.")
    added = True
    trend = False

    def __init__(self, account, pairs):
        Bot.__init__(self, account)
        self.pairs = tuple(sorted(set(pairs) | {BTC}))
        self.subscriptions = tuple((p, "1h") for p in self.pairs)
        self._times = {}

    def on_candle(self, ctx, s, i):
        pass

    def _last_closed(self, s, t):
        times = self._times.get(id(s))
        if times is None or len(times) != len(s.candles):
            times = self._times[id(s)] = [c["t"] for c in s.candles]
        i = bisect.bisect_right(times, t - HOUR_MS) - 1
        return i if i >= 0 and s.candles[i]["t"] + HOUR_MS >= t - 3 * HOUR_MS else None

    def _volumes(self, ctx):
        today = ctx.t // DAY_MS
        out = {}
        for pair in self.pairs:
            s = ctx.series.get((pair, "1h"))
            i = self._last_closed(s, ctx.t) if s else None
            if i is None or pair not in ctx.prices:
                continue
            days = dict((d, 0.0) for d in range(today - VOLUME_DAYS, today))
            while i >= 0 and s.candles[i]["t"] // DAY_MS >= today - VOLUME_DAYS:
                c = s.candles[i]
                if c["t"] // DAY_MS in days:
                    days[c["t"] // DAY_MS] += c["v"] * c["c"]
                i -= 1
            out[pair] = statistics.median(days.values())
        return out

    def _btc_above_average(self, ctx):
        s = ctx.series.get((BTC, "1h"))
        i = self._last_closed(s, ctx.t) if s else None
        if i is None:
            return None
        start = s.candles[i]["t"] - TREND_DAYS * DAY_MS
        closes = [c["c"] for c in s.candles[:i + 1] if c["t"] > start]
        if len(closes) < TREND_DAYS * 20:
            return None
        return closes[-1] >= statistics.mean(closes)

    def on_tick(self, ctx):
        memo = self.acct.memo
        if ctx.t < memo.get("next_check", 0):
            return
        volumes = self._volumes(ctx)
        risk_on = self._btc_above_average(ctx) if self.trend else True
        if len(volumes) < COINS or risk_on is None:
            memo["next_check"] = ctx.t + HOUR_MS
            return
        memo["next_check"] = ctx.t + EVERY_H * HOUR_MS
        positions = self.acct.s["positions"]
        if not risk_on:
            for pair in sorted(positions):
                self.acct.sell(pair, ctx.prices[pair], ctx.t, "BTC below its 30-day average")
            return
        ranked = sorted(volumes, key=lambda p: (-volumes[p], p))
        keep = set(ranked[:KEEP])
        for pair in sorted(positions):
            if pair not in keep:
                self.acct.sell(pair, ctx.prices[pair], ctx.t, "no longer among the 10 most traded")
        slots = COINS - len(positions)
        reason = "among the %d most traded" % COINS + ("; BTC above its 30-day average" if self.trend else "")
        for n, pair in enumerate(ranked[:KEEP]):
            if slots <= 0:
                break
            if pair in positions:
                continue
            # A coin whose smallest order is more than an equal share is passed over for the next one.
            if self.acct.buy(pair, self.acct.cash / slots, ctx.prices[pair], ctx.t,
                             reason if n < COINS else "among the %d most traded, standing in for one it can't buy" % KEEP):
                slots -= 1

    def describe(self):
        held = sorted(coin(p) for p in self.acct.s["positions"])
        if held:
            return "holding " + ", ".join(held)
        return "cash, BTC below its 30-day average" if self.trend and self.acct.memo.get("next_check") else "cash"


class LiquidTrend(LiquidBasket):
    key = "liquid5_btc30"
    title = "Liquid 5, BTC trend filter"
    rules = ("The same 5 coins, held only while BTC's price is above its 30-day average, and in cash otherwise. It checks "
             "every 3 days. In 17 past 15-day windows it ended flat (+0.1% a window after costs) while holding the same "
             "coins lost 2.2%, and its worst window was -10% instead of -20%. It was the best of 14 timing rules tried, "
             "which flatters that result; these 15 days are its real test.")
    trend = True


def specs(universe):
    pairs = tuple(universe)
    return [(cls.key, cls.kind, lambda account, cls=cls: cls(account, pairs)) for cls in (LiquidBasket, LiquidTrend)]
