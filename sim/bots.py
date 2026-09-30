BTC, ETH, SOL, XRP, DOGE = "I-BTC_INR", "I-ETH_INR", "I-SOL_INR", "I-XRP_INR", "I-DOGE_INR"
HOUR_MS = 3600000


class Bot:
    key = ""
    title = ""
    rules = ""
    kind = "spot"
    subscriptions = ()

    def __init__(self, account):
        self.acct = account

    def on_candle(self, ctx, series, i):
        raise NotImplementedError

    def on_tick(self, ctx):
        pass

    def describe(self):
        return None

    def value(self, prices, t):
        try:
            return self.acct.liquidation_value(prices, t)
        except Exception:  # a broken bot is shown at its last known value instead of stopping the run
            return self.acct.s.get("last_value", self.acct.s["capital"])


class BuyAndHold(Bot):
    key = "hodl_btc"
    title = "Buy & hold BTC"
    rules = "Benchmark. Buys Bitcoin once with all ₹5,000 and never sells."
    subscriptions = ((BTC, "15m"),)

    def on_candle(self, ctx, s, i):
        if not self.acct.memo.get("bought"):
            self.acct.memo["bought"] = bool(self.acct.buy(BTC, self.acct.cash, s.candles[i]["c"], ctx.t, "one-time buy"))


class TrendFollower(Bot):
    key = "trend_ema"
    title = "Trend follower"
    rules = ("1-hour candles on BTC, ETH, SOL. Buys when the 20-hour average is above the 50-hour average "
             "and price bounces back above the 20-hour average. Sells on a trailing stop (2.5x ATR) "
             "or when price closes below the 50-hour average.")
    pairs = (BTC, ETH, SOL)
    subscriptions = tuple((p, "1h") for p in pairs)

    def on_candle(self, ctx, s, i):
        fast, slow, atr = s.get("ema", 20), s.get("ema", 50), s.get("atr", 14)
        if i < 1 or None in (fast[i], slow[i], atr[i], fast[i - 1], slow[i - 1]):
            return
        c = s.candles[i]
        pos = self.acct.position(s.pair)
        if pos:
            if c["l"] <= pos["stop"]:
                self.acct.sell(s.pair, min(pos["stop"], c["o"]), ctx.t, "trailing stop")
            elif c["c"] < slow[i]:
                self.acct.sell(s.pair, c["c"], ctx.t, "closed below 50-hour average")
            else:
                pos["peak"] = max(pos["peak"], c["c"])
                pos["stop"] = max(pos["stop"], pos["peak"] - 2.5 * atr[i])
            return
        crossed_up = fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]
        bounced = fast[i] > slow[i] and c["c"] > fast[i] and s.closes[i - 1] <= fast[i - 1]
        if (crossed_up or bounced) and self.acct.buy(s.pair, ctx.equity(self.acct) / len(self.pairs), c["c"], ctx.t, "uptrend entry"):
            pos = self.acct.position(s.pair)
            pos["peak"] = c["c"]
            pos["stop"] = c["c"] - 2.5 * atr[i]


class DipBuyer(Bot):
    key = "rsi_dip"
    title = "Dip buyer (RSI)"
    rules = ("15-minute candles on BTC and ETH. Buys when RSI(14) falls below 30. "
             "Sells at +3% profit, -3% loss, when RSI recovers above 55, or after 12 hours.")
    pairs = (BTC, ETH)
    subscriptions = tuple((p, "15m") for p in pairs)

    def on_candle(self, ctx, s, i):
        rsi = s.get("rsi", 14)
        if rsi[i] is None:
            return
        c = s.candles[i]
        pos = self.acct.position(s.pair)
        if pos:
            if c["l"] <= pos["stop"]:
                self.acct.sell(s.pair, min(pos["stop"], c["o"]), ctx.t, "stop loss -3%")
            elif c["h"] >= pos["target"]:
                self.acct.sell(s.pair, max(pos["target"], c["o"]), ctx.t, "take profit +3%")
            elif rsi[i] > 55:
                self.acct.sell(s.pair, c["c"], ctx.t, "RSI recovered to %.0f" % rsi[i])
            elif ctx.t - pos["t"] >= 12 * HOUR_MS:
                self.acct.sell(s.pair, c["c"], ctx.t, "12-hour time limit")
            return
        if rsi[i] < 30 and self.acct.buy(s.pair, ctx.equity(self.acct) / len(self.pairs), c["c"], ctx.t, "RSI %.0f" % rsi[i]):
            pos = self.acct.position(s.pair)
            entry = pos["cost"] / pos["qty"]
            pos["stop"] = entry * 0.97
            pos["target"] = entry * 1.03


