import unittest

from research.arb_snapshot import parse_book, routes


class ArbitrageMathTest(unittest.TestCase):
    def test_numeric_quote_sorting_and_fee_bound(self):
        book = parse_book("I-BTC_INR", {
            "timestamp": 1234,
            "bids": {"99": "2", "101": "1"},
            "asks": {"103": "2", "102": "1"},
        })
        self.assertEqual(book["bid"]["price"], 101)
        self.assertEqual(book["ask"]["price"], 102)
        books = {
            "I-USDT_INR": {"bid": {"price": 100}, "ask": {"price": 101}},
            "I-BTC_INR": {"bid": {"price": 10050}, "ask": {"price": 10000}},
            "B-BTC_USDT": {"bid": {"price": 100}, "ask": {"price": 101}},
        }
        gross = routes("BTC", books, inr_fee=0, c2c_fee=0)
        charged = routes("BTC", books, inr_fee=0.0059, c2c_fee=0.002006)
        self.assertAlmostEqual(gross["inr_coin_usdt_inr"]["gross_upper_bound"], 0)
        self.assertAlmostEqual(gross["inr_coin_usdt_inr"]["net_upper_bound"], 0)
        for direction in gross:
            self.assertLess(charged[direction]["net_upper_bound"], gross[direction]["net_upper_bound"])


if __name__ == "__main__":
    unittest.main()
