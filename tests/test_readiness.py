import unittest

from sim import fill_audit, readiness


DAY_MS = readiness.DAY_MS


def account(value):
    return {"capital": 5000, "last_value": value, "max_dd": 0.04, "kind": "spot"}


class ReadinessTest(unittest.TestCase):
    def setUp(self):
        self.config = {"capital_inr": 5000, "universe": ["I-BTC_INR", "I-ETH_INR"]}
        self.state = {"sim_start": 0, "last_event_t": 15 * DAY_MS, "bots": {
            "btc.hold": account(5000), "eth.hold": account(5000),
            "btc.grid_3pct": account(5500), "eth.grid_3pct": account(5500),
        }, "fill_audit": fill_audit.fresh(0)}
        self.state["fill_audit"]["initialized"] = True
        for bot in ("btc.grid_3pct", "eth.grid_3pct"):
            self.state["fill_audit"]["bots"][bot] = {"within_tenth": 10, "over_tenth": 0,
                                                       "over_full": 0, "zero": 0, "unmatched": 0}
        self.baseline = {"windows": [{"returns": {"grid_3pct": 0.05, "hold": 0.01}} for _ in range(12)]}

    def row(self):
        rows = readiness.evaluate(self.state, self.config, self.baseline)["families"]
        return next(row for row in rows if row["key"] == "grid_3pct")

    def test_only_backed_spot_family_can_pass(self):
        row = self.row()
        self.assertTrue(row["pilot_screen_passed"])
        self.assertEqual(row["history_profitable"], 12)
        self.assertEqual(row["paper_beat_hold"], 2)
        self.assertEqual(readiness.evaluate(self.state, self.config, self.baseline)["passing"], ["grid_3pct"])

    def test_paper_win_cannot_override_losing_history(self):
        self.baseline["windows"] = [{"returns": {"grid_3pct": -0.03, "hold": 0.01}} for _ in range(12)]
        row = self.row()
        self.assertFalse(row["pilot_screen_passed"])
        self.assertIn("historical returns did not persist after costs", row["reasons"])

    def test_bad_fill_or_short_forward_run_blocks_pilot(self):
        self.state["fill_audit"]["bots"]["btc.grid_3pct"]["zero"] = 1
        self.state["bots"]["btc.grid_3pct"]["status"] = "no data"
        self.state["last_event_t"] = 3 * DAY_MS
        row = self.row()
        self.assertFalse(row["pilot_screen_passed"])
        self.assertTrue(any("forward-paper days" in reason for reason in row["reasons"]))
        self.assertIn("quoted fills need order-book validation", row["reasons"])
        self.assertTrue(any("lost data" in reason for reason in row["reasons"]))


if __name__ == "__main__":
    unittest.main()