class BreakoutHunter(Bot):
    key = "breakout"
    title = "Breakout hunter"
    rules = ("1-hour candles on BTC, ETH, SOL, XRP, DOGE. Buys when price closes above its 20-hour high. "
             "Sells when price closes below its 10-hour low or hits a stop 2x ATR below entry.")
    pairs = (BTC, ETH, SOL, XRP, DOGE)
    subscriptions = tuple((p, "1h") for p in pairs)

    def on_candle(self, ctx, s, i):
        high, low, atr = s.get("high", 20), s.get("low", 10), s.get("atr", 14)
        if None in (high[i], low[i], atr[i]):
            return
        c = s.candles[i]
        pos = self.acct.position(s.pair)
        if pos:
            if c["l"] <= pos["stop"]:
                self.acct.sell(s.pair, min(pos["stop"], c["o"]), ctx.t, "stop loss")
            elif c["c"] < low[i]:
                self.acct.sell(s.pair, c["c"], ctx.t, "broke 10-hour low")
            return
        if c["c"] > high[i] and self.acct.buy(s.pair, ctx.equity(self.acct) / len(self.pairs), c["c"], ctx.t, "20-hour breakout"):
            self.acct.position(s.pair)["stop"] = c["c"] - 2 * atr[i]


class GridTrader(Bot):
    key = "grid_btc"
    title = "Grid trader"
    rules = ("15-minute candles on BTC. Splits the money into 6 lots, buys a lot each time price falls "
             "another 2%, and sells each lot 2% above where it bought. Re-centres when price runs up.")
    subscriptions = ((BTC, "15m"),)
    spacing = 0.02
    levels = 6

    def on_candle(self, ctx, s, i):
        c = s.candles[i]
        grid = self.acct.memo
        if "center" not in grid:
            grid.update(center=c["c"], lots={}, lot_budget=self.acct.cash / self.levels)
            return
        lots = grid["lots"]
        for level in sorted(lots, key=int):
            lot = lots[level]
            if c["h"] >= lot["target"] and self.acct.sell(BTC, max(lot["target"], c["o"]), ctx.t, "grid sell, level %s" % level, qty=lot["qty"]):
                del lots[level]
        for k in range(1, self.levels + 1):
            price = grid["center"] * (1 - self.spacing) ** k
            if str(k) not in lots and c["l"] <= price:
                qty = self.acct.buy(BTC, grid["lot_budget"], min(price, c["o"]), ctx.t, "grid buy, level %d" % k)
                if qty:
                    lots[str(k)] = {"qty": qty, "target": price * (1 + self.spacing)}
        if not lots and c["c"] > grid["center"] * (1 + self.spacing):
            grid.update(center=c["c"], lot_budget=self.acct.cash / self.levels)


class GoalChaser(Bot):
    key = "goal_chaser_10x"
    title = "Goal chaser (10x futures)"
    rules = ("What chasing 20x in 15 days looks like. Always all-in on BTC futures at 10x leverage: "
             "long when the 9-hour average is above the 21-hour average, short otherwise. "
             "A 9.5% move the wrong way wipes out the position.")
    kind = "futures"
    subscriptions = ((BTC, "1h"),)
    leverage = 10

    def on_candle(self, ctx, s, i):
        fast, slow = s.get("ema", 9), s.get("ema", 21)
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
        self.acct.open(BTC, want, self.leverage, c["c"], ctx.t, "go %s" % want)


FIXED_BOTS = (BuyAndHold, TrendFollower, DipBuyer, BreakoutHunter, GridTrader, GoalChaser)
