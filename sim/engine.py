import csv
import http.client
import json
import os
import traceback

from . import coindcx, report
from .accounts import FuturesAccount, SpotAccount
from .bots import FIXED_BOTS
from .github import GitHub
from .indicators import Series
from .learner import SelfLearner

ALL_BOTS = FIXED_BOTS + (SelfLearner,)
FIFTEEN_MIN_MS = 15 * 60 * 1000
HOUR_MS = 3600000
DAY_MS = 86400000
FINISH_GRACE_MS = 2 * HOUR_MS
WORKFLOW_FILE = "simulate.yml"
TRADE_FIELDS = ("time_ist", "bot", "side", "pair", "qty", "price", "value", "fee", "tds", "pnl", "tax", "reason")


class Context:
    def __init__(self, prices, series):
        self.prices = prices
        self.series = series
        self.t = 0

    def equity(self, acct):
        return acct.equity(self.prices)


def run(root, now_ms, start_ms=None, notify=True, fetch=coindcx.closed_candles):
    config = _read_json(os.path.join(root, "config.json"))
    state_dir = os.path.join(root, "state")
    state_path = os.path.join(state_dir, "state.json")
    os.makedirs(state_dir, exist_ok=True)
    first_run = not os.path.exists(state_path)
    if first_run:
        state = _new_state(config, start_ms if start_ms is not None else now_ms - now_ms % FIFTEEN_MIN_MS)
    else:
        state = _read_json(state_path)
    reports = state["reports"]
    if state["finished"] and all(reports.get(k) for k in ("final_posted", "issue_closed", "workflow_disabled")):
        print("The simulation already finished. Nothing to do.")
        return state

    trades = []
    bots = _build_bots(state, config, trades)
    prices = state["last_prices"]
    processed = 0
    if not state["finished"]:
        series = {}
        for pair, interval in sorted(set(sub for bot in bots for sub in bot.subscriptions)):
            series[(pair, interval)] = Series(pair, interval, fetch(pair, interval, now_ms))
        _seed_prices(prices, series, state["sim_start"])
        if first_run:
            state["start_prices"] = dict(prices)
        processed, snapshots = _replay(state, bots, series, prices)
        _append_equity(state_dir, snapshots)
        _append_trades(state_dir, trades)
        state["runs"] += 1
        state["last_run"] = now_ms
        state["finished"] = now_ms >= state["sim_end"] + FINISH_GRACE_MS
        _write_json(state_path, state)

    board = report.leaderboard(bots, prices, state["last_event_t"] or now_ms, config)
    try:
        report.update_readme(root, report.dashboard(state, board, config, prices, now_ms, bots))
        report.write_chart(root, state, bots, config)
    except Exception:  # the dashboard is cosmetic; a rendering bug must not block saving or reporting
        traceback.print_exc()
    if notify:
        _notify(state, board, config, prices, now_ms, len(bots))
        _write_json(state_path, state)

    print("Processed %d candles and %d trades. Run %d, %s." % (processed, len(trades), state["runs"], report.ist(now_ms)))
    for r in board:
        print("  %-28s %10s  %7s  %s" % (r["title"], report.inr(r["value"]), report.pct(r["ret"]), r["now"]))
    return state


def _new_state(config, start_ms):
    return {
        "version": 1,
        "sim_start": start_ms,
        "sim_end": start_ms + config["duration_days"] * DAY_MS,
        "cursor": {},
        "last_prices": {},
        "start_prices": {},
        "last_event_t": None,
        "bots": {},
        "reports": {"issue": None, "last_daily": None, "values": {}},
        "runs": 0,
        "last_run": None,
        "finished": False,
    }


def _build_bots(state, config, trades):
    bots = []
    for cls in ALL_BOTS:
        account_cls = FuturesAccount if cls.kind == "futures" else SpotAccount
        acct_state = state["bots"].setdefault(cls.key, account_cls.fresh(config["capital_inr"]))

        def log(row, key=cls.key):
            trades.append(dict(row, bot=key))

        bots.append(cls(account_cls(acct_state, config["costs"], config["markets"], log)))
    return bots


def _seed_prices(prices, series, sim_start):
    for (pair, interval), s in sorted(series.items(), key=lambda item: item[0][1] != "15m"):
        if pair in prices or not s.candles:
            continue
        before = [c for c in s.candles if c["t"] < sim_start]
        prices[pair] = (before[-1] if before else s.candles[0])["c"]


