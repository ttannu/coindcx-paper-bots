import csv
import datetime as dt
import json
import os
import tempfile
import unittest

from sim import engine, fill_audit
from sim.accounts import SpotAccount
from sim.bots import BTC, BuyAndHold
from sim.indicators import Series


ROOT = os.path.dirname(os.path.dirname(__file__))
CONFIG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))


class FillAuditTest(unittest.TestCase):
    def test_orders_are_bucketed_without_double_counting_futures(self):
        audit = fill_audit.fresh(0)
        order = {"side": "BUY", "pair": BTC, "t": 900000, "value": 500}
        for volume in (0, 100, 1000, 10000):
            fill_audit.record(audit, "btc.hold", "spot", order, {BTC: (900000, volume)})
        fill_audit.record(audit, "btc.hold", "spot", order, {})
        fill_audit.record(audit, "btc.trend_3x", "futures", order, {BTC: (900000, 0)})
        self.assertEqual(audit["spot"], {"within_tenth": 1, "over_tenth": 1, "over_full": 1,
                                          "zero": 1, "unmatched": 1})
        self.assertEqual(fill_audit.total(audit["bots"]["btc.hold"]), 5)
        self.assertNotIn("btc.trend_3x", audit["bots"])

    def test_backfill_is_idempotent_and_marks_missing_candles(self):
        t = int(dt.datetime(2026, 10, 1, 0, 15, tzinfo=fill_audit.IST).timestamp() * 1000)
        candle = {"t": t - fill_audit.FIFTEEN_MIN_MS, "o": 100, "h": 100, "l": 100, "c": 100, "v": 0}
        series = {(BTC, "15m"): Series(BTC, "15m", [candle])}
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "trades.csv"), "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=("time_ist", "bot", "side", "pair", "value"))
                writer.writeheader()
                writer.writerow({"time_ist": "2026-10-01 00:15", "bot": "btc.hold", "side": "BUY",
                                 "pair": "BTC/INR", "value": "500"})
                writer.writerow({"time_ist": "2026-09-30 23:45", "bot": "btc.hold", "side": "SELL",
                                 "pair": "BTC/INR", "value": "500"})
                writer.writerow({"time_ist": "2026-10-01 00:15", "bot": "btc.trend_3x", "side": "OPEN LONG",
                                 "pair": "BTC/INR", "value": "500"})
            audit = fill_audit.fresh(t)
            accounts = {"btc.hold": {"kind": "spot"}, "btc.trend_3x": {"kind": "futures"}}
            fill_audit.backfill(audit, root, series, accounts)
            fill_audit.backfill(audit, root, series, accounts)
        self.assertTrue(audit["initialized"])
        self.assertEqual(audit["spot"]["zero"], 1)
        self.assertEqual(audit["spot"]["unmatched"], 1)
        self.assertEqual(fill_audit.total(audit["spot"]), 2)

    def test_replay_audits_a_new_order_at_its_candle_close(self):
        account_state = SpotAccount.fresh(5000)
        audit = fill_audit.fresh(0)
        market = {}
        account = SpotAccount(account_state, CONFIG["costs"], CONFIG["markets"],
                              lambda row: fill_audit.record(audit, "hodl_btc", "spot", row, market))
        bot = BuyAndHold(account)
        candle = {"t": 0, "o": 8500000, "h": 8500000, "l": 8500000, "c": 8500000, "v": 0}
        state = {"cursor": {}, "sim_start": 0, "sim_end": 900000, "last_event_t": None, "last_tick_t": None}
        engine._replay(state, [bot], {(BTC, "15m"): Series(BTC, "15m", [candle])}, {BTC: 8500000}, market)
        self.assertEqual(audit["spot"]["zero"], 1)
        self.assertEqual(account_state["trades"], 0)  # Open purchase, no closed trade yet.


if __name__ == "__main__":
    unittest.main()
