import json
import os
import unittest
from types import SimpleNamespace

import test_robustness as rb
from sim import engine, lowcost, report, swarm
from sim.accounts import SpotAccount
from synthetic import DAY, H1, START, build_market, make_fetch

MINUTE = 60000
M15 = 15 * MINUTE
# Market orders on the same draws, so only the fee differs.
SAME_CALLS = ("hold", "flip_1")
LIMIT_ONLY = ("grid_1_5pct", "grid_3pct")


def read_config():
    with open(os.path.join(rb.ROOT, "config.json"), encoding="utf-8") as fh:
        return json.load(fh)


def candle(t, o, h, l, c):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": 1.0}


class Series:
    def __init__(self, candles, rsi):
        self.candles = candles
        self.rsi = rsi

    def get(self, name, period):
        return self.rsi


class LowCostTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws = rb.Workspace()
        fetch = make_fetch(build_market("chop", seed=31))
        now = START + 7 * MINUTE
        while now < START + 3 * DAY:
            cls.ws.run(now, fetch, notify=False)
            now += 5 * H1
        cls.state = cls.ws.state()
        with open(os.path.join(cls.ws.root, "README.md"), encoding="utf-8") as fh:
            readme = fh.read()
        cls.block = readme[readme.index(report.START_MARK):readme.index(report.END_MARK)]

    @classmethod
    def tearDownClass(cls):
        cls.ws.close()

    def test_every_twin_pays_the_vip_fee(self):
        config = read_config()
        bots = engine._build_bots({"bots": {}}, config, [])
        twins = [bot for bot in bots if getattr(bot, "lowcost", False)]
        self.assertEqual(len(twins), len(config["universe"]) * len(config["low_cost"]["families"]))
        normal = dict((bot.key, bot) for bot in bots if not getattr(bot, "lowcost", False))
        for bot in twins:
            base = normal[swarm.bot_key(bot.pair, bot.family.base)]
            self.assertIs(type(bot), lowcost.LIMIT.get(type(base), type(base)))
            self.assertEqual(bot.seed, base.key)
            self.assertAlmostEqual(bot.acct._fee_rate(), config["low_cost"]["spot_fee_rate"] * (1 + config["costs"]["gst_rate"]))
            self.assertAlmostEqual(base.acct._fee_rate(), config["costs"]["spot_fee_rate"] * (1 + config["costs"]["gst_rate"]))
            self.assertEqual(bot.acct._slippage(bot.pair), config["markets"][bot.pair]["slippage"])

    def test_twins_make_the_same_calls_and_keep_more(self):
        bots = self.state["bots"]
        rb.check_invariants(self, self.state)
        compared = 0
        for key, twin in bots.items():
            if not key.endswith("_low"):
                continue
            base = bots[key[:-len("_low")]]
            family = key.split(".")[1][:-len("_low")]
            if family in LIMIT_ONLY:
                self.assertEqual(twin["spread"], 0.0, key)
            if family in SAME_CALLS:
                self.assertEqual(twin["trades"], base["trades"], key)
                self.assertEqual(sorted(twin["positions"]), sorted(base["positions"]), key)
                if base["fees"]:
                    self.assertLess(twin["fees"], base["fees"], key)
                    self.assertGreater(twin["last_value"], base["last_value"], key)
                    compared += 1
        self.assertGreaterEqual(compared, 2)

    def test_twins_stay_out_of_the_rankings(self):
        ranked = sum(1 for key in self.state["bots"]
                     if not key.endswith("_low") and not key.startswith("slow_"))
        self.assertIn("%s bots on 2 coins." % "{:,}".format(ranked), self.block)
        top = self.block.split("**Top 15 bots**")[1].split("**The original bots**")[0]
        self.assertNotIn("low cost", top)
        with open(os.path.join(self.ws.root, "docs", "equity.svg"), encoding="utf-8") as fh:
            self.assertIn("Median of all %s bots" % "{:,}".format(ranked), fh.read())

    def test_the_dashboard_compares_each_twin_with_its_original(self):
        config = read_config()
        self.assertIn("**Low-cost test.** Since 1 Oct", self.block)
        self.assertIn("(0.17% instead of 0.5%, plus GST)", self.block)
        table = self.block.split("**Low-cost test.**")[1].split("![Value of the top bots")[0]
        rows = [line for line in table.splitlines() if line.startswith("| ") and not line.startswith("| Strategy")]
        labels = sorted(line.split(" | ")[0][2:] for line in rows)
        names = dict((f.key, f.label[0].upper() + f.label[1:]) for f in swarm.FAMILIES)
        self.assertEqual(labels, sorted(names[key] for key in config["low_cost"]["families"]))
        for line in rows:
            cells = line.strip("| ").split(" | ")
            self.assertRegex(cells[3], r"^-\d+\.\d% → [-+]\d+\.\d%$", line)
            self.assertRegex(cells[4], r"^\d+/2$", line)
        self.assertRegex(table, r"VIP 1 needs ₹5,00,000 of trading in 30 days\. The busiest of these strategies, .+, has "
                                r"traded ₹[\d,]+ per bot in \d+\.\d days, a pace of ₹[\d,]+ a month")


