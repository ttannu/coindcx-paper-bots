"""Four slow, single-wallet research portfolios. Paper only, with no order API.

These strategies failed the historical profit screen. Their sole purpose here is
to collect independent forward observations without mixing them into the older
leaderboard or implying that four virtual wallets represent extra real capital.
"""

import bisect

from .bots import Bot, coin
from .slow_signals import HOUR_MS, PAIRS, POLICIES, History, targets


LABELS = {
    "btc_sma30": "BTC 30-day trend timing",
    "tsmom30": "four-coin 30-day time-series momentum",
    "crossmom7": "four-coin 7-day relative momentum",
    "donchian20_10": "four-coin 20/10-day breakout",
}


class SlowPortfolio(Bot):
    kind = "spot"
    research_cohort = True
    subscriptions = tuple((pair, "1h") for pair in PAIRS)

    def __init__(self, account, policy):
        super().__init__(account)
        self.policy = policy
        self.key = "slow_" + policy
        self.title = LABELS[policy]
        self.rules = ("Single ₹5,000 virtual spot portfolio; uses only completed hourly candles, reviews every %d hours, "
                      "and acts on a signal at the following hourly close. Historical profit screen failed; paper only." %
                      POLICIES[policy])

    @staticmethod
    def _histories(ctx):
        histories = {}
        for pair in PAIRS:
            series = ctx.series.get((pair, "1h"))
            if series is None:
                raise ValueError("missing hourly series for %s" % pair)
            # A scheduled run may replay several days. Discard all later candles
            # so even a future data gap cannot change an earlier decision.
            i = bisect.bisect_left([c["t"] for c in series.candles], ctx.t)
            histories[pair] = History(pair, series.candles[max(0, i - 721):i])
            histories[pair].closed(ctx.t, 1)
        return histories

    def _execute(self, ctx, histories, desired):
        bars = {pair: histories[pair].closed(ctx.t, 1)[-1] for pair in PAIRS}
        prices = {pair: bars[pair]["c"] for pair in PAIRS}
        held = self.acct.s["positions"]
        def liquid_enough(pair, approximate_value):
            # Unlike the old bots, do not claim a fill on a quiet hourly candle.
            # This remains only a proxy for actual order-book depth.
            if bars[pair]["v"] * bars[pair]["c"] < 10 * approximate_value:
                self.acct.memo["liquidity_deferrals"] = self.acct.memo.get("liquidity_deferrals", 0) + 1
                return False
            return True

        deferred_exit = False
        for pair in sorted(set(held) - set(desired)):
            if liquid_enough(pair, held[pair]["qty"] * prices[pair]):
                self.acct.sell(pair, prices[pair], ctx.t, self.policy + " exit, prior-hour signal")
            else:
                deferred_exit = True
        if deferred_exit:
            return False

        deferred_entry = False
        for pair in sorted(set(desired) - set(held)):
            equity = self.acct.liquidation_value(prices, ctx.t)
            if not liquid_enough(pair, desired[pair] * max(0.0, equity)):
                deferred_entry = True
                continue
            budget = min(desired[pair] * max(0.0, equity),
                         max(0.0, self.acct.cash - self.acct.s["tax_due"]))
            self.acct.buy(pair, budget, prices[pair], ctx.t, self.policy + " entry, prior-hour signal")
        return not deferred_entry

    def on_candle(self, ctx, s, i):
        if s.pair != PAIRS[0] or s.interval != "1h":
            return
        memo = self.acct.memo
        memo.setdefault("joined", ctx.t)
        try:
            histories = self._histories(ctx)
        except ValueError:
            memo["missing_history_hours"] = memo.get("missing_history_hours", 0) + 1
            return
        pending = memo.get("pending")
        if pending and ctx.t >= pending["due"]:
            # If the scheduled hour was missed, its signal is stale. After a
            # liquidity deferral, use the newest completed bar before retrying.
            filled = ctx.t == pending["due"] and self._execute(ctx, histories, pending["target"])
            del memo["pending"]
            if not filled:
                memo["next_review"] = ctx.t
        # A breach starts a cash exit at the next available hour even when the
        # normal signal review is days away.
        prices = {pair: histories[pair].closed(ctx.t, 1)[-1]["c"] for pair in PAIRS}
        current_value = self.acct.liquidation_value(prices, ctx.t)
        peak = max(self.acct.s["peak"], current_value)
        if not memo.get("halted") and (current_value <= 0.80 * self.acct.s["capital"] or
                                        (peak > 0 and current_value <= 0.80 * peak)):
            memo["halted"] = True
            memo["pending"] = {"due": ctx.t + HOUR_MS, "target": {}}
        if ctx.t < memo.get("next_review", 0):
            return
        try:
            desired = targets(self.policy, histories, ctx.t, self.acct.s["positions"])
        except ValueError:
            memo["missing_history_hours"] = memo.get("missing_history_hours", 0) + 1
            memo["next_review"] = ctx.t + HOUR_MS
            return
        if memo.get("halted"):
            desired = {}
        memo["pending"] = {"due": ctx.t + HOUR_MS, "target": desired}
        memo["next_review"] = ctx.t + POLICIES[self.policy] * HOUR_MS

    def describe(self):
        held = sorted(coin(pair) for pair in self.acct.s["positions"])
        if held:
            return "holding " + ", ".join(held)
        if self.acct.memo.get("halted"):
            return "cash, loss brake triggered"
        return "cash"


def specs():
    return [("slow_" + policy, "spot", lambda account, policy=policy: SlowPortfolio(account, policy))
            for policy in LABELS]
