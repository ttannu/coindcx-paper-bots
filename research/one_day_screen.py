"""Reproduce a one-day ₹5,000-to-₹15,000 feasibility screen, without orders.

Uses the predeclared rules in one_day_plan.md and local archived CoinDCX
hourly candles. The 47-coin scan is an oracle that knows the winning coin in
advance, not a tradable bot or a bound on leveraged strategies.
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import statistics

from sim.accounts import SpotAccount
from sim.slow_signals import HOUR_MS, PAIRS, POLICIES, History
from .strategy_screen import CAPITAL, DAY_MS, GOAL, START, run_window


DAY_COUNT = 255
END = START + DAY_COUNT * DAY_MS
MODELS = ("normal", "next_close")


def _utc(t):
    return dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).isoformat()


def _best(records, key, candidate):
    if records[key] is None or candidate["return"] > records[key]["return"]:
        records[key] = candidate


def _closes(pair, rows):
    """Allow gaps in an oracle pair but never infer a 24-hour move across one."""
    by_time = {}
    for row in rows:
        try:
            t, price, volume = int(row["t"]), float(row["c"]), float(row["v"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("%s has an invalid hourly candle" % pair) from exc
        if t % HOUR_MS or t in by_time or price <= 0 or volume < 0 or not all(
                math.isfinite(value) for value in (price, volume)):
            raise ValueError("%s has a duplicate or invalid hourly candle at %d" % (pair, t))
        by_time[t] = (price, volume)
    return by_time


def _spot_value(pair, entry, exit_price, start, end, config):
    account = SpotAccount(SpotAccount.fresh(CAPITAL), config["costs"],
                          {pair: config["markets"][pair]}, lambda row: None)
    if account.buy(pair, CAPITAL, entry, start, "hindsight entry"):
        account.sell(pair, exit_price, end, "hindsight exit")
    return account.liquidation_value({}, end)


def _oracle_days():
    return [{"start_utc": _utc(START + k * DAY_MS), "available_pairs": 0,
             "best_gross": None, "best_after_costs": None,
             "best_gross_with_volume": None, "best_after_costs_with_volume": None}
            for k in range(DAY_COUNT)]


def _scan_pair(pair, rows, config, days, rolling):
    by_time = _closes(pair, rows)
    for k, day in enumerate(days):
        start = START + k * DAY_MS
        entry = by_time.get(start - HOUR_MS)
        exit_bar = by_time.get(start + DAY_MS - HOUR_MS)
        if entry is None or exit_bar is None:
            continue
        day["available_pairs"] += 1
        gross = exit_bar[0] / entry[0] - 1
        after_costs = _spot_value(pair, entry[0], exit_bar[0], start, start + DAY_MS, config) / CAPITAL - 1
        gross_candidate = {"pair": pair, "return": round(gross, 8)}
        net_candidate = {"pair": pair, "return": round(after_costs, 8)}
        _best(day, "best_gross", gross_candidate)
        _best(day, "best_after_costs", net_candidate)
        if entry[1] > 0 and exit_bar[1] > 0:
            _best(day, "best_gross_with_volume", gross_candidate)
            _best(day, "best_after_costs_with_volume", net_candidate)

    for t, entry in by_time.items():
        if not START - HOUR_MS <= t <= END - DAY_MS - HOUR_MS:
            continue
        exit_bar = by_time.get(t + DAY_MS)
        if exit_bar is None:
            continue
        gross = exit_bar[0] / entry[0] - 1
        candidate = {"pair": pair, "start_utc": _utc(t + HOUR_MS), "return": round(gross, 8)}
        active = entry[1] > 0 and exit_bar[1] > 0
        improves_all = rolling["best_gross"] is None or candidate["return"] > rolling["best_gross"]["return"]
        improves_active = active and (rolling["best_gross_with_volume"] is None or
                                      candidate["return"] > rolling["best_gross_with_volume"]["return"])
        if improves_all or improves_active:
            # Evaluate only the biggest observed gross moves. This is a
            # post-screen cost diagnostic, never an input to a trading rule.
            candidate["modeled_spot_value_inr"] = round(_spot_value(
                pair, entry[0], exit_bar[0], t + HOUR_MS, t + HOUR_MS + DAY_MS, config), 2)
        rolling["observations"] += 1
        rolling["gross_200_percent_observations"] += gross >= 2
        _best(rolling, "best_gross", candidate)
        if active:
            rolling["positive_volume_observations"] += 1
            rolling["positive_volume_gross_200_percent_observations"] += gross >= 2
            _best(rolling, "best_gross_with_volume", candidate)


def _rule_summary(results, benchmark):
    returns = [result["return"] for result in results]
    return {
        "mean_return": round(statistics.mean(returns), 8),
        "median_return": round(statistics.median(returns), 8),
        "best_return": max(returns),
        "worst_return": min(returns),
        "profitable_days": sum(value > 0 for value in returns),
        "beat_btc_hold_days": sum(value > other["return"] for value, other in zip(returns, benchmark)),
        "target_at_end_days": sum(result["value"] >= GOAL for result in results),
        "target_at_any_hour_days": sum(result["goal_reached_at_any_mark"] for result in results),
        "orders": sum(result["orders"] for result in results),
        "zero_volume_orders": sum(result["zero_volume_orders"] for result in results),
        "over_tenth_orders": sum(result["over_tenth_orders"] for result in results),
    }


def screen(history_dir, config):
    digest = hashlib.sha256()
    histories = {}
    oracle_days = _oracle_days()
    rolling = {"observations": 0, "positive_volume_observations": 0,
               "gross_200_percent_observations": 0, "positive_volume_gross_200_percent_observations": 0,
               "best_gross": None, "best_gross_with_volume": None}
    for pair in config["universe"]:
        name = pair + "_1h.json"
        with open(os.path.join(history_dir, name), "rb") as fh:
            raw = fh.read()
        digest.update(name.encode("utf-8") + b"\0" + raw)
        rows = json.loads(raw)
        if pair in PAIRS:
            histories[pair] = History(pair, rows)
        _scan_pair(pair, rows, config, oracle_days, rolling)
    if set(histories) != set(PAIRS):
        raise ValueError("the four fixed strategy pairs must be in the 47-coin universe")
    for pair, history in histories.items():
        if history.times[0] > START - 31 * DAY_MS or history.times[-1] + HOUR_MS < END:
            raise ValueError("%s does not cover the warmup and the 255 daily windows" % pair)

    results = {name: {model: [] for model in MODELS} for name in POLICIES}
    days = []
    for k in range(DAY_COUNT):
        start = START + k * DAY_MS
        daily = {"start_utc": _utc(start), "rules": {}, "oracle": oracle_days[k]}
        for name in POLICIES:
            normal = run_window(name, histories, config, start, window_days=1)
            next_close = run_window(name, histories, config, start, execution="next_close", window_days=1)
            results[name]["normal"].append(normal)
            results[name]["next_close"].append(next_close)
            daily["rules"][name] = {
                "normal_return": normal["return"], "normal_target_at_any_hour": normal["goal_reached_at_any_mark"],
                "next_close_return": next_close["return"],
                "next_close_target_at_any_hour": next_close["goal_reached_at_any_mark"],
            }
        days.append(daily)

    def count_days(key, threshold):
        return sum(day[key] is not None and day[key]["return"] >= threshold for day in oracle_days)

    return {
        "capital_inr": CAPITAL, "target_value_inr": GOAL,
        "day_count": DAY_COUNT, "start_utc": _utc(START), "end_exclusive_utc": _utc(END),
        "universe_pairs": list(config["universe"]), "input_sha256": digest.hexdigest(),
        "rule_summary": {name: {model: _rule_summary(results[name][model], results["hold_btc"][model])
                                for model in MODELS} for name in POLICIES},
        "oracle_summary": {
            "utc_days_with_any_gross_200_percent": count_days("best_gross", 2),
            "utc_days_with_any_after_cost_200_percent": count_days("best_after_costs", 2),
            "utc_days_with_any_gross_200_percent_positive_volume": count_days("best_gross_with_volume", 2),
            "utc_days_with_any_after_cost_200_percent_positive_volume": count_days(
                "best_after_costs_with_volume", 2),
            "best_utc_day_gross": max((day["best_gross"] for day in oracle_days if day["best_gross"]),
                                      key=lambda result: result["return"], default=None),
            "best_utc_day_after_costs": max((day["best_after_costs"] for day in oracle_days
                                             if day["best_after_costs"]),
                                            key=lambda result: result["return"], default=None),
            "rolling_hourly_24h": rolling,
        },
        "days": days,
        "limitations": "Hindsight spot-coin selection cannot be traded as a signal. Prices are hourly candle closes, "
                       "not executable books; the 47 coins were selected at the end of the sample. "
                       "The cost and tax model may differ from the user's account. No futures strategy was validated.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-dir", required=True)
    parser.add_argument("--config", default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json"))
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "one_day_screen_results.json"))
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as fh:
        config = json.load(fh)
    result = screen(args.history_dir, config)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("%d independent 24-hour windows; ₹5,000 wallet; ₹15,000 target." % result["day_count"])
    for name in POLICIES:
        row = result["rule_summary"][name]["normal"]
        print("%-15s mean %+6.2f%%, profit %3d/%d, target %d/%d, best %+6.1f%%" % (
            name, 100 * row["mean_return"], row["profitable_days"], DAY_COUNT,
            row["target_at_any_hour_days"], DAY_COUNT, 100 * row["best_return"]))
    oracle = result["oracle_summary"]
    print("Hindsight best-coin spot holds: gross ≥200%% on %d/%d UTC days; after costs ≥200%% on %d/%d." % (
        oracle["utc_days_with_any_gross_200_percent"], DAY_COUNT,
        oracle["utc_days_with_any_after_cost_200_percent"], DAY_COUNT))
    print("Oracle coin choice, candle-close fills and historical data do not establish future executable profit.")


if __name__ == "__main__":
    main()
