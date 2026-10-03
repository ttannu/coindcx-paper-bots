"""Predeclared, single-wallet screen of slow INR spot strategies.

Run with locally downloaded CoinDCX hourly candles, for example:

    python3 -m research.strategy_screen \
      --history-dir /path/to/coindcx/history \
      --output research/strategy_screen_results.json

The signals use completed candles. Orders are sent at the following hour's
open and pay the same INR spot costs as the paper engine. The next hour's
reported turnover is used only for a retrospective fill warning; it never
decides whether to trade. No historical order book is available, so these
are screens, not proven executable returns.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import statistics

from sim.accounts import SpotAccount
from sim.slow_signals import HOUR_MS, PAIRS, POLICIES, History, targets


DAY_MS = 24 * HOUR_MS
CAPITAL = 5_000.0
GOAL = 15_000.0  # The user's ₹10,000 profit target on ₹5,000 capital.
START = int(dt.datetime(2026, 1, 18, tzinfo=dt.timezone.utc).timestamp() * 1000)
WINDOW_DAYS = 15
WINDOW_COUNT = 17


def run_window(name, histories, config, start, slippage_multiplier=1.0, execution="next_open",
               window_days=None):
    end = start + (WINDOW_DAYS if window_days is None else window_days) * DAY_MS
    costs = config["costs"]
    markets = {pair: dict(config["markets"][pair],
                          slippage=config["markets"][pair]["slippage"] * slippage_multiplier)
               for pair in PAIRS}
    orders = []
    account = SpotAccount(SpotAccount.fresh(CAPITAL), costs, markets, orders.append)
    warnings = {"zero_volume": 0, "over_tenth": 0, "largest_participation": 0.0}
    audited = 0
    reached_goal = False

    def fill(desired, bars, price, t, field):
        for pair in sorted(set(account.s["positions"]) - set(desired)):
            account.sell(pair, bars[pair][field], t, name + " exit")
        for pair in sorted(set(desired) - set(account.s["positions"])):
            # Reserve accrued estimated tax; several virtual bots do not create more capital.
            equity = account.liquidation_value(price, t)
            budget = min(desired[pair] * max(0.0, equity),
                         max(0.0, account.cash - account.s["tax_due"]))
            account.buy(pair, budget, bars[pair][field], t, name + " entry")

    def audit(bars):
        nonlocal audited
        for order in orders[audited:]:
            # Retrospective audit only; future volume cannot veto a trade in the backtest.
            turnover = bars[order["pair"]]["v"] * bars[order["pair"]]["c"]
            if turnover == 0:
                warnings["zero_volume"] += 1
            else:
                share = order["value"] / turnover
                warnings["largest_participation"] = max(warnings["largest_participation"], share)
                if share > 0.1:
                    warnings["over_tenth"] += 1
        audited = len(orders)

    if execution == "next_open":
        price = {pair: histories[pair].closed(start, 1)[-1]["c"] for pair in PAIRS}
        for t in range(start, end, HOUR_MS):
            bars = {pair: histories[pair].opening(t) for pair in PAIRS}
            review = t == start or (POLICIES[name] is not None and (t - start) % (POLICIES[name] * HOUR_MS) == 0)
            if review:
                fill(targets(name, histories, t, account.s["positions"]), bars, price, t, "o")
            audit(bars)
            price = {pair: bars[pair]["c"] for pair in PAIRS}
            reached_goal |= account.mark(price, t + HOUR_MS) >= GOAL
    elif execution == "next_close":
        pending = None
        for t in range(start, end + HOUR_MS, HOUR_MS):
            if t > start:
                bars = {pair: histories[pair].closed(t, 1)[-1] for pair in PAIRS}
                price = {pair: bars[pair]["c"] for pair in PAIRS}
                if pending is not None:
                    fill(pending, bars, price, t, "c")
                    pending = None
                audit(bars)
                reached_goal |= account.mark(price, t) >= GOAL
            review = t < end and (t == start or
                                  (POLICIES[name] is not None and (t - start) % (POLICIES[name] * HOUR_MS) == 0))
            if review:
                pending = targets(name, histories, t, account.s["positions"])
    else:
        raise ValueError("unknown execution model: %s" % execution)
    return {
        "value": round(account.s["last_value"], 2),
        "return": round(account.s["last_value"] / CAPITAL - 1, 8),
        "orders": len(orders),
        "closed_trades": account.s["trades"],
        "max_drawdown": round(account.s["max_dd"], 8),
        "fees_inr": round(account.s["fees"], 2),
        "estimated_tax_inr": round(account.s["tax_due"], 2),
        "zero_volume_orders": warnings["zero_volume"],
        "over_tenth_orders": warnings["over_tenth"],
        "largest_participation": round(warnings["largest_participation"], 4),
        "goal_reached_at_any_mark": reached_goal,
    }


def _summary(windows, name, field="normal"):
    results = [w[field][name] for w in windows]
    returns = [r["return"] for r in results]
    holds = [w[field]["hold_btc"]["return"] for w in windows]
    return {
        "mean_return": round(statistics.mean(returns), 8),
        "median_return": round(statistics.median(returns), 8),
        "profitable_windows": sum(r > 0 for r in returns),
        "beat_btc_hold_windows": sum(r > b for r, b in zip(returns, holds)),
        "worst_window": min(returns),
        "worst_drawdown": max(r["max_drawdown"] for r in results),
        "orders": sum(r["orders"] for r in results),
        "zero_volume_orders": sum(r["zero_volume_orders"] for r in results),
        "over_tenth_orders": sum(r["over_tenth_orders"] for r in results),
        "goal_reached_at_end_windows": sum(r["value"] >= GOAL for r in results),
    }


def screen(history_dir, config):
    digest = hashlib.sha256()
    histories = {}
    for pair in PAIRS:
        path = os.path.join(history_dir, pair + "_1h.json")
        with open(path, "rb") as fh:
            raw = fh.read()
        digest.update(path.rsplit(os.sep, 1)[-1].encode("utf-8") + b"\0")
        digest.update(raw)
        histories[pair] = History(pair, json.loads(raw))
    last_end = START + WINDOW_COUNT * WINDOW_DAYS * DAY_MS
    for pair, h in histories.items():
        if h.times[0] > START - 31 * DAY_MS or h.times[-1] + HOUR_MS < last_end:
            raise ValueError("%s does not cover the warmup and all test windows" % pair)
    windows = []
    for k in range(WINDOW_COUNT):
        start = START + k * WINDOW_DAYS * DAY_MS
        result = {"start_utc": dt.datetime.fromtimestamp(start / 1000, dt.timezone.utc).isoformat(),
                  "normal": {}, "double_slippage": {}, "next_close": {}}
        for name in POLICIES:
            result["normal"][name] = run_window(name, histories, config, start)
            result["double_slippage"][name] = run_window(name, histories, config, start, slippage_multiplier=2.0)
            result["next_close"][name] = run_window(name, histories, config, start, execution="next_close")
        windows.append(result)
    return {
        "capital_inr": CAPITAL, "target_value_inr": GOAL, "data_sha256": digest.hexdigest(),
        "pairs": list(PAIRS), "window_days": WINDOW_DAYS, "window_count": WINDOW_COUNT,
        "start_utc": windows[0]["start_utc"],
        "end_utc": dt.datetime.fromtimestamp(last_end / 1000, dt.timezone.utc).isoformat(),
        "execution": "Primary: signal from completed 1h candles, trade at next hour open plus measured Sep 30 half-spread. "
                     "Sensitivity: trade at next hour close (same delay as forward paper bots), or double the spread. "
                     "CoinDCX fee/GST, TDS and estimated tax apply; mark at liquidation value. "
                     "Next-hour volume is an audit only.",
        "windows": windows,
        "summary": {name: {field: _summary(windows, name, field)
                            for field in ("normal", "double_slippage", "next_close")}
                    for name in POLICIES},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-dir", required=True, help="Local CoinDCX hourly JSON candle directory")
    parser.add_argument("--config", default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json"))
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "strategy_screen_results.json"))
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as fh:
        config = json.load(fh)
    result = screen(args.history_dir, config)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("17 windows of one ₹5,000 wallet; no strategy is guaranteed profitable.")
    for name in POLICIES:
        r = result["summary"][name]["normal"]
        s = result["summary"][name]["double_slippage"]
        c = result["summary"][name]["next_close"]
        print("%-15s mean %+6.1f%%, median %+6.1f%%, profit %2d/17, BTC beat %2d/17, "
              "worst %+6.1f%%, bad fills %d, doubled spread mean %+6.1f%%, next close mean %+6.1f%%" %
              (name, 100 * r["mean_return"], 100 * r["median_return"], r["profitable_windows"],
               r["beat_btc_hold_windows"], 100 * r["worst_window"],
               r["zero_volume_orders"] + r["over_tenth_orders"], 100 * s["mean_return"],
               100 * c["mean_return"]))


if __name__ == "__main__":
    main()
