import json
import os
import unittest
from unittest import mock

from research import strategy_screen
from sim import report, slow
from sim.accounts import SpotAccount
from sim.engine import Context
from sim.indicators import Series
from sim.slow_signals import HOUR_MS, PAIRS, History, targets


ROOT = os.path.dirname(os.path.dirname(__file__))
START = strategy_screen.START


def config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as fh:
        return json.load(fh)


def histories(hours_after=24, ramp=None, zero_at=None):
    ramp = ramp or {}
    rows = {}
    for pair in PAIRS:
        series = []
        for k in range(-721, hours_after):
            price = 100 * (1 + ramp.get(pair, 0) * (k + 721))
            if pair == PAIRS[0] and k >= 0:
                price = 200
            volume = 0 if (pair, k) == zero_at else 1000
            series.append({"t": START + k * HOUR_MS, "o": price, "h": price, "l": price,
                           "c": price, "v": volume})
        rows[pair] = series
    return {pair: History(pair, candles) for pair, candles in rows.items()}


class SignalTest(unittest.TestCase):
    def test_future_prices_do_not_change_a_signal(self):
        data = histories(ramp={PAIRS[0]: 0.0001, PAIRS[1]: 0.00005})
        before = targets("crossmom7", data, START, {})
        self.assertEqual(set(before), {PAIRS[0], PAIRS[1]})
        later = data[PAIRS[3]].rows[data[PAIRS[3]].index(START)]
        later.update(o=1_000_000, h=1_000_000, l=1_000_000, c=1_000_000)
        self.assertEqual(targets("crossmom7", data, START, {}), before)

    def test_a_gap_in_hourly_history_is_rejected(self):
        bars = histories(hours_after=1)[PAIRS[0]].rows
        with self.assertRaisesRegex(ValueError, "gap"):
            History(PAIRS[0], bars[:30] + bars[31:])


