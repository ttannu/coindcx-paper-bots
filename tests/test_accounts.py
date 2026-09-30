import json
import os
import unittest

from sim.accounts import FuturesAccount, SpotAccount, floor_step

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as fh:
    CONFIG = json.load(fh)
COSTS, MARKETS = CONFIG["costs"], CONFIG["markets"]
BTC = "I-BTC_INR"


def spot(capital=5000):
    trades = []
    return SpotAccount(SpotAccount.fresh(capital), COSTS, MARKETS, trades.append), trades


def futures(capital=5000):
    trades = []
    return FuturesAccount(FuturesAccount.fresh(capital), COSTS, MARKETS, trades.append), trades


class FloorStepTest(unittest.TestCase):
    def test_rounds_down_to_the_lot_size(self):
        self.assertEqual(floor_step(0.123456, 0.001), 0.123)
        self.assertEqual(floor_step(0.3, 0.1), 0.3)
        self.assertEqual(floor_step(0.00009, 0.0001), 0.0)


class SpotAccountTest(unittest.TestCase):
    def test_round_trip_at_the_same_price_loses_fees_and_slippage(self):
        acct, _ = spot()
        qty = acct.buy(BTC, 5000, 10000000, 0, "test")
        self.assertGreater(qty, 0)
        acct.sell(BTC, 10000000, 1, "test")
        loss = 5000 - acct.cash
        fee_rate = COSTS["spot_fee_rate"] * (1 + COSTS["gst_rate"])
        slippage = MARKETS[BTC].get("slippage", COSTS["slippage"])
        self.assertAlmostEqual(loss / 5000, 2 * fee_rate + 2 * slippage, delta=0.002)
        self.assertEqual(acct.s["tax_due"], 0)
        self.assertEqual(acct.s["losses"], 1)

    def test_losses_do_not_offset_tax_on_gains(self):
        acct, _ = spot(10000)
        acct.buy(BTC, 5000, 10000000, 0, "a")
        acct.sell(BTC, 11000000, 1, "a")
        tax_after_win = acct.s["tax_due"]
        self.assertGreater(tax_after_win, 0)
        acct.buy(BTC, 5000, 10000000, 2, "b")
        acct.sell(BTC, 9000000, 3, "b")
        self.assertEqual(acct.s["tax_due"], tax_after_win)

    def test_tds_starts_after_the_threshold(self):
        acct, trades = spot(60000)
        acct.buy(BTC, 40000, 10000000, 0, "a")
        acct.sell(BTC, 10000000, 1, "a")
        self.assertEqual(trades[-1]["tds"], 0)
        acct.buy(BTC, 30000, 10000000, 2, "b")
        acct.sell(BTC, 10000000, 3, "b")
        self.assertAlmostEqual(trades[-1]["tds"], trades[-1]["value"] * COSTS["tds_rate"])
        self.assertAlmostEqual(acct.s["tds_credit"], trades[-1]["tds"])

    def test_orders_below_the_minimum_are_skipped(self):
        acct, trades = spot(50)
        self.assertEqual(acct.buy(BTC, 50, 10000000, 0, "tiny"), 0.0)
        self.assertEqual(trades, [])
        self.assertEqual(acct.cash, 50)

    def test_liquidation_value_matches_an_actual_sale(self):
        acct, _ = spot()
        acct.buy(BTC, 5000, 10000000, 0, "a")
        expected = acct.liquidation_value({BTC: 10500000})
        acct.sell(BTC, 10500000, 1, "a")
        self.assertAlmostEqual(expected, acct.liquidation_value({}), places=6)


class FuturesAccountTest(unittest.TestCase):
    def test_ten_x_long_is_liquidated_by_a_small_drop(self):
        acct, trades = futures()
        self.assertTrue(acct.open(BTC, "long", 10, 10000000, 0, "test"))
        liq = acct.open_position["liq"]
        self.assertAlmostEqual(liq / 10000000, 0.9055, delta=0.001)
        self.assertFalse(acct.check_liquidation({"h": 10100000, "l": liq + 1}, 1))
        self.assertTrue(acct.check_liquidation({"h": 10100000, "l": liq - 1}, 2))
        self.assertEqual(acct.s["liquidations"], 1)
        acct.mark({BTC: 10000000}, 3)
        self.assertEqual(acct.s["status"], "busted")
        self.assertEqual(trades[-1]["side"], "LIQUIDATED")

    def test_short_profits_when_price_falls(self):
        acct, _ = futures()
        acct.open(BTC, "short", 10, 10000000, 0, "test")
        acct.close(9700000, 3600000, "test")
        self.assertGreater(acct.cash, 5000 * 1.2)
        self.assertGreater(acct.s["tax_due"], 0)


if __name__ == "__main__":
    unittest.main()
