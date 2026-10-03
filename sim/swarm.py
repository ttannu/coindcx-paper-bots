import hashlib

from .bots import HOUR_MS, Bot, coin
from .learner import SelfLearner

FLIP_ODDS = 1.0 / 12


def draw(*parts):
    # hashlib, not hash(): Python salts hash() per process, and every run must replay the same coin flips.
    digest = hashlib.blake2b("|".join(str(p) for p in parts).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2.0 ** 64


def bot_key(pair, family):
    return "%s.%s" % (coin(pair).lower(), family.key)


class Family:
    def __init__(self, key, label, cls, rules, luck=False, **params):
        self.key = key
        self.label = label
        self.cls = cls
        self.rules = rules
        self.luck = luck
        self.params = params
        self.kind = cls.kind


class CoinBot(Bot):
    interval = "1h"

    def __init__(self, account, pair, family):
        Bot.__init__(self, account)
        self.pair = pair
        self.coin = coin(pair)
        self.family = family
        self.p = family.params
        self.key = bot_key(pair, family)
        # The coin flips draw from this; a low-cost twin keeps its original's, so both make the same random calls.
        self.seed = self.key
        self.title = "%s: %s" % (self.coin, family.label)
        self.subscriptions = ((pair, self.interval),)


class Hold(CoinBot):
    interval = "15m"

    def on_candle(self, ctx, s, i):
        if not self.acct.memo.get("bought"):
            self.acct.memo["bought"] = bool(self.acct.buy(self.pair, self.acct.cash, s.candles[i]["c"], ctx.t, "one-time buy"))


class Trend(CoinBot):
    def __init__(self, account, pair, family):
        self.interval = family.params["interval"]
        CoinBot.__init__(self, account, pair, family)

    def on_candle(self, ctx, s, i):
        fast, slow, atr = s.get("ema", self.p["fast"]), s.get("ema", self.p["slow"]), s.get("atr", 14)
        if i < 1 or None in (fast[i], slow[i], atr[i], fast[i - 1], slow[i - 1]):
            return
        c = s.candles[i]
        pos = self.acct.position(self.pair)
        if pos:
            if c["l"] <= pos["stop"]:
                self.acct.sell(self.pair, min(pos["stop"], c["o"]), ctx.t, "trailing stop")
            elif c["c"] < slow[i]:
                self.acct.sell(self.pair, c["c"], ctx.t, "closed below the slow average")
            else:
                pos["peak"] = max(pos["peak"], c["c"])
                pos["stop"] = max(pos["stop"], pos["peak"] - 2.5 * atr[i])
            return
        crossed_up = fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]
        bounced = fast[i] > slow[i] and c["c"] > fast[i] and s.closes[i - 1] <= fast[i - 1]
        if (crossed_up or bounced) and self.acct.buy(self.pair, self.acct.cash, c["c"], ctx.t, "uptrend entry"):
            pos = self.acct.position(self.pair)
            pos["peak"] = c["c"]
            pos["stop"] = c["c"] - 2.5 * atr[i]


class Dip(CoinBot):
    interval = "15m"

    def on_candle(self, ctx, s, i):
        rsi = s.get("rsi", 14)
        if rsi[i] is None:
            return
        c = s.candles[i]
        pos = self.acct.position(self.pair)
        if pos:
            if c["l"] <= pos["stop"]:
                self.acct.sell(self.pair, min(pos["stop"], c["o"]), ctx.t, "stop loss")
            elif c["h"] >= pos["target"]:
                self.acct.sell(self.pair, max(pos["target"], c["o"]), ctx.t, "take profit")
            elif rsi[i] > 55:
                self.acct.sell(self.pair, c["c"], ctx.t, "RSI recovered to %.0f" % rsi[i])
            elif ctx.t - pos["t"] >= 12 * HOUR_MS:
                self.acct.sell(self.pair, c["c"], ctx.t, "12-hour time limit")
            return
        if rsi[i] < self.p["below"] and self.acct.buy(self.pair, self.acct.cash, c["c"], ctx.t, "RSI %.0f" % rsi[i]):
            pos = self.acct.position(self.pair)
            entry = pos["cost"] / pos["qty"]
            pos["stop"] = entry * (1 - self.p["band"])
            pos["target"] = entry * (1 + self.p["band"])


class Breakout(CoinBot):
    def on_candle(self, ctx, s, i):
        high, low, atr = s.get("high", self.p["high"]), s.get("low", self.p["low"]), s.get("atr", 14)
        if None in (high[i], low[i], atr[i]):
            return
        c = s.candles[i]
        pos = self.acct.position(self.pair)
        if pos:
            if c["l"] <= pos["stop"]:
                self.acct.sell(self.pair, min(pos["stop"], c["o"]), ctx.t, "stop loss")
            elif c["c"] < low[i]:
                self.acct.sell(self.pair, c["c"], ctx.t, "broke the %d-hour low" % self.p["low"])
            return
        if c["c"] > high[i] and self.acct.buy(self.pair, self.acct.cash, c["c"], ctx.t, "%d-hour breakout" % self.p["high"]):
            self.acct.position(self.pair)["stop"] = c["c"] - 2 * atr[i]


