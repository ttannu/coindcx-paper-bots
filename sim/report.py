import csv
import datetime as dt
import math
import os
from collections import OrderedDict
from xml.sax.saxutils import escape

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
DAY_MS = 86400000
BTC = "I-BTC_INR"
ISSUE_TITLE = "Paper-trading bots: daily reports"
FINAL_TITLE = "Paper-trading bots: final results"
START_MARK = "<!-- DASHBOARD:START -->"
END_MARK = "<!-- DASHBOARD:END -->"
COLORS = ("#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2", "#4b5563")


def inr(amount):
    sign = "-" if amount < 0 else ""
    digits = str(int(round(abs(amount))))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    return sign + "₹" + digits


def pct(fraction, signed=True):
    return ("%+.1f%%" if signed else "%.1f%%") % (fraction * 100)


def ist(ms, fmt="%d %b %Y, %H:%M IST"):
    return dt.datetime.fromtimestamp(ms / 1000.0, IST).strftime(fmt)


def symbol(pair):
    return pair.split("-")[1].split("_")[0]


def day_number(state, config, now_ms):
    elapsed = min(now_ms, state["sim_end"]) - state["sim_start"]
    return max(1, min(config["duration_days"], int(elapsed // DAY_MS) + 1))


def leaderboard(bots, prices, t, config):
    rows = []
    for bot in bots:
        s = bot.acct.s
        value = bot.value(prices, t)
        rows.append({
            "key": bot.key,
            "title": bot.title,
            "value": value,
            "ret": value / config["capital_inr"] - 1,
            "goal": value / config["goal_inr"],
            "trades": s["trades"],
            "win_rate": float(s["wins"]) / s["trades"] if s["trades"] else None,
            "max_dd": s["max_dd"],
            "now": _holding(bot),
            "fees": s["fees"],
            "tds": s.get("tds_credit", 0.0),
            "tax": s["tax_due"],
        })
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows


def _holding(bot):
    s = bot.acct.s
    if s["status"] == "busted":
        return "busted"
    if s["status"] == "error":
        return "stopped by an error"
    described = bot.describe()
    if described:
        return described
    if bot.acct.kind == "futures":
        pos = s["position"]
        return "%s %gx" % (pos["side"], pos["leverage"]) if pos else "flat"
    held = sorted(symbol(p) for p in s["positions"])
    return "holding " + ", ".join(held) if held else "cash"


def _btc_line(state, prices):
    start, now = state["start_prices"].get(BTC), prices.get(BTC)
    if not start or not now:
        return ""
    return "BTC/INR since the start: %s (%s to %s)." % (pct(now / start - 1), inr(start), inr(now))


def dashboard(state, board, config, prices, now_ms, bots=()):
    capital, goal = config["capital_inr"], config["goal_inr"]
    if state["finished"]:
        heading = "### Final results after %d days" % config["duration_days"]
        status = "The simulation has finished and the automation has switched itself off."
    else:
        heading = "### Live results: day %d of %d" % (day_number(state, config, now_ms), config["duration_days"])
        status = "GitHub is asked to refresh this every 30 minutes but often runs late; each run catches up on everything it missed."
    lines = [
        heading,
        "",
        "Last updated %s. Runs from %s to %s. %s" % (ist(now_ms), ist(state["sim_start"]), ist(state["sim_end"]), status),
        "",
        "Each bot started with %s of simulated money. The goal is %s (%dx). %s" % (
            inr(capital), inr(goal), goal // capital, _btc_line(state, prices)),
        "",
        "| # | Bot | Value if sold now, after costs and tax | Return | Progress to %s | Closed trades | Win rate | Worst drop | Now |" % inr(goal),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for rank, r in enumerate(board, 1):
        lines.append("| %d | %s | %s | %s | %s | %d | %s | %s | %s |" % (
            rank, r["title"], inr(r["value"]), pct(r["ret"]), pct(r["goal"], False), r["trades"],
            "–" if r["win_rate"] is None else pct(r["win_rate"], False), pct(r["max_dd"], False), r["now"]))
    lines += [
        "",
        "![Value of each bot over time](docs/equity.svg)",
        "",
        "Costs so far across all bots: %s in fees and GST, %s of TDS held back (refundable when you file taxes), "
        "and %s of estimated tax." % (inr(sum(r["fees"] for r in board)), inr(sum(r["tds"] for r in board)),
                                       inr(sum(r["tax"] for r in board))),
    ]
    for bot in bots:
        ranked = bot.insights() if hasattr(bot, "insights") else []
        if ranked:
            lines += [
                "",
                "**What the self-learning bot sees.** Its best strategy variants over the last 3 days, after all costs:",
                "",
                "| Variant | Last 3 days | Signal now |",
                "|---|---|---|",
            ]
            lines += ["| %s | %s | %s |" % (key, pct(score), signal) for key, score, signal in ranked]
    return "\n".join(lines)


def update_readme(root, block):
    path = os.path.join(root, "README.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    new_block = START_MARK + "\n" + block + "\n" + END_MARK
    start, end = text.find(START_MARK), text.find(END_MARK)
    if start == -1 or end == -1:
        text = text.rstrip() + "\n\n" + new_block + "\n"
    else:
        text = text[:start] + new_block + text[end + len(END_MARK):]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def write_chart(root, state, bots, config):
    series = OrderedDict((bot.key, []) for bot in bots)
    path = os.path.join(root, "state", "equity.csv")
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row["bot"] in series:
                    series[row["bot"]].append((int(row["t_ms"]), float(row["value"])))
    titles = dict((bot.key, bot.title) for bot in bots)
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    with open(os.path.join(root, "docs", "equity.svg"), "w", encoding="utf-8") as fh:
        fh.write(chart_svg(state, series, titles, config["capital_inr"], config["goal_inr"]))


TICK_STEPS = (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9)


def chart_svg(state, series, titles, capital, goal):
    width, height = 900, 440
    left, right, top, bottom = 76, 20, 24, 124
    plot_h = height - top - bottom
    x0, x1 = state["sim_start"], state["sim_end"]
    floor = capital * 0.1
    values = [v for points in series.values() for _, v in points]
    shown = [max(v, floor) for v in values] + [capital]
    lo, hi = min(shown) / 1.05, max(shown) * 1.05
    if hi / lo < 1.25:
        mid = math.sqrt(hi * lo)
        lo, hi = mid / 1.118, mid * 1.118
    log_lo, log_span = math.log(lo), math.log(hi / lo)

    def x_of(t):
        return left + (t - x0) / float(x1 - x0) * (width - left - right)

    def y_of(v):
        return top + (1 - (math.log(max(v, floor)) - log_lo) / log_span) * plot_h

    note = "Log scale: equal percentage moves take equal space."
    if any(v < floor for v in values):
        note += " Values below %s are drawn at %s." % (inr(floor), inr(floor))
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
           'font-family="Arial, Helvetica, sans-serif" font-size="12">' % (width, height, width, height),
           '<rect width="100%" height="100%" fill="#ffffff"/>',
           '<text x="%d" y="%d" text-anchor="end" fill="#9ca3af" font-size="11">%s</text>'
           % (width - right, top - 10, escape(note))]
    ticks = []
    for k in range(int(math.floor(math.log10(lo))), int(math.ceil(math.log10(hi))) + 1):
        for m in TICK_STEPS:
            v = m * 10 ** k
            if lo <= v <= hi and (not ticks or y_of(ticks[-1]) - y_of(v) >= 28):
                ticks.append(v)
    for v in ticks:
        y = y_of(v)
        out.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="#e5e7eb"/>' % (left, width - right, y, y))
        out.append('<text x="%d" y="%.1f" text-anchor="end" fill="#6b7280">%s</text>' % (left - 8, y + 4, escape(inr(v))))
    days = int(round((x1 - x0) / float(DAY_MS)))
    for d in range(0, days + 1, 3 if days > 10 else 1):
        x = x_of(x0 + d * DAY_MS)
        out.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="#f3f4f6"/>' % (x, x, top, height - bottom))
        out.append('<text x="%.1f" y="%d" text-anchor="middle" fill="#6b7280">Day %d</text>' % (x, height - bottom + 18, d))
    for level, label, color in ((capital, "start", "#9ca3af"), (goal, "goal", "#16a34a")):
        if lo <= level <= hi:
            y = y_of(level)
            out.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="%s" stroke-dasharray="5 4"/>'
                       % (left, width - right, y, y, color))
            out.append('<text x="%d" y="%.1f" text-anchor="end" fill="%s">%s %s</text>'
                       % (width - right - 4, y - 6, color, label, escape(inr(level))))
    for idx, (key, points) in enumerate(series.items()):
        color = COLORS[idx % len(COLORS)]
        if len(points) == 1:
            out.append('<circle cx="%.1f" cy="%.1f" r="3" fill="%s"/>' % (x_of(points[0][0]), y_of(points[0][1]), color))
        elif points:
            path = " ".join("%.1f,%.1f" % (x_of(t), y_of(v)) for t, v in points)
            out.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2"/>' % (path, color))
        lx = left + (idx % 3) * 275
        ly = height - bottom + 48 + (idx // 3) * 22
        latest = inr(points[-1][1]) if points else "–"
        out.append('<rect x="%d" y="%d" width="14" height="4" fill="%s"/>' % (lx, ly - 4, color))
        out.append('<text x="%d" y="%d" fill="#111827">%s <tspan fill="#6b7280">%s</tspan></text>'
                   % (lx + 20, ly, escape(titles[key]), escape(latest)))
    if not values:
        out.append('<text x="%d" y="%d" text-anchor="middle" fill="#6b7280">Waiting for the first closed candles</text>'
                   % (width // 2, top + plot_h // 2))
    out.append("</svg>")
    return "\n".join(out)


def start_message(state, config, bot_count):
    costs = config["costs"]
    return "\n".join([
        "@%s your paper-trading bots are running." % config["notify_user"],
        "",
        "- %d bots, each with %s of simulated money, trade on live CoinDCX INR prices. "
        "No real money and no API keys are involved." % (bot_count, inr(config["capital_inr"])),
        "- One of them is self-learning: every hour it re-scores its strategy variants on live prices and follows "
        "whichever is working after costs, or holds cash when none is.",
        "- They pay realistic costs: a %.1f%% fee plus %d%% GST on every spot trade, slippage, %d%% TDS once a bot's "
        "sales pass %s, and an estimated %.1f%% tax on each profitable sale, with no offset for losses." % (
            costs["spot_fee_rate"] * 100, round(costs["gst_rate"] * 100), round(costs["tds_rate"] * 100),
            inr(costs["tds_threshold_inr"]), costs["tax_rate"] * 100),
        "- The simulation runs from %s to %s. A report is posted here every day, by the first run after %02d:00 IST." % (
            ist(state["sim_start"]), ist(state["sim_end"]), config["report_hour_ist"]),
        "- After %d days the final results are posted here, this issue closes, and the automation switches itself off."
        % config["duration_days"],
        "",
        "Live dashboard: https://github.com/%s" % config["repository"],
    ])


def daily_message(state, board, config, prices, now_ms, previous):
    lines = [
        "@%s **Day %d of %d**, %s" % (config["notify_user"], day_number(state, config, now_ms),
                                     config["duration_days"], ist(now_ms, "%d %b %Y")),
        "",
        "| # | Bot | Value if sold now | Since start | Last 24 hours | Closed trades |",
        "|---|---|---|---|---|---|",
    ]
    for rank, r in enumerate(board, 1):
        before = previous.get(r["key"])
        change = pct(r["value"] / before - 1) if before and before > 0 else "–"
        lines.append("| %d | %s | %s | %s | %s | %d |" % (rank, r["title"], inr(r["value"]), pct(r["ret"]), change, r["trades"]))
    best = board[0]
    lines += [
        "",
        _btc_line(state, prices),
        "Best so far: **%s** at %s, which is %s of the %s goal." % (
            best["title"], inr(best["value"]), pct(best["goal"], False), inr(config["goal_inr"])),
        "",
        "Dashboard: https://github.com/%s" % config["repository"],
    ]
    return "\n".join(lines)


def final_message(state, board, config, prices):
    goal = config["goal_inr"]
    lines = [
        "@%s **Final results after %d days** (%s to %s)" % (
            config["notify_user"], config["duration_days"], ist(state["sim_start"]), ist(state["sim_end"])),
        "",
        "| # | Bot | Final value | Return | Closed trades | Win rate | Worst drop | Fees + GST | TDS held | Est. tax |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rank, r in enumerate(board, 1):
        lines.append("| %d | %s | %s | %s | %d | %s | %s | %s | %s | %s |" % (
            rank, r["title"], inr(r["value"]), pct(r["ret"]), r["trades"],
            "–" if r["win_rate"] is None else pct(r["win_rate"], False), pct(r["max_dd"], False),
            inr(r["fees"]), inr(r["tds"]), inr(r["tax"])))
    reached = [r["title"] for r in board if r["value"] >= goal]
    best = board[0]
    lines.append("")
    if reached:
        lines.append("Reached the %s goal: %s." % (inr(goal), ", ".join(reached)))
    else:
        lines.append("No bot reached the %s goal. The best finished at %s (%s)." % (inr(goal), inr(best["value"]), pct(best["ret"])))
    lines += [
        _btc_line(state, prices),
        "Everything above is simulated. No real money was used.",
        "",
        "The automation has switched itself off. To run another %d days, delete the `state` folder and "
        "re-enable the `simulate` workflow in the Actions tab." % config["duration_days"],
    ]
    return "\n".join(lines)
