"""Low-cost twins, added on 1 Oct 2026: the strategies that had an edge before costs in the backtests in docs/research.md,
with buy & hold and a coin flip to compare against, run again with CoinDCX's VIP 1 fee instead of 0.5%. The grids and
dip-buyers also use limit orders, which pay no spread but fill at exactly their price, and only once a later candle trades
through it: a gap past the price gets no better fill, and a candle that just touches it is taken to fill the orders queued
there first. Stops, RSI and time exits stay market orders and pay the spread, as do buy & hold's one purchase and the coin
flips, which therefore make exactly the same calls as their originals. Tax is unchanged."""
from . import swarm
from .bots import HOUR_MS

ORDER_MS = HOUR_MS


class LimitGrid(swarm.Grid):
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
            if c["h"] > lot["target"] and self.acct.sell(self.pair, lot["target"], ctx.t, "grid sell, level %s" % level,
                                                         qty=lot["qty"], limit=True):
                del lots[level]
        for k in range(1, self.levels + 1):
            price = grid["center"] * (1 - spacing) ** k
            if str(k) not in lots and c["l"] < price:
                qty = self.acct.buy(self.pair, grid["lot_budget"], price, ctx.t, "grid buy, level %d" % k, limit=True)
                if qty:
                    lots[str(k)] = {"qty": qty, "target": price * (1 + spacing)}
        if not lots and c["c"] > grid["center"] * (1 + spacing):
            grid.update(center=c["c"], lot_budget=self.acct.cash / self.levels)


class LimitDip(swarm.Dip):
    """On the signal it bids the candle's close for an hour instead of buying there, so it only gets in if the price keeps
    falling, which is when a real bid fills."""

    def on_candle(self, ctx, s, i):
        rsi = s.get("rsi", 14)
        if rsi[i] is None:
            return
        c = s.candles[i]
        memo = self.acct.memo
        pos = self.acct.position(self.pair)
        if pos:
            if c["l"] <= pos["stop"]:
                self.acct.sell(self.pair, min(pos["stop"], c["o"]), ctx.t, "stop loss")
            elif c["h"] > pos["target"]:
                self.acct.sell(self.pair, pos["target"], ctx.t, "take profit", limit=True)
            elif rsi[i] > 55:
                self.acct.sell(self.pair, c["c"], ctx.t, "RSI recovered to %.0f" % rsi[i])
            elif ctx.t - pos["t"] >= 12 * HOUR_MS:
                self.acct.sell(self.pair, c["c"], ctx.t, "12-hour time limit")
            return
        order = memo.get("order")
        if order:
            if c["l"] < order["price"] and self.acct.buy(self.pair, self.acct.cash, order["price"], ctx.t, order["reason"],
                                                          limit=True):
                del memo["order"]
                pos = self.acct.position(self.pair)
                entry = pos["cost"] / pos["qty"]
                pos["stop"] = entry * (1 - self.p["band"])
                pos["target"] = entry * (1 + self.p["band"])
                return
            if ctx.t < order["until"]:
                return
            del memo["order"]
        if rsi[i] < self.p["below"]:
            memo["order"] = {"price": c["c"], "until": ctx.t + ORDER_MS, "reason": "RSI %.0f, limit buy" % rsi[i]}


LIMIT = {swarm.Grid: LimitGrid, swarm.Dip: LimitDip}


def family(base):
    twin = swarm.Family(base.key + "_low", base.label + ", low cost", LIMIT.get(base.cls, base.cls), base.rules,
                        luck=base.luck, **base.params)
    twin.base = base
    return twin


def _make(account, pair, twin, costs):
    account.costs = costs
    bot = twin.cls(account, pair, twin)
    bot.lowcost = True
    bot.seed = swarm.bot_key(pair, twin.base)
    return bot


def specs(universe, config):
    low = config.get("low_cost")
    if not low:
        return []
    costs = dict(config["costs"], spot_fee_rate=low["spot_fee_rate"])
    by_key = dict((f.key, f) for f in swarm.FAMILIES)
    # Spot only: the VIP rate is a spot fee, and futures already pay 0.05%.
    twins = [family(by_key[key]) for key in low["families"] if by_key[key].kind == "spot"]
    return [(swarm.bot_key(pair, twin), twin.kind, lambda account, pair=pair, twin=twin: _make(account, pair, twin, costs))
            for pair in universe for twin in twins]