def _guard(bot, stage, fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # one broken bot must not stop the others
        bot.acct.s["status"] = "error"
        bot.acct.s["error"] = "%s in %s: %s" % (type(exc).__name__, stage, exc)
        traceback.print_exc()


def _replay(state, bots, series, prices):
    events = []
    for (pair, interval), s in series.items():
        span = coindcx.INTERVAL_MS[interval]
        cursor = state["cursor"].get("%s|%s" % (pair, interval), -1)
        for i, c in enumerate(s.candles):
            close_t = c["t"] + span
            if c["t"] > cursor and c["t"] >= state["sim_start"] and close_t <= state["sim_end"]:
                events.append((close_t, span, pair, interval, i))
    events.sort()

    ctx = Context(prices, series)
    snapshots = []
    for n, (close_t, span, pair, interval, i) in enumerate(events):
        s = series[(pair, interval)]
        ctx.t = close_t
        prices[pair] = s.candles[i]["c"]
        for bot in bots:
            if bot.acct.active and (pair, interval) in bot.subscriptions:
                _guard(bot, "on_candle", bot.on_candle, ctx, s, i)
        state["cursor"]["%s|%s" % (pair, interval)] = s.candles[i]["t"]
        state["last_event_t"] = close_t
        is_last = n + 1 == len(events)
        if not is_last and events[n + 1][0] == close_t:
            continue
        for bot in bots:
            if bot.acct.active:
                _guard(bot, "on_tick", bot.on_tick, ctx)
            if bot.acct.active:
                _guard(bot, "mark", bot.acct.mark, prices, close_t)
        if is_last or close_t % HOUR_MS == 0:
            snapshots.append((close_t, [(bot.key, bot.value(prices, close_t)) for bot in bots]))
    return len(events), snapshots


def _append_equity(state_dir, snapshots):
    path = os.path.join(state_dir, "equity.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(["t_ms", "time_ist", "bot", "value"])
        for t, values in snapshots:
            for key, value in values:
                writer.writerow([t, report.ist(t, "%Y-%m-%d %H:%M"), key, "%.2f" % value])


def _append_trades(state_dir, trades):
    if not trades:
        return
    path = os.path.join(state_dir, "trades.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=TRADE_FIELDS)
        if new:
            writer.writeheader()
        for row in trades:
            writer.writerow({
                "time_ist": report.ist(row["t"], "%Y-%m-%d %H:%M"),
                "bot": row["bot"],
                "side": row["side"],
                "pair": report.symbol(row["pair"]) + "/INR",
                "qty": "%.8f" % row["qty"],
                "price": "%.2f" % row["price"],
                "value": "%.2f" % row["value"],
                "fee": "%.2f" % row["fee"],
                "tds": "%.2f" % row["tds"],
                "pnl": "" if row["pnl"] is None else "%.2f" % row["pnl"],
                "tax": "%.2f" % row["tax"],
                "reason": row["reason"],
            })


def _notify(state, board, config, prices, now_ms, bot_count):
    github = GitHub.from_env()
    reports = state["reports"]
    today = report.ist(now_ms, "%Y-%m-%d")
    try:
        if reports["issue"] is None:
            body = report.start_message(state, config, bot_count)
            reports["issue"] = github.create_issue(report.ISSUE_TITLE, body) if github else 0
            if not github:
                print(body)
            reports["last_daily"] = today
            reports["values"] = dict((r["key"], r["value"]) for r in board)
        if state["finished"]:
            if not reports.get("final_posted"):
                body = report.final_message(state, board, config, prices)
                if github:
                    github.comment(reports["issue"], body)
                else:
                    print(body)
                reports["final_posted"] = True
            if not reports.get("issue_closed"):
                if github:
                    github.close_issue(reports["issue"], report.FINAL_TITLE)
                reports["issue_closed"] = True
            if not reports.get("workflow_disabled"):
                if github:
                    github.disable_workflow(WORKFLOW_FILE)
                reports["workflow_disabled"] = True
        elif reports["last_daily"] != today and int(report.ist(now_ms, "%H")) >= config["report_hour_ist"]:
            body = report.daily_message(state, board, config, prices, now_ms, reports["values"])
            if github:
                github.comment(reports["issue"], body)
            else:
                print(body)
            reports["last_daily"] = today
            reports["values"] = dict((r["key"], r["value"]) for r in board)
    except (OSError, ValueError, KeyError, http.client.HTTPException) as exc:
        print("Warning: could not update the report issue, will retry next run: %s" % exc)


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