class LimitOrderTest(unittest.TestCase):
    def setUp(self):
        config = read_config()
        self.pair = config["universe"][0]
        self.costs = dict(config["costs"], spot_fee_rate=config["low_cost"]["spot_fee_rate"])
        self.markets = {self.pair: {"step": 0.0001, "min_qty": 0.0001, "min_notional": 10.0, "slippage": 0.004}}
        self.trades = []

    def feed(self, key, candles, rsi=None):
        family = lowcost.family(dict((f.key, f) for f in swarm.FAMILIES)[key])
        bot = family.cls(SpotAccount(SpotAccount.fresh(5000), self.costs, self.markets, self.trades.append), self.pair, family)
        series = Series(candles, rsi)
        for i, c in enumerate(candles):
            bot.on_candle(SimpleNamespace(t=c["t"] + M15), series, i)
        return bot

    def fills(self):
        return [(t["side"], round(t["price"], 6)) for t in self.trades]

    def test_a_grid_fills_at_its_own_prices_and_only_through_them(self):
        step = 1 - 0.015
        level1, level2 = 100 * step, 100 * step ** 2
        bot = self.feed("grid_1_5pct", [
            candle(0, 100, 100, 100, 100),
            candle(M15, 99, 99, level1, 99),
            candle(2 * M15, 97, 97.5, 96.9, 97),
            candle(3 * M15, 100.5, 101, 100, 100.5),
        ])
        self.assertEqual(self.fills(), [("BUY", round(level1, 6)), ("BUY", round(level2, 6)),
                                        ("SELL", round(level1 * 1.015, 6)), ("SELL", round(level2 * 1.015, 6))])
        self.assertEqual(bot.acct.s["spread"], 0.0)

    def test_a_dip_buyer_bids_for_an_hour_and_its_stop_pays_the_spread(self):
        bot = self.feed("dip_30_3", [
            candle(0, 100, 100, 99, 99),
            candle(M15, 99, 99.5, 99, 99.2),
            candle(2 * M15, 99.2, 99.6, 99.1, 99.5),
            candle(3 * M15, 99.5, 99.8, 99.3, 99.6),
            candle(4 * M15, 99.6, 99.9, 99.4, 99.7),
            candle(5 * M15, 99.7, 99.7, 98, 98),
            candle(6 * M15, 98, 98.2, 97.5, 98),
            candle(7 * M15, 98.5, 101.5, 98.4, 101),
            candle(8 * M15, 101, 101, 100, 100),
            candle(9 * M15, 100, 100, 99.5, 99.6),
            candle(10 * M15, 99.6, 99.6, 96.5, 96.8),
        ], rsi=[25, 40, 40, 40, 40, 25, 40, 40, 25, 40, 40])
        self.assertEqual(self.fills(), [("BUY", 98.0), ("SELL", round(98 * 1.03, 6)),
                                        ("BUY", 100.0), ("SELL", round(97 * (1 - 0.004), 6))])
        self.assertAlmostEqual(bot.acct.s["spread"], self.trades[-1]["qty"] * 97 * 0.004)


if __name__ == "__main__":
    unittest.main()