class Grid(CoinBot):
    interval = "15m"
    levels = 6

    def on_candle(self, ctx, s, i):
        spacing = self.p["spacing"]
        c = s.candles[i]
        grid = self.acct.memo
        if "center" not in grid:
            grid.update(center=c["c"], lots={}, lot_budget=self.acct.cash / self.levels)
            return
        lots = grid["lots"]
        for level in sorted(lots, key=int):
            lot = lots[level]
            if c["h"] >= lot["target"] and self.acct.sell(self.pair, max(lot["target"], c["o"]), ctx.t,
                                                          "grid sell, level %s" % level, qty=lot["qty"]):
                del lots[level]
        for k in range(1, self.levels + 1):
            price = grid["center"] * (1 - spacing) ** k
            if str(k) not in lots and c["l"] <= price:
                qty = self.acct.buy(self.pair, grid["lot_budget"], min(price, c["o"]), ctx.t, "grid buy, level %d" % k)
                if qty:
                    lots[str(k)] = {"qty": qty, "target": price * (1 + spacing)}
        if not lots and c["c"] > grid["center"] * (1 + spacing):
            grid.update(center=c["c"], lot_budget=self.acct.cash / self.levels)


class PumpRider(CoinBot):
    def on_candle(self, ctx, s, i):
        average, atr = s.get("ema", 20), s.get("atr", 14)
        if i < 24 or None in (average[i], atr[i]):
            return
        c = s.candles[i]
        pos = self.acct.position(self.pair)
        if pos:
            if c["l"] <= pos["stop"]:
                self.acct.sell(self.pair, min(pos["stop"], c["o"]), ctx.t, "trailing stop")
            elif c["c"] < average[i]:
                self.acct.sell(self.pair, c["c"], ctx.t, "closed below the 20-hour average")
            elif ctx.t - pos["t"] >= 24 * HOUR_MS:
                self.acct.sell(self.pair, c["c"], ctx.t, "24-hour time limit")
            else:
                pos["peak"] = max(pos["peak"], c["c"])
                pos["stop"] = max(pos["stop"], pos["peak"] - 3 * atr[i])
            return
        surge = c["c"] / s.closes[i - 24] - 1
        if (surge >= 0.08 and c["c"] > c["o"] and c["c"] > average[i]
                and self.acct.buy(self.pair, self.acct.cash, c["c"], ctx.t, "up %.0f%% in 24 hours" % (surge * 100))):
            pos = self.acct.position(self.pair)
            pos["peak"] = c["c"]
            pos["stop"] = c["c"] - 3 * atr[i]


class CoinFlip(CoinBot):
    def on_candle(self, ctx, s, i):
        c = s.candles[i]
        if draw(self.seed, c["t"]) >= FLIP_ODDS:
            return
        if self.acct.position(self.pair):
            self.acct.sell(self.pair, c["c"], ctx.t, "coin flip")
        else:
            self.acct.buy(self.pair, self.acct.cash, c["c"], ctx.t, "coin flip")


class FuturesTrend(CoinBot):
    kind = "futures"

    def on_candle(self, ctx, s, i):
        fast, slow = s.get("ema", self.p["fast"]), s.get("ema", self.p["slow"])
        if None in (fast[i], slow[i]):
            return
        c = s.candles[i]
        if self.acct.check_liquidation(c, ctx.t):
            return
        want = "long" if fast[i] > slow[i] else "short"
        pos = self.acct.open_position
        if pos and pos["side"] == want:
            return
        if pos:
            self.acct.close(c["c"], ctx.t, "signal flipped to %s" % want)
        self.acct.open(self.pair, want, self.p["leverage"], c["c"], ctx.t, "go %s" % want)


class FuturesFlip(CoinBot):
    kind = "futures"

    def on_candle(self, ctx, s, i):
        c = s.candles[i]
        if self.acct.check_liquidation(c, ctx.t) or draw(self.seed, c["t"]) >= FLIP_ODDS:
            return
        if self.acct.open_position:
            self.acct.close(c["c"], ctx.t, "coin flip")
        else:
            side = "long" if draw(self.seed, c["t"], "side") < 0.5 else "short"
            self.acct.open(self.pair, side, self.p["leverage"], c["c"], ctx.t, "coin flip: %s" % side)


class Learner(SelfLearner):
    def __init__(self, account, pair, family):
        SelfLearner.__init__(self, account, pairs=(pair,))
        self.pair = pair
        self.coin = coin(pair)
        self.family = family
        self.key = bot_key(pair, family)
        self.title = "%s: %s" % (self.coin, family.label)


