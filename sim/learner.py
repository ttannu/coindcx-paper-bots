import math
from collections import OrderedDict

from .accounts import FuturesAccount
from .bots import BTC, ETH, HOUR_MS, Bot, coin

WINDOW_HOURS = 72
MIN_HISTORY_HOURS = 24
WARMUP_HOURS = 168
SWITCH_MARGIN = 0.02
MIN_EDGE = 0.02
MIN_HOLD_MS = 12 * HOUR_MS
TARGET_HOURLY_VOL = 0.008
MIN_EXPOSURE = 0.1
BRAKE = 0.92
COOLDOWN_MS = 24 * HOUR_MS
FLOOR = 0.85


def _trend(fast, slow, shorts):
    def signal(s, i, current):
        f, m = s.get("ema", fast)[i], s.get("ema", slow)[i]
        if f is None or m is None:
            return current
        if f > m:
            return 1
        return -1 if shorts else 0
    return signal


def _breakout(period):
    def signal(s, i, current):
        high, low = s.get("high", period)[i], s.get("low", period)[i]
        if high is None or low is None:
            return current
        if s.closes[i] > high:
            return 1
        if s.closes[i] < low:
            return -1
        return current
    return signal


def _reversion(s, i, current):
    r = s.get("rsi", 14)[i]
    if r is None:
        return current
    if r < 30:
        return 1
    if r > 70:
        return -1
    if (current == 1 and r >= 50) or (current == -1 and r <= 50):
        return 0
    return current


def _hold(direction):
    return lambda s, i, current: direction


def _variants(pairs):
    out = OrderedDict()
    for pair in pairs:
        name = coin(pair)
        for fast, slow in ((6, 24), (12, 48), (24, 96)):
            out["%s trend %d/%dh" % (name, fast, slow)] = (pair, _trend(fast, slow, True))
            out["%s trend %d/%dh, long only" % (name, fast, slow)] = (pair, _trend(fast, slow, False))
        for period in (24, 72):
            out["%s %dh breakout" % (name, period)] = (pair, _breakout(period))
        out["%s RSI reversion" % name] = (pair, _reversion)
        out["%s hold long" % name] = (pair, _hold(1))
        out["%s hold short" % name] = (pair, _hold(-1))
    return out


def _ignore(row):
    pass


def _direction(pos):
    if not pos:
        return 0
    return 1 if pos["side"] == "long" else -1


