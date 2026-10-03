import json
import os
import unittest

from research.one_day_screen import DAY_COUNT, _oracle_days, _scan_pair
from research.strategy_screen import DAY_MS, HOUR_MS, START, run_window
from sim.slow_signals import PAIRS, History


ROOT = os.path.dirname(os.path.dirname(__file__))


def config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as fh:
        return json.load(fh)


def rolling():
    return {"observations": 0, "positive_volume_observations": 0,
            "gross_200_percent_observations": 0, "positive_volume_gross_200_percent_observations": 0,
            "best_gross": None, "best_gross_with_volume": None}


class OneDayScreenTest(unittest.TestCase):
    def test_window_ends_before_a_second_day_pump(self):
        histories = {}
        for pair in PAIRS:
            rows = []
            for k in range(-721, 48):
                price = 500 if pair == PAIRS[0] and k >= 24 else 100
                rows.append({"t": START + k * HOUR_MS, "o": price, "h": price, "l": price,
                             "c": price, "v": 1000})
            histories[pair] = History(pair, rows)
        one_day = run_window("hold_btc", histories, config(), START, window_days=1)
        two_days = run_window("hold_btc", histories, config(), START, window_days=2)
        self.assertLess(one_day["value"], 5000)
        self.assertFalse(one_day["goal_reached_at_any_mark"])
        self.assertGreater(two_days["value"], 15000)

    def test_oracle_requires_exact_day_and_reports_after_cost_value(self):
        pair = PAIRS[0]
        rows = [{"t": START - HOUR_MS, "c": 100, "v": 1000},
                {"t": START + DAY_MS - HOUR_MS, "c": 400, "v": 1000}]
        days, observed = _oracle_days(), rolling()
        _scan_pair(pair, rows, config(), days, observed)
        self.assertEqual(len(days), DAY_COUNT)
        self.assertEqual(days[0]["available_pairs"], 1)
        self.assertEqual(days[0]["best_gross"]["return"], 3.0)
        self.assertGreater(days[0]["best_after_costs"]["return"], 2.0)
        self.assertEqual(observed["observations"], 1)
        self.assertGreater(observed["best_gross"]["modeled_spot_value_inr"], 15000)

    def test_oracle_flags_zero_volume_and_skips_missing_endpoint(self):
        pair = PAIRS[0]
        rows = [{"t": START - HOUR_MS, "c": 100, "v": 1000},
                {"t": START + DAY_MS - HOUR_MS, "c": 400, "v": 0}]
        days, observed = _oracle_days(), rolling()
        _scan_pair(pair, rows, config(), days, observed)
        self.assertIsNone(days[0]["best_gross_with_volume"])
        self.assertEqual(observed["positive_volume_observations"], 0)
        rows.pop()
        days, observed = _oracle_days(), rolling()
        _scan_pair(pair, rows, config(), days, observed)
        self.assertEqual(days[0]["available_pairs"], 0)
        self.assertEqual(observed["observations"], 0)


if __name__ == "__main__":
    unittest.main()
