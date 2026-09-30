import csv
import http.client
import json
import os
import smtplib
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import coindcx, desk, liquid, report, research, swarm
from .accounts import FuturesAccount, SpotAccount
from .bots import BTC, FIXED_BOTS, Bot
from .github import GitHub
from .indicators import Series
from .learner import SelfLearner
from .llm import Gemini
from .mailer import Mailer

ALL_BOTS = FIXED_BOTS + (SelfLearner,)
STATE_VERSION = 4
# Versions that only add bookkeeping: the replay changes no bot, so nobody is told about it.
QUIET_UPGRADES = frozenset([4])
FIFTEEN_MIN_MS = 15 * 60 * 1000
HOUR_MS = 3600000
DAY_MS = 86400000
FINISH_GRACE_MS = 2 * HOUR_MS
STALE_AFTER_MS = 12 * HOUR_MS
FETCH_WORKERS = 6
WORKFLOW_FILE = "simulate.yml"
TRADE_FIELDS = ("time_ist", "bot", "side", "pair", "qty", "price", "value", "fee", "tds", "pnl", "tax", "reason")


class Context:
    def __init__(self, prices, series):
        self.prices = prices
        self.series = series
        self.t = 0

    def equity(self, acct):
        return acct.equity(self.prices)


def run(root, now_ms, start_ms=None, notify=True, fetch=coindcx.closed_candles, desk_llm=Gemini.from_env, gather=research.gather):
    config = _read_json(os.path.join(root, "config.json"))
    state_dir = os.path.join(root, "state")
    state_path = os.path.join(state_dir, "state.json")
    os.makedirs(state_dir, exist_ok=True)
    upgraded = False
    if not os.path.exists(state_path):
        state = _new_state(config, start_ms if start_ms is not None else now_ms - now_ms % FIFTEEN_MIN_MS)
    else:
        state = _read_json(state_path)
        if state.get("version", 1) < STATE_VERSION:
            state, upgraded = _upgrade(state, config), True
    reports = state["reports"]
    if state["finished"] and all(reports.get(k) for k in ("final_posted", "issue_closed", "workflow_disabled")):
        print("The simulation already finished. Nothing to do.")
        return state

    trades = []
    bots = _build_bots(state, config, trades)
    prices = state["last_prices"]
    processed = 0
    series = None
    if not state["finished"]:
        series = _fetch_all(state, sorted(set(sub for bot in bots for sub in bot.subscriptions)), fetch, now_ms)
        if upgraded:
            _check_replayable(state, series)
            # Only once prices are in: a skipped run still gets saved, and must not save half an upgrade.
            for name in ("equity.csv", "trades.csv"):
                if os.path.exists(os.path.join(state_dir, name)):
                    os.remove(os.path.join(state_dir, name))
        _seed_prices(prices, series, state["sim_start"])
        for pair, price in prices.items():
            state["start_prices"].setdefault(pair, price)
        _freeze_stale(state, bots, now_ms)
        processed, snapshots = _replay(state, bots, series, prices)
        _append_equity(state_dir, [bot.key for bot in bots], snapshots)
        _append_trades(state_dir, trades)
        state["runs"] += 1
        state["last_run"] = now_ms
        state["finished"] = now_ms >= state["sim_end"] + FINISH_GRACE_MS
        _write_json(state_path, state)

    board = report.leaderboard(bots, prices, state["last_event_t"] or now_ms, config)
    if series is not None:
        _safely(_desk_meeting, root, state, config, series, prices, board, bots, now_ms, desk_llm, gather)
        _write_json(state_path, state)
    try:
        report.update_readme(root, report.dashboard(state, board, config, prices, now_ms, bots))
        report.write_chart(root, state, board, config)
    except Exception:  # the dashboard is cosmetic; a rendering bug must not block saving or reporting
        traceback.print_exc()
    if notify:
        mailer = Mailer.from_env()
        _safely(_notify, state, board, config, prices, now_ms, len(bots))
        _safely(_deliver_mail, state, board, config, prices, now_ms, mailer)
        _safely(_switch_off, state, now_ms, mailer)
        _write_json(state_path, state)

    print("Processed %d candles and %d trades for %d bots. Run %d, %s." % (
        processed, len(trades), len(bots), state["runs"], report.ist(now_ms)))
    for r in board[:10]:
        print("  %-36s %10s  %7s  %s" % (r["title"], report.inr(r["value"]), report.pct(r["ret"]), r["now"]))
    return state


def _new_state(config, start_ms):
    return {
        "version": STATE_VERSION,
        "sim_start": start_ms,
        "sim_end": start_ms + config["duration_days"] * DAY_MS,
        "cursor": {},
        "last_prices": {},
        "start_prices": {},
        "last_event_t": None,
        "last_tick_t": None,
        "data_gaps": {},
        "desk": desk.fresh_book(),
        "bots": {},
        "reports": {"issue": None, "last_daily": None, "values": {}},
        "runs": 0,
        "last_run": None,
        "finished": False,
    }