class SelfLearner(Bot):
    key = "self_learning"
    title = "Self-learning ensemble"
    rules = ("Runs 22 strategy variants on BTC and ETH (trend, breakout, mean reversion, hold long, hold short) "
             "as unfunded shadow accounts that pay the same costs, and scores each on its last 3 days after fees and tax. "
             "Every hour it follows the best one. It switches only when another is ahead by more than 2 points and at least "
             "12 hours have passed since its last change, and it holds cash when none has made at least 2%. "
             "Trades futures at 1x or less (lower liquidation risk than leveraged futures, about a tenth of spot fees) and takes smaller "
             "positions when the market is swinging hard. Studies the previous 7 days before its first trade. "
             "Checked every 15 minutes: if it falls 8% below its best value it holds cash for 24 hours, and if it "
             "falls 15% below its starting money it stops trading for good.")
    kind = "futures"
    pairs = (BTC, ETH)

    def __init__(self, account, pairs=None):
        Bot.__init__(self, account)
        if pairs is not None:
            self.pairs = tuple(pairs)
        self.subscriptions = tuple((p, "1h") for p in self.pairs)
        self.variants = _variants(self.pairs)
        memo = account.memo
        for key, default in (("shadows", {}), ("history", {}), ("signals", {}), ("leader", None), ("since", 0),
                             ("warm", False), ("cooldown_until", 0), ("brake_peak", account.s["capital"]),
                             ("stopped", False)):
            memo.setdefault(key, default)
        self.shadows = OrderedDict()
        for key in self.variants:
            if key not in memo["shadows"]:
                memo["shadows"][key] = FuturesAccount.fresh(account.s["capital"])
            self.shadows[key] = FuturesAccount(memo["shadows"][key], account.costs, account.markets, _ignore)

    def on_candle(self, ctx, s, i):
        if not self.acct.memo["warm"]:
            self._warm_up(ctx)
        mine = self.acct.open_position
        if mine and mine["pair"] == s.pair:
            self.acct.check_liquidation(s.candles[i], ctx.t)
        self._step_shadows(s, i, ctx.t)

    def on_tick(self, ctx):
        if not self.acct.memo["warm"]:
            return
        on_the_hour = ctx.t % HOUR_MS == 0
        if on_the_hour:
            self._record(ctx.prices, ctx.t)
        if self._protect(ctx) or not on_the_hour:
            return
        self._follow(ctx, self._choose(ctx))

    def _protect(self, ctx):
        memo = self.acct.memo
        if memo["stopped"]:
            return True
        value = self.acct.liquidation_value(ctx.prices, ctx.t)
        if value <= FLOOR * self.acct.s["capital"]:
            self._exit(ctx, "capital floor reached, stopping for good")
            memo["stopped"] = True
            return True
        if memo["cooldown_until"]:
            if ctx.t < memo["cooldown_until"]:
                return True
            memo["cooldown_until"] = 0
            memo["brake_peak"] = value
        memo["brake_peak"] = max(memo["brake_peak"], value)
        if value <= BRAKE * memo["brake_peak"]:
            self._exit(ctx, "loss brake, cash for 24 hours")
            memo["cooldown_until"] = ctx.t + COOLDOWN_MS
            return True
        return False

    def _exit(self, ctx, reason):
        mine = self.acct.open_position
        if mine:
            self.acct.close(ctx.prices[mine["pair"]], ctx.t, reason)
        self.acct.memo["leader"] = None
        self.acct.memo["since"] = ctx.t

    def _exposure(self, ctx, pair):
        s = ctx.series.get((pair, "1h"))
        closes = [c["c"] for c in s.candles if c["t"] + HOUR_MS <= ctx.t][-25:] if s else []
        if len(closes) < 25:
            return 1.0
        rets = [math.log(b / a) for a, b in zip(closes, closes[1:])]
        mean = sum(rets) / len(rets)
        vol = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
        return 1.0 if vol <= TARGET_HOURLY_VOL else round(TARGET_HOURLY_VOL / vol, 2)

    def _warm_up(self, ctx):
        start = ctx.t - WARMUP_HOURS * HOUR_MS
        events = []
        for pair in self.pairs:
            s = ctx.series.get((pair, "1h"))
            for i, c in enumerate(s.candles if s else ()):
                if start <= c["t"] + HOUR_MS < ctx.t:
                    events.append((c["t"] + HOUR_MS, pair, i))
        events.sort()
        prices = {}
        for n, (close_t, pair, i) in enumerate(events):
            s = ctx.series[(pair, "1h")]
            prices[pair] = s.closes[i]
            self._step_shadows(s, i, close_t)
            if n + 1 == len(events) or events[n + 1][0] != close_t:
                self._record(prices, close_t)
        self.acct.memo["warm"] = True

    def _step_shadows(self, s, i, t):
        signals = self.acct.memo["signals"]
        candle = s.candles[i]
        for key, (pair, signal) in self.variants.items():
            if pair != s.pair:
                continue
            shadow = self.shadows[key]
            shadow.check_liquidation(candle, t)
            want = signal(s, i, signals.get(key, 0))
            signals[key] = want
            if want == _direction(shadow.open_position):
                continue
            if shadow.open_position:
                shadow.close(candle["c"], t, "signal")
            if want:
                shadow.open(pair, "long" if want > 0 else "short", 1, candle["c"], t, "signal")

    def _record(self, prices, t):
        history = self.acct.memo["history"]
        for key, shadow in self.shadows.items():
            values = history.setdefault(key, [])
            values.append(round(shadow.liquidation_value(prices, t), 2))
            del values[:-(WINDOW_HOURS + 1)]

    def scores(self):
        out = {}
        for key, values in self.acct.memo["history"].items():
            if key in self.variants and len(values) > MIN_HISTORY_HOURS and values[0] > 0:
                out[key] = values[-1] / values[0] - 1
        return out

    def _choose(self, ctx):
        memo = self.acct.memo
        scores = self.scores()
        leader = memo["leader"]
        if scores:
            best = max(scores, key=scores.get)
            if leader not in scores or scores[best] > scores[leader] + SWITCH_MARGIN or scores[leader] < MIN_EDGE:
                leader = best
        if leader not in scores or scores[leader] < MIN_EDGE:
            leader = None
        if leader != memo["leader"]:
            if ctx.t - memo["since"] < MIN_HOLD_MS:
                return memo["leader"]
            memo["since"] = ctx.t
        memo["leader"] = leader
        return leader

    def _follow(self, ctx, leader):
        want = self.shadows[leader].open_position if leader else None
        target = (want["pair"], want["side"]) if want else None
        mine = self.acct.open_position
        if mine and (mine["pair"], mine["side"]) == target:
            return
        if mine:
            self.acct.close(ctx.prices[mine["pair"]], ctx.t, "switching to %s" % (leader or "cash"))
        exposure = self._exposure(ctx, target[0]) if target else 0
        if exposure >= MIN_EXPOSURE:
            self.acct.open(target[0], target[1], exposure, ctx.prices[target[0]], ctx.t, "following %s" % leader)

    def describe(self):
        memo = self.acct.memo
        mine = self.acct.open_position
        if not memo["warm"]:
            return "studying"
        if memo["stopped"]:
            return "cash, stopped at the capital floor"
        if memo["cooldown_until"]:
            return "cash, loss brake"
        if mine:
            return "%s %s at %gx, following %s" % (mine["side"], coin(mine["pair"]), mine["leverage"], memo["leader"])
        if memo["leader"]:
            return "cash, following %s" % memo["leader"]
        return "cash, nothing has an edge"

    def insights(self, top=5):
        scores = self.scores()
        signals = self.acct.memo["signals"]
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top]
        names = {1: "long", -1: "short", 0: "flat"}
        return [(key, score, names[signals.get(key, 0)]) for key, score in ranked]
