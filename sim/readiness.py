"""Evidence screen for a small future spot pilot; this module never places orders."""

import argparse
import datetime as dt
import json
import os
import statistics

from . import fill_audit, swarm


DAY_MS = 24 * 3600000
MIN_HISTORY_WINDOWS = 12
MIN_PROFITABLE_WINDOWS = 9
MIN_FORWARD_DAYS = 15
MAX_HIGH_PARTICIPATION_SHARE = 0.05
BASELINE_PATH = os.path.join("research", "backtest_windows.json")


def _pct(value):
    return "%+.1f%%" % (100 * value)


def _median(values):
    values = list(values)
    return statistics.median(values) if values else None


def evaluate(state, config, baseline):
    """Return transparent per-family reasons; a pass is only a pilot screen."""
    accounts = state["bots"]
    windows = baseline["windows"]
    audit = state.get("fill_audit", {})
    by_bot = audit.get("bots", {})
    days = max(0, (state.get("last_event_t") or state["sim_start"]) - state["sim_start"]) / DAY_MS
    families = []
    for family in swarm.FAMILIES:
        if family.kind != "spot" or family.luck or family.key == "hold":
            continue  # Futures use spot-price proxies; holding and coin flips are controls.
        keys = [(pair[2:-4].lower(), pair) for pair in config["universe"]]
        live = [(accounts.get(coin + "." + family.key), accounts.get(coin + ".hold"), coin + "." + family.key)
                for coin, _ in keys]
        live = [(account, hold, key) for account, hold, key in live if account and hold]
        returns = [account["last_value"] / account["capital"] - 1 for account, _, _ in live]
        beats = sum(account["last_value"] > hold["last_value"] for account, hold, _ in live)
        drawdowns = [account.get("max_dd", 0.0) for account, _, _ in live]
        unhealthy = sum(account.get("status", "active") != "active" for account, _, _ in live)
        historical = [(w["returns"][family.key], w["returns"]["hold"]) for w in windows
                      if family.key in w["returns"] and "hold" in w["returns"]]
        win_windows = sum(value > 0 for value, _ in historical)
        beat_windows = sum(value > hold for value, hold in historical)
        mean_history = statistics.mean(value for value, _ in historical) if historical else None
        mean_advantage = statistics.mean(value - hold for value, hold in historical) if historical else None
        median_history = _median(value for value, _ in historical)
        warnings = dict((name, 0) for name in fill_audit.BUCKETS)
        for _, _, key in live:
            for name in warnings:
                warnings[name] += by_bot.get(key, {}).get(name, 0)
        audited = fill_audit.total(warnings)
        hard_warnings = warnings["zero"] + warnings["over_full"] + warnings["unmatched"]
        positive_candles = audited - warnings["zero"] - warnings["unmatched"]
        high_share = ((warnings["over_tenth"] + warnings["over_full"]) / positive_candles
                      if positive_candles else None)
        reasons = []
        if len(historical) < MIN_HISTORY_WINDOWS:
            reasons.append("fewer than %d historical windows" % MIN_HISTORY_WINDOWS)
        elif mean_history <= 0 or median_history <= 0 or win_windows < MIN_PROFITABLE_WINDOWS:
            reasons.append("historical returns did not persist after costs")
        if beat_windows < MIN_PROFITABLE_WINDOWS:
            reasons.append("did not beat holding in %d historical windows" % MIN_PROFITABLE_WINDOWS)
        if mean_advantage is None or mean_advantage <= 0:
            reasons.append("historical average did not beat holding")
        if days < MIN_FORWARD_DAYS:
            reasons.append("only %.1f of %d forward-paper days" % (days, MIN_FORWARD_DAYS))
        if len(live) * 10 < len(config["universe"]) * 9:
            reasons.append("forward-paper coin coverage is below 90%")
        if unhealthy:
            reasons.append("%d forward-paper accounts stopped or lost data" % unhealthy)
        if not returns or _median(returns) <= 0:
            reasons.append("forward-paper median is not profitable")
        if live and beats * 3 < len(live) * 2:
            reasons.append("forward paper did not beat holding on two-thirds of coins")
        if not audit.get("initialized") or audited == 0:
            reasons.append("spot fill audit is unavailable")
        elif hard_warnings or high_share is None or high_share > MAX_HIGH_PARTICIPATION_SHARE:
            reasons.append("quoted fills need order-book validation")
        families.append({"key": family.key, "label": family.label, "history_windows": len(historical),
                         "history_mean": mean_history, "history_median": median_history,
                         "history_mean_advantage": mean_advantage,
                         "history_profitable": win_windows, "history_beat_hold": beat_windows,
                         "paper_days": days, "paper_coins": len(live), "paper_median": _median(returns),
                         "paper_beat_hold": beats, "paper_worst_drawdown": max(drawdowns) if drawdowns else None,
                         "audited_orders": audited, "fill_warnings": hard_warnings,
                         "high_participation_share": high_share, "reasons": reasons, "pilot_screen_passed": not reasons})
    families.sort(key=lambda f: f["history_mean"] if f["history_mean"] is not None else float("-inf"), reverse=True)
    return {"paper_days": days, "families": families, "passing": [f["key"] for f in families if f["pilot_screen_passed"]]}