def _trend_rules(fast, slow, unit):
    return ("Buys when the %d-%s average is above the %d-%s average and price crosses or bounces above the faster one. "
            "Sells on a trailing stop 2.5x ATR below the high, or a close below the slower average." % (fast, unit, slow, unit))


def _dip_rules(below, band):
    return ("15-minute candles. Buys when RSI(14) falls below %d. Sells at +%d%%, -%d%%, when RSI recovers above 55, "
            "or after 12 hours." % (below, band * 100, band * 100))


def _flip_rules(n):
    return ("Luck control #%d. After every hourly candle a fixed pseudo-random draw decides: in cash, it buys with "
            "1-in-12 odds; holding, it sells with 1-in-12 odds. It pays the same costs as the others." % n)


FAMILIES = (
    Family("hold", "buy & hold", Hold, "Buys the coin once with all its money and never sells. Every other strategy on the "
           "coin is measured against this."),
    Family("trend_6_24h", "trend 6/24h", Trend, "1-hour candles. " + _trend_rules(6, 24, "hour"), interval="1h", fast=6, slow=24),
    Family("trend_12_48h", "trend 12/48h", Trend, "1-hour candles. " + _trend_rules(12, 48, "hour"), interval="1h", fast=12, slow=48),
    Family("trend_24_96h", "trend 24/96h", Trend, "1-hour candles. " + _trend_rules(24, 96, "hour"), interval="1h", fast=24, slow=96),
    Family("trend_2_8h", "fast trend 2/8h", Trend, "15-minute candles. " + _trend_rules(8, 32, "candle"), interval="15m", fast=8, slow=32),
    Family("trend_5_20h", "fast trend 5/20h", Trend, "15-minute candles. " + _trend_rules(20, 80, "candle"), interval="15m", fast=20, slow=80),
    Family("dip_25_3", "RSI dip <25 ±3%", Dip, _dip_rules(25, 0.03), below=25, band=0.03),
    Family("dip_30_3", "RSI dip <30 ±3%", Dip, _dip_rules(30, 0.03), below=30, band=0.03),
    Family("dip_30_6", "RSI dip <30 ±6%", Dip, _dip_rules(30, 0.06), below=30, band=0.06),
    Family("breakout_20_10h", "breakout 20/10h", Breakout, "1-hour candles. Buys a close above the 20-hour high. Sells a close "
           "below the 10-hour low, or at a stop 2x ATR below entry.", high=20, low=10),
    Family("breakout_48_24h", "breakout 48/24h", Breakout, "1-hour candles. Buys a close above the 48-hour high. Sells a close "
           "below the 24-hour low, or at a stop 2x ATR below entry.", high=48, low=24),
    Family("grid_1_5pct", "grid 1.5%", Grid, "15-minute candles. Splits the money into 6 lots, buys a lot each time price falls "
           "another 1.5%, and sells each lot 1.5% above where it bought. Re-centres when price runs up.", spacing=0.015),
    Family("grid_3pct", "grid 3%", Grid, "15-minute candles. Same as the 1.5% grid with 3% steps.", spacing=0.03),
    Family("pump", "pump rider", PumpRider, "1-hour candles. Buys when the coin is up 8% or more in 24 hours, the last candle "
           "closed green, and price is above its 20-hour average. Sells on a trailing stop 3x ATR below the high, a close "
           "below the 20-hour average, or after 24 hours."),
    Family("flip_1", "coin flip #1", CoinFlip, _flip_rules(1), luck=True),
    Family("flip_2", "coin flip #2", CoinFlip, _flip_rules(2), luck=True),
    Family("flip_3", "coin flip #3", CoinFlip, _flip_rules(3), luck=True),
    Family("trend_3x", "3x futures trend", FuturesTrend, "Always all-in on futures at 3x: long when the 9-hour average is "
           "above the 21-hour average, short otherwise. A 33% move the wrong way wipes out the position.",
           fast=9, slow=21, leverage=3),
    Family("trend_10x", "10x futures trend", FuturesTrend, "The same at 10x. A 9.5% move the wrong way wipes out the position.",
           fast=9, slow=21, leverage=10),
    Family("long_short", "long/short 12/48h", FuturesTrend, "Futures at 1x: long when the 12-hour "
           "average is above the 48-hour average, short otherwise.", fast=12, slow=48, leverage=1),
    Family("flip_3x", "coin flip, 3x futures", FuturesFlip, "Luck control on futures at 3x. After every hourly candle, with "
           "1-in-12 odds, it opens a random long or short when flat, or closes its position.", luck=True, leverage=3),
    Family("learner", "self-learning", Learner, "The self-learning bot on this coin alone: 11 shadow variants (trend long/short "
           "and long-only, breakouts, RSI reversion, hold long, hold short), following the best one after costs, at 1x or less, "
           "with the same loss brake and capital floor."),
)


def specs(universe):
    out = []
    for pair in universe:
        for family in FAMILIES:
            out.append((bot_key(pair, family), family.kind,
                        lambda account, pair=pair, family=family: family.cls(account, pair, family)))
    return out
