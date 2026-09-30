"""The two bots added on 1 Oct: the 5 most traded coins held as a basket, with and without a BTC trend filter."""
import bisect
import csv
import json
import math
import os
import unittest

import test_robustness as rb
from sim import liquid
from synthetic import DAY, H1, M15, START, _hourly, build_market, make_fetch

MINUTE = 60000
MAJORS = ("I-BTC_INR", "I-ETH_INR", "I-SOL_INR", "I-XRP_INR", "I-DOGE_INR")
UNIVERSE = MAJORS + ("I-ADA_INR", "I-TRX_INR", "I-LINK_INR", "I-DOT_INR", "I-AVAX_INR", "I-BNB_INR", "I-UNI_INR")
HOLD, TREND = liquid.LiquidBasket.key, liquid.LiquidTrend.key
RISING = ((START - 30 * DAY, 1.0), (START + 15 * DAY, 1.5))
FALLING = ((START - 30 * DAY, 1.5), (START + 15 * DAY, 1.0))
TOPPING = ((START - 30 * DAY, 1.0), (START, 1.3), (START + DAY, 1.3), (START + 2 * DAY, 0.9))


def market(btc_path, seed):
    """Random coins, the majors traded ten times as much as the rest, and BTC following a fixed smooth path."""
    m = build_market("calm", seed, pairs=UNIVERSE)
    for (pair, interval), rows in m.items():
        if interval == "1h" and pair not in MAJORS:
            for row in rows:
                row["v"] *= 0.1
    times, factors = [t for t, _ in btc_path], [f for _, f in btc_path]

    def factor(t):
        i = bisect.bisect_right(times, t)
        if i == 0 or i == len(times):
            return factors[0] if i == 0 else factors[-1]
        w = float(t - times[i - 1]) / (times[i] - times[i - 1])
        return factors[i - 1] + w * (factors[i] - factors[i - 1])

    rows, price = [], 8.5e6 * factor(START - 43 * DAY)
    for row in m[("I-BTC_INR", "15m")]:
        close = 8.5e6 * factor(row["t"] + M15) * (1 + 0.001 * math.sin(row["t"] / H1))
        rows.append({"t": row["t"], "o": price, "h": max(price, close) * 1.001, "l": min(price, close) * 0.999,
                     "c": close, "v": 1e5 / close})
        price = close
    m[("I-BTC_INR", "15m")], m[("I-BTC_INR", "1h")] = rows, _hourly(rows)
    return m


class LiquidBotTest(unittest.TestCase):
    def setUp(self):
        self.ws = rb.Workspace(universe=UNIVERSE)

    def tearDown(self):
        self.ws.close()

    def run_until(self, fetch, end):
        now = START + 7 * MINUTE
        while now < end:
            self.ws.run(now, fetch, notify=False)
            now += 5 * H1
        self.ws.run(end, fetch, notify=False)
        state = self.ws.state()
        for key, b in state["bots"].items():
            self.assertNotEqual(b["status"], "error", "%s: %s" % (key, b.get("error")))
        for key in (HOLD, TREND):
            self.assertGreaterEqual(state["bots"][key]["cash"], -1e-6)
            self.assertTrue(math.isfinite(state["bots"][key]["last_value"]))
        return state

    def trades(self, key):
        path = os.path.join(self.ws.root, "state", "trades.csv")
        if not os.path.exists(path):
            return []
        with open(path, newline="", encoding="utf-8") as fh:
            return [r for r in csv.DictReader(fh) if r["bot"] == key]

    def test_both_buy_the_five_most_traded_coins_in_equal_parts_while_btc_rises(self):
        state = self.run_until(make_fetch(market(RISING, seed=31)), START + 2 * H1)
        for key in (HOLD, TREND):
            buys = self.trades(key)
            self.assertEqual(sorted(r["pair"] for r in buys), sorted(p[2:-4] + "/INR" for p in MAJORS), key)
            self.assertEqual(set(r["side"] for r in buys), {"BUY"})
            for r in buys:
                self.assertTrue(850 < float(r["value"]) < 1100, r)
            self.assertTrue(4850 < sum(float(r["value"]) for r in buys) < 5000)
            self.assertEqual(sorted(state["bots"][key]["positions"]), sorted(MAJORS))
        self.assertEqual(self.trades(TREND)[0]["reason"], "among the 5 most traded; BTC above its 30-day average")
        self.assertEqual(self.trades(HOLD)[0]["reason"], "among the 5 most traded")

    def test_a_coin_whose_smallest_order_is_too_big_is_passed_over(self):
        path = os.path.join(self.ws.root, "config.json")
        with open(path, encoding="utf-8") as fh:
            config = json.load(fh)
        config["markets"]["I-SOL_INR"]["min_qty"] = 1.0
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(config, fh)
        state = self.run_until(make_fetch(market(RISING, seed=35)), START + 2 * H1)
        buys = self.trades(HOLD)
        self.assertEqual(len(buys), 5)
        self.assertNotIn("SOL/INR", [r["pair"] for r in buys])
        self.assertEqual(buys[-1]["reason"], "among the 10 most traded, standing in for one it can't buy")
        for r in buys:
            self.assertTrue(850 < float(r["value"]) < 1100, r)
        self.assertEqual(len(state["bots"][HOLD]["positions"]), 5)

    def test_the_filter_holds_cash_while_btc_is_below_its_average(self):
        state = self.run_until(make_fetch(market(FALLING, seed=32)), START + 4 * DAY)
        self.assertEqual(self.trades(TREND), [])
        self.assertEqual(state["bots"][TREND]["cash"], 5000)
        self.assertEqual(len(self.trades(HOLD)), 5)

    def test_the_filter_sells_everything_when_btc_falls_below_its_average(self):
        state = self.run_until(make_fetch(market(TOPPING, seed=33)), START + 7 * DAY)
        buys = [r for r in self.trades(TREND) if r["side"] == "BUY"]
        sells = [r for r in self.trades(TREND) if r["side"] == "SELL"]
        self.assertEqual(len(buys), 5)
        self.assertEqual(len(sells), 5)
        self.assertEqual(set(r["reason"] for r in sells), {"BTC below its 30-day average"})
        self.assertEqual(len(set(r["time_ist"] for r in sells)), 1)
        self.assertEqual(state["bots"][TREND]["positions"], {})
        self.assertEqual(state["bots"][HOLD]["trades"], 0)
        self.assertEqual(len(state["bots"][HOLD]["positions"]), 5)

    def test_a_coin_that_stops_being_traded_is_swapped_out(self):
        m = market(RISING, seed=34)
        for row in m[("I-SOL_INR", "1h")]:
            row["v"] *= 100 if row["t"] < START - 12 * DAY else 0
        state = self.run_until(make_fetch(m), START + 7 * DAY)
        sells = [r for r in self.trades(HOLD) if r["side"] == "SELL"]
        self.assertEqual([(r["pair"], r["reason"]) for r in sells], [("SOL/INR", "no longer among the 10 most traded")])
        held = set(state["bots"][HOLD]["positions"])
        self.assertEqual(len(held), 5)
        self.assertEqual(held & set(MAJORS), set(MAJORS) - {"I-SOL_INR"})


if __name__ == "__main__":
    unittest.main()