def render(result, baseline, state):
    last = state.get("last_event_t") or state["sim_start"]
    updated = dt.datetime.fromtimestamp(last / 1000, dt.timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    lines = [
        "# CoinDCX live-pilot evidence screen", "",
        "Paper prices through %s (%.1f of 15 forward-paper days). **%d spot strategy families pass this screen.** "
        "No live trading is wired to this repository." % (updated, result["paper_days"], len(result["passing"])), "",
        "The historical inputs are 12 non-overlapping 15-day CoinDCX candle replays from 3 Apr to 30 Sep 2026, "
        "after the simulation's fees, spread, and estimated tax. They came from the local backtest output identified "
        "by SHA-256 `%s`. Candle fills and tax assumptions are imperfect; these results cannot guarantee a future gain." %
        baseline["source_sha256"], "",
        "A family passes only if its historical mean and median are positive, at least 9 of 12 windows are profitable, "
        "at least 9 beat holding and the mean advantage is positive; its 15-day forward-paper median is profitable, "
        "covers at least 90% of the coins and beats holding on at least two-thirds of them; and its spot orders have no "
        "zero-volume, oversize, or unmatched fills and at most 5% use more than "
        "10% of a candle's reported volume. These are conservative pilot criteria, not a statistical proof of skill. "
        "All orders still need live order-book and reconciliation tests before any real-money use.", "",
        "| Spot family | Historical mean | Profitable windows | Beat holding, history | Forward median | Spot fill warnings | Above 10% volume | Pilot screen |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in result["families"]:
        lines.append("| %s | %s | %d/%d | %d/%d | %s | %d/%d | %s | %s |" % (
            item["label"], _pct(item["history_mean"]) if item["history_mean"] is not None else "–",
            item["history_profitable"], item["history_windows"], item["history_beat_hold"], item["history_windows"],
            _pct(item["paper_median"]) if item["paper_median"] is not None else "–", item["fill_warnings"],
            item["audited_orders"],
            "%.1f%%" % (100 * item["high_participation_share"]) if item["high_participation_share"] is not None else "–",
            "passed" if item["pilot_screen_passed"] else "blocked"))
    lines += ["", "Futures are excluded because their simulated P&L uses CoinDCX INR spot candles, and funding is a "
              "fixed assumption rather than CoinDCX futures data. "
              "The VIP-fee twins are excluded because a ₹5,000 account has not demonstrated the trading volume needed "
              "for that fee tier. Coin flips and buy-and-hold are controls, not candidate strategies.", "",
              "Before any live pilot, set a total capital limit and a daily loss limit, confirm the account's tax "
              "jurisdiction and fees, add an authenticated CoinDCX order client with idempotent order IDs and exchange "
              "reconciliation, and test it in dry-run mode. Passing this screen would permit review of a capped pilot; "
              "it would never authorize unlimited autonomous trading.", ""]
    return "\n".join(lines)


def write(root, state, config):
    baseline_path = os.path.join(root, BASELINE_PATH)
    if not os.path.exists(baseline_path):
        baseline_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), BASELINE_PATH)
    with open(baseline_path, encoding="utf-8") as fh:
        baseline = json.load(fh)
    result = evaluate(state, config, baseline)
    path = os.path.join(root, "docs", "live-readiness.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render(result, baseline, state))
    return result


def main():
    parser = argparse.ArgumentParser(description="Update the CoinDCX paper-to-live evidence screen")
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(__file__)))
    args = parser.parse_args()
    with open(os.path.join(args.root, "config.json"), encoding="utf-8") as fh:
        config = json.load(fh)
    with open(os.path.join(args.root, "state", "state.json"), encoding="utf-8") as fh:
        state = json.load(fh)
    result = write(args.root, state, config)
    print("%d of %d spot strategy families pass the live-pilot evidence screen." %
          (len(result["passing"]), len(result["families"])))


if __name__ == "__main__":
    main()
