import json
import os
import re
import unittest

import test_robustness as rb
from sim import report, swarm
from sim.accounts import FuturesAccount, SpotAccount
from synthetic import DAY, START, build_market, make_fetch

BTC, SOL = "I-BTC_INR", "I-SOL_INR"
H8 = 8 * 3600000


def read_config():
    with open(os.path.join(rb.ROOT, "config.json"), encoding="utf-8") as fh:
        return json.load(fh)


class BreakdownTest(unittest.TestCase):
    def setUp(self):
        config = read_config()
        self.costs, self.markets = config["costs"], config["markets"]

    def spot(self):
        return SpotAccount(SpotAccount.fresh(5000), self.costs, self.markets, lambda row: None)

    def futures(self):
        return FuturesAccount(FuturesAccount.fresh(5000), self.costs, self.markets, lambda row: None)

    def assertAddsUp(self, acct, prices, t):
        m = acct.breakdown(prices, t)
        self.assertAlmostEqual(m["net"], acct.liquidation_value(prices, t) - 5000, places=6)
        self.assertAlmostEqual(m["moves"] - m["spread"] - m["fees"] - m["tax"] - m["funding"], m["net"], places=6)
        for part in ("spread", "fees", "tax", "funding"):
            self.assertGreaterEqual(m[part], 0.0, part)
        return m

    def test_price_moves_are_measured_at_market_prices(self):
        acct = self.spot()
        qty = acct.buy(BTC, 5000, 8.0e6, 0, "test")
        held = self.assertAddsUp(acct, {BTC: 8.4e6}, 1)
        self.assertAlmostEqual(held["moves"], qty * 0.4e6, places=6)
        self.assertAlmostEqual(held["spread"], qty * (8.0e6 + 8.4e6) * self.markets[BTC]["slippage"], places=6)
        self.assertGreater(held["tax"], 0)
        acct.sell(BTC, 8.4e6, 2, "test")
        sold = self.assertAddsUp(acct, {BTC: 8.4e6}, 3)
        for part in ("moves", "spread", "fees", "tax", "net"):
            self.assertAlmostEqual(sold[part], held[part], places=6, msg=part)

    def test_tax_is_paid_on_a_winning_sale_even_when_the_book_loses(self):
        acct = self.spot()
        acct.buy(SOL, 2500, 12000, 0, "test")
        acct.buy(BTC, 2500, 8.0e6, 0, "test")
        acct.sell(SOL, 13000, 1, "test")
        acct.sell(BTC, 7.0e6, 1, "test")
        m = self.assertAddsUp(acct, {SOL: 13000, BTC: 7.0e6}, 2)
        self.assertLess(m["net"], 0)
        self.assertGreater(m["tax"], 0)

    def test_a_futures_round_trip_at_one_price_loses_only_costs(self):
        acct = self.futures()
        acct.open(BTC, "long", 3, 8.0e6, 0, "test")
        still_open = self.assertAddsUp(acct, {BTC: 8.0e6}, H8)
        self.assertAlmostEqual(still_open["moves"], 0.0, places=6)
        self.assertGreater(still_open["funding"], 0)
        acct.close(8.0e6, H8, "test")
        closed = self.assertAddsUp(acct, {BTC: 8.0e6}, 2 * H8)
        self.assertAlmostEqual(closed["moves"], 0.0, places=6)
        self.assertEqual(closed["tax"], 0.0)
        for part in ("spread", "fees", "funding", "net"):
            self.assertAlmostEqual(closed[part], still_open[part], places=6, msg=part)

    def test_a_short_that_wins_pays_tax_on_the_gain(self):
        acct = self.futures()
        acct.open(SOL, "short", 2, 12000, 0, "test")
        acct.close(11000, H8, "test")
        m = self.assertAddsUp(acct, {SOL: 11000}, H8)
        self.assertGreater(m["moves"], 0)
        self.assertGreater(m["tax"], 0)


class MoneyReportTest(unittest.TestCase):
    def test_the_dashboard_shows_where_the_money_went(self):
        fetch = make_fetch(build_market("chop", seed=27))
        ws = rb.Workspace()
        try:
            ws.run(START + 2 * DAY, fetch, notify=False)
            state = ws.state()
            rb.check_invariants(self, state)
            with open(os.path.join(ws.root, "README.md"), encoding="utf-8") as fh:
                readme = fh.read()
        finally:
            ws.close()
        block = readme[readme.index(report.START_MARK):readme.index(report.END_MARK)]
        self.assertIn("**Where the money went.** On average a bot's trades have made ", block)
        table = block.split("**Where the money went.**")[1].split("![Value of the top bots")[0]
        rows = [line for line in table.splitlines() if line.startswith("| ") and not line.startswith("| Strategy")]
        labels = [line.split(" | ")[0][2:] for line in rows]
        self.assertEqual(labels[-1], "**All bots**")
        self.assertEqual(len(rows), len(swarm.FAMILIES) + 4)
        for label in ("Original bots", "Added on 1 Oct", "AI desk"):
            self.assertIn(label, labels)
        self.assertIn("| **All bots** | %s |" % "{:,}".format(len(state["bots"])), table)
        for line in rows:
            cells = line.strip("| ").split(" | ")
            numbers = [0.0 if c == "–" else float(c.rstrip("%")) for c in cells[2:]]
            moves, spread, fees, tax, funding, result = numbers
            self.assertAlmostEqual(moves + spread + fees + tax + funding, result, delta=0.3, msg=line)
            for cost in (spread, fees, tax, funding):
                self.assertLessEqual(cost, 0.0, line)
        match = re.search(r"(\d+) of the (\d+) strategies are ahead before costs, and (\d+) after them", block)
        self.assertEqual(int(match.group(2)), len(swarm.FAMILIES))
        self.assertLessEqual(int(match.group(3)), int(match.group(2)))


if __name__ == "__main__":
    unittest.main()