def _upgrade(old, config):
    # Every bot, old and new, is replayed from the original start so they all share one timeline and one set of costs.
    state = _new_state(config, old["sim_start"])
    for key in ("reports", "runs", "last_run", "desk"):
        if key in old:
            state[key] = old[key]
    if any(v not in QUIET_UPGRADES for v in range(old.get("version", 1) + 1, STATE_VERSION + 1)):
        state["reports"]["announce"] = True
    return state


def _check_replayable(state, series):
    # CoinDCX returns only the latest 1,000 candles, about 10 days of 15-minute ones.
    probe = series.get((BTC, "15m"))
    if probe and probe.candles and probe.candles[0]["t"] > state["sim_start"]:
        raise RuntimeError("Can't upgrade the state: an upgrade replays every bot from %s, but CoinDCX now returns "
                           "15-minute prices only from %s. Keep the state version as it is." % (
                               report.ist(state["sim_start"]), report.ist(probe.candles[0]["t"])))


def _build_bots(state, config, trades):
    bots = []
    universe = config.get("universe", ())
    makers = ([(cls.key, cls.kind, cls) for cls in ALL_BOTS] + liquid.specs(universe) + swarm.specs(universe) +
              desk.specs(state, config))
    for key, kind, make in makers:
        account_cls = FuturesAccount if kind == "futures" else SpotAccount
        acct_state = state["bots"].setdefault(key, account_cls.fresh(config["capital_inr"]))

        def log(row, key=key):
            trades.append(dict(row, bot=key))

        bots.append(make(account_cls(acct_state, config["costs"], config["markets"], log)))
    return bots


def _fetch_all(state, subs, fetch, now_ms):
    # BTC goes first, alone: if CoinDCX is down, the run stops here instead of spending minutes retrying every coin.
    probe = (BTC, "15m") if (BTC, "15m") in subs else subs[0]
    series = {probe: Series(probe[0], probe[1], fetch(probe[0], probe[1], now_ms))}
    failed = []
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        jobs = [(sub, pool.submit(fetch, sub[0], sub[1], now_ms)) for sub in subs if sub != probe]
        for sub, job in jobs:
            try:
                series[sub] = Series(sub[0], sub[1], job.result())
            except coindcx.DataUnavailable as exc:
                failed.append(sub)
                print("Warning: skipping this coin for now: %s" % exc)
    if 2 * len(failed) > len(subs):
        raise coindcx.DataUnavailable("%d of %d price series could not be downloaded" % (len(failed), len(subs)))
    gaps = state.setdefault("data_gaps", {})
    for sub in subs:
        name = "%s|%s" % sub
        if sub in failed:
            gaps.setdefault(name, now_ms)
        else:
            gaps.pop(name, None)
    return series


def _freeze_stale(state, bots, now_ms):
    stale = set(name for name, since in state.get("data_gaps", {}).items() if now_ms - since >= STALE_AFTER_MS)
    for bot in bots:
        if bot.acct.active and bot.subscriptions and all("%s|%s" % sub in stale for sub in bot.subscriptions):
            bot.acct.s["status"] = "no data"
            bot.acct.s["error"] = "CoinDCX has sent no prices for %s since %s" % (
                ", ".join(sorted(set(report.symbol(p) for p, _ in bot.subscriptions))),
                report.ist(min(state["data_gaps"]["%s|%s" % sub] for sub in bot.subscriptions)))


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

    listeners = {}
    for bot in bots:
        for sub in bot.subscriptions:
            listeners.setdefault(sub, []).append(bot)
    ticking = [bot for bot in bots if type(bot).on_tick is not Bot.on_tick]
    ctx = Context(prices, series)
    snapshots = []
    last_tick = state.get("last_tick_t") or 0
    for n, (close_t, span, pair, interval, i) in enumerate(events):
        s = series[(pair, interval)]
        ctx.t = close_t
        prices[pair] = s.candles[i]["c"]
        for bot in listeners.get((pair, interval), ()):
            if bot.acct.active:
                _guard(bot, "on_candle", bot.on_candle, ctx, s, i)
        state["cursor"]["%s|%s" % (pair, interval)] = s.candles[i]["t"]
        state["last_event_t"] = max(state["last_event_t"] or 0, close_t)
        is_last = n + 1 == len(events)
        if not is_last and events[n + 1][0] == close_t:
            continue
        # A coin that was missing from earlier runs replays its backlog here; the clock itself never goes back.
        if close_t <= last_tick:
            continue
        last_tick = close_t
        for bot in ticking:
            if bot.acct.active:
                _guard(bot, "on_tick", bot.on_tick, ctx)
        for bot in bots:
            if bot.acct.active:
                _guard(bot, "mark", bot.acct.mark, prices, close_t)
        if is_last or close_t % HOUR_MS == 0:
            snapshots.append((close_t, [bot.value(prices, close_t) for bot in bots]))
    state["last_tick_t"] = last_tick or None
    return len(events), snapshots