class ExecutionTest(unittest.TestCase):
    def test_backtest_buys_after_the_signal_and_uses_one_wallet(self):
        data = histories()
        with mock.patch.object(strategy_screen, "WINDOW_DAYS", 1):
            held = strategy_screen.run_window("hold_btc", data, config(), START)
            basket = strategy_screen.run_window("hold_equal", data, config(), START)
            next_close = strategy_screen.run_window("hold_btc", data, config(), START,
                                                    execution="next_close")
        # BTC jumps from 100 to 200 between the known signal and the next open.
        # An accidental same-candle fill at 100 would approximately double the wallet.
        self.assertLess(held["value"], 5000)
        self.assertLess(next_close["value"], 5000)
        self.assertEqual(held["orders"], 1)
        self.assertEqual(basket["orders"], 4)
        self.assertLess(basket["value"], 5000)

    def test_forward_bot_waits_one_hour_and_defers_zero_volume_fill(self):
        data = histories(hours_after=3, zero_at=(PAIRS[0], 0))
        series = {(pair, "1h"): Series(pair, "1h", h.rows) for pair, h in data.items()}
        prices = {pair: 100 for pair in PAIRS}
        ctx = Context(prices, series)
        orders = []
        cfg = config()
        account = SpotAccount(SpotAccount.fresh(5000), cfg["costs"], cfg["markets"], orders.append)
        bot = slow.SlowPortfolio(account, "btc_sma30")
        btc = series[(PAIRS[0], "1h")]

        ctx.t = START
        bot.on_candle(ctx, btc, 0)
        self.assertEqual(len(orders), 0)
        self.assertEqual(account.memo["pending"]["due"], START + HOUR_MS)
        ctx.t = START + HOUR_MS
        bot.on_candle(ctx, btc, 0)
        self.assertEqual(len(orders), 0)
        self.assertEqual(account.memo["liquidity_deferrals"], 1)
        ctx.t = START + 2 * HOUR_MS
        bot.on_candle(ctx, btc, 0)
        self.assertEqual(len(orders), 1)
        self.assertGreater(orders[0]["price"], 200)
        self.assertEqual(account.memo["joined"], START)

    def test_deferred_buy_rechecks_a_reversing_signal(self):
        data = histories(hours_after=3, zero_at=(PAIRS[0], 0))
        first_hour = data[PAIRS[0]].rows[data[PAIRS[0]].index(START)]
        first_hour.update(o=50, h=50, l=50, c=50)
        series = {(pair, "1h"): Series(pair, "1h", h.rows) for pair, h in data.items()}
        cfg = config()
        orders = []
        account = SpotAccount(SpotAccount.fresh(5000), cfg["costs"], cfg["markets"], orders.append)
        bot = slow.SlowPortfolio(account, "btc_sma30")
        ctx = Context({pair: 100 for pair in PAIRS}, series)
        btc = series[(PAIRS[0], "1h")]

        ctx.t = START
        bot.on_candle(ctx, btc, 0)
        self.assertEqual(account.memo["pending"]["target"], {PAIRS[0]: 0.95})
        ctx.t = START + HOUR_MS
        bot.on_candle(ctx, btc, 0)
        self.assertEqual(account.memo["pending"]["target"], {})
        ctx.t = START + 2 * HOUR_MS
        bot.on_candle(ctx, btc, 0)
        self.assertEqual(orders, [])

    def test_liquid_exit_is_not_blocked_by_illiquid_replacement(self):
        data = histories(hours_after=2, zero_at=(PAIRS[1], 0))
        series = {(pair, "1h"): Series(pair, "1h", h.rows) for pair, h in data.items()}
        cfg = config()
        orders = []
        account = SpotAccount(SpotAccount.fresh(5000), cfg["costs"], cfg["markets"], orders.append)
        account.buy(PAIRS[0], 2000, 100, START - HOUR_MS, "initial position")
        bot = slow.SlowPortfolio(account, "crossmom7")
        ctx = Context({pair: 100 for pair in PAIRS}, series)
        ctx.t = START + HOUR_MS

        active = bot._execute(ctx, bot._histories(ctx), {PAIRS[1]: 0.45})
        self.assertFalse(active)
        self.assertEqual([order["side"] for order in orders], ["BUY", "SELL"])
        self.assertEqual(account.s["positions"], {})

    def test_new_paper_portfolios_are_not_in_the_old_leaderboard(self):
        cfg = config()
        account = SpotAccount(SpotAccount.fresh(5000), cfg["costs"], cfg["markets"], lambda _: None)
        bot = slow.SlowPortfolio(account, "tsmom30")
        prices = {pair: 100 for pair in PAIRS}
        self.assertEqual(report.leaderboard([bot], prices, START, cfg), [])
        self.assertEqual([row["key"] for row in report.experimental_board([bot], prices, START, cfg)], [bot.key])

    def test_large_portfolio_loss_schedules_a_cash_exit(self):
        data = histories(hours_after=2)
        latest_btc = data[PAIRS[0]].rows[data[PAIRS[0]].index(START) - 1]
        latest_btc.update(o=70, h=70, l=70, c=70)
        series = {(pair, "1h"): Series(pair, "1h", h.rows) for pair, h in data.items()}
        cfg = config()
        account = SpotAccount(SpotAccount.fresh(5000), cfg["costs"], cfg["markets"], lambda _: None)
        account.buy(PAIRS[0], 5000, 100, START - 2 * HOUR_MS, "old position")
        account.mark({PAIRS[0]: 100}, START - HOUR_MS)
        bot = slow.SlowPortfolio(account, "btc_sma30")
        ctx = Context({pair: 100 for pair in PAIRS}, series)
        ctx.t = START
        bot.on_candle(ctx, series[(PAIRS[0], "1h")], 0)
        self.assertTrue(account.memo["halted"])
        self.assertEqual(account.memo["pending"], {"due": START + HOUR_MS, "target": {}})


if __name__ == "__main__":
    unittest.main()