def _append_equity(state_dir, keys, snapshots):
    path = os.path.join(state_dir, "equity.csv")
    header = ["t_ms", "time_ist"] + keys
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            current = next(csv.reader(fh), None)
        if current != header:
            with open(path, newline="", encoding="utf-8") as fh:
                old = list(csv.DictReader(fh))
            with open(path + ".tmp", "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=header, restval="", extrasaction="ignore")
                writer.writeheader()
                writer.writerows(old)
            os.replace(path + ".tmp", path)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(header)
        for t, values in snapshots:
            writer.writerow([t, report.ist(t, "%Y-%m-%d %H:%M")] + ["%.0f" % v for v in values])


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


def _desk_meeting(root, state, config, series, prices, board, bots, now_ms, make_llm, gather):
    if "desk" not in config or not desk.due(state, now_ms):
        return
    book = state["desk"]
    book["cooldowns"] = dict((model, until) for model, until in book["cooldowns"].items() if until > now_ms)
    llm = make_llm(book["cooldowns"], now_ms)
    book["waiting_for_key"] = llm is None
    if llm is not None:
        desk.hold_meeting(root, state, config, series, prices, board, bots, now_ms, llm, gather)


def _safely(step, *args):
    try:
        step(*args)
    except Exception:  # the save step only runs if this process succeeds, so a reporting bug must not crash it
        traceback.print_exc()


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
        if reports.get("announce") and not state["finished"]:
            body = report.upgrade_message(state, board, config, prices, now_ms)
            if github:
                github.comment(reports["issue"], body)
            else:
                print(body)
            reports["announce"] = False
            _queue_mail(reports, "upgrade", report.upgrade_subject(board, config), body, config)
        book = state.get("desk") or {}
        if book.get("announce") and not state["finished"]:
            body = report.desk_message(state, board, config, now_ms)
            if github:
                github.comment(reports["issue"], body)
            else:
                print(body)
            book["announce"] = False
            _queue_mail(reports, "desk", report.DESK_TITLE, body, config)
        if state["finished"]:
            if not reports.get("final_posted"):
                body = report.final_message(state, board, config, prices)
                if github:
                    github.comment(reports["issue"], body)
                else:
                    print(body)
                reports["final_posted"] = True
                _queue_mail(reports, "final", report.FINAL_TITLE, body, config)
            if not reports.get("issue_closed"):
                if github:
                    github.close_issue(reports["issue"], report.FINAL_TITLE)
                reports["issue_closed"] = True
        elif reports["last_daily"] != today and int(report.ist(now_ms, "%H")) >= config["report_hour_ist"]:
            body = report.daily_message(state, board, config, prices, now_ms, reports["values"])
            if github:
                github.comment(reports["issue"], body)
            else:
                print(body)
            reports["last_daily"] = today
            reports["values"] = dict((r["key"], r["value"]) for r in board)
            _queue_mail(reports, "daily", report.daily_subject(state, board, config, now_ms), body, config)
    except (OSError, ValueError, KeyError, http.client.HTTPException) as exc:
        print("Warning: could not update the report issue, will retry next run: %s" % exc)


def _queue_mail(reports, kind, subject, body, config):
    # Only the newest report of each kind is kept, so a late or broken mail setup never floods the inbox.
    outbox = [m for m in reports.get("outbox", []) if m["kind"] != kind]
    outbox.append({"kind": kind, "subject": subject, "body": body.replace("@%s " % config["notify_user"], "", 1)})
    reports["outbox"] = outbox


def _deliver_mail(state, board, config, prices, now_ms, mailer):
    reports = state["reports"]
    if not mailer or now_ms < reports.get("mail_retry_after", 0):
        return
    pending = list(reports.get("outbox", []))
    if not reports.get("mail_welcomed"):
        pending.insert(0, {"kind": "welcome", "subject": report.WELCOME_TITLE,
                           "body": report.welcome_message(state, board, config, prices, now_ms)})
    for item in pending:
        try:
            mailer.send(item["subject"], item["body"])
        except smtplib.SMTPAuthenticationError as exc:
            # Retrying a rejected password every half hour can get the Gmail account flagged.
            reports["mail_retry_after"] = now_ms + 6 * HOUR_MS
            print("Warning: Gmail rejected the app password, will try again in 6 hours: %s" % exc)
            return
        except (OSError, ValueError) as exc:
            print("Warning: could not send the email report, will retry next run: %s" % exc)
            return
        if item["kind"] == "welcome":
            reports["mail_welcomed"] = True
        else:
            reports["outbox"].remove(item)


def _switch_off(state, now_ms, mailer):
    reports = state["reports"]
    if not state["finished"] or reports.get("workflow_disabled"):
        return
    delivered = reports.get("final_posted") and reports.get("issue_closed") and not (mailer and reports.get("outbox"))
    if not delivered and now_ms < state["sim_end"] + DAY_MS:
        return
    github = GitHub.from_env()
    try:
        if github:
            github.disable_workflow(WORKFLOW_FILE)
        reports["workflow_disabled"] = True
    except (OSError, ValueError, http.client.HTTPException) as exc:
        print("Warning: could not switch off the workflow, will retry next run: %s" % exc)


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, sort_keys=True, separators=(",", ":"))
        fh.write("\n")
    os.replace(tmp, path)
