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
WELCOME_TITLE = "Paper-trading bots: email reports are on"
UPGRADE_TITLE = "Paper-trading bots: now %s bots on %d coins"
LOWCOST_TITLE = "Paper-trading bots: %s low-cost twins added"
LOWCOST_BACKTEST = (
    "Replayed over the six months before the launch, these rules cut the losses but made nothing: per 15 days the 1.5% "
    "grid averaged -1.5% (against -10.3% at normal costs), the 3% grid -0.3% and the dip-buyers -1.8% to -2.9%, while "
    "holding at the same fee made +1.6%. Filling every limit order at the candle price, as the normal-cost bots fill, had "
    "shown +2% to +6%, profits from fills a real order can't get. Details are in docs/research.md.")
DESK_TITLE = "Paper-trading bots: the AI trading desk made its first decision"
MIN_SKILL_DAYS = 3
START_MARK = "<!-- DASHBOARD:START -->"
END_MARK = "<!-- DASHBOARD:END -->"
BENCHMARK = "hodl_btc"
MEDIAN = "median"
COLORS = ("#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2", "#db2777", "#65a30d", "#4b5563")


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


def _row(bot, prices, t, config):
    s = bot.acct.s
    value = bot.value(prices, t)
    desk = getattr(bot, "desk", False)
    return {
        "key": bot.key,
        "title": bot.title,
        "family": getattr(bot, "family", None),
        "coin": getattr(bot, "coin", None),
        "desk": desk,
        "added": getattr(bot, "added", False),
        "joined": s["memo"].get("joined") if desk else None,
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
        "money": _money(bot, prices, t),
    }


def leaderboard(bots, prices, t, config):
    rows = [_row(bot, prices, t, config) for bot in bots if not getattr(bot, "lowcost", False)]
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows


def lowcost_board(bots, prices, t, config):
    """The low-cost twins. They pay costs a ₹5,000 account can't get, so they are kept out of the leaderboard."""
    rows = [_row(bot, prices, t, config) for bot in bots if getattr(bot, "lowcost", False)]
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows


def _money(bot, prices, t):
    try:
        return bot.acct.breakdown(prices, t)
    except Exception:  # like Bot.value: a broken bot must not stop the report
        return None


def _holding(bot):
    s = bot.acct.s
    if s["status"] == "busted":
        return "busted"
    if s["status"] == "error":
        return "stopped by an error"
    if s["status"] == "no data":
        return "frozen: CoinDCX stopped sending prices"
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


def _median(values):
    values = sorted(values)
    if not values:
        return 0.0
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2.0


def _count(n):
    return "{:,}".format(n)


def summary_line(board, config):
    capital = config["capital_inr"]
    coins = len(set(r["coin"] for r in board if r["coin"]))
    hold = dict((r["coin"], r["value"]) for r in board if r["family"] and r["family"].key == "hold")
    rivals = [r for r in board if r["family"] and r["family"].key != "hold" and r["coin"] in hold]
    return ("%s bots on %d coins. %s are up and %s are down; %s are wiped out. The median bot is at %s. "
            "%s of %s bots are ahead of simply holding their coin." % (
                _count(len(board)), coins, _count(sum(1 for r in board if r["value"] > capital)),
                _count(sum(1 for r in board if r["value"] < capital)), _count(sum(1 for r in board if r["now"] == "busted")),
                inr(_median(r["value"] for r in board)), _count(sum(1 for r in rivals if r["value"] > hold[r["coin"]])),
                _count(len(rivals))))


def elapsed_days(state, t):
    return max(0, t - state["sim_start"]) / float(DAY_MS)


def _verdict(luck, benchmark, median, luck_median, beat, coins, days):
    # The profit condition matters on falling days, when a strategy that just sat in cash beats both yardsticks.
    if luck:
        return "luck control"
    if benchmark:
        return "benchmark"
    if days < MIN_SKILL_DAYS:
        return "too early"
    if median > 0 and luck_median is not None and median > luck_median and 2 * beat > coins:
        return "yes"
    return "not yet"


def report_card(board, days):
    hold = dict((r["coin"], r["value"]) for r in board if r["family"] and r["family"].key == "hold")
    groups = OrderedDict()
    for r in board:
        if r["family"]:
            groups.setdefault(r["family"].key, []).append(r)
    luck = [r["ret"] for r in board if r["family"] and r["family"].luck]
    luck_median = _median(luck) if luck else None
    cards = []
    for rows in groups.values():
        family = rows[0]["family"]
        median = _median(r["ret"] for r in rows)
        beat = sum(1 for r in rows if r["coin"] in hold and r["value"] > hold[r["coin"]])
        cards.append({
            "label": family.label[0].upper() + family.label[1:],
            "median": median,
            "best": rows[0],
            "worst": rows[-1],
            "profit": sum(1 for r in rows if r["ret"] > 0),
            "beat": None if family.key == "hold" else beat,
            "wiped": sum(1 for r in rows if r["now"] == "busted"),
            "coins": len(rows),
            "verdict": _verdict(family.luck, family.key == "hold", median, luck_median, beat, len(rows), days),
        })
    cards.sort(key=lambda c: c["median"], reverse=True)
    return cards


def _card_lines(cards):
    lines = [
        "| Strategy | Median return | Best coin | Worst coin | In profit | Beat holding | Wiped out | Skill shown? |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in cards:
        lines.append("| %s | %s | %s %s | %s %s | %d/%d | %s | %d | %s |" % (
            c["label"], pct(c["median"]), c["best"]["coin"], pct(c["best"]["ret"]), c["worst"]["coin"], pct(c["worst"]["ret"]),
            c["profit"], c["coins"], "–" if c["beat"] is None else "%d/%d" % (c["beat"], c["coins"]), c["wiped"], c["verdict"]))
    return lines


def luck_line(board):
    flips = [r for r in board if r["family"] and r["family"].luck]
    if not flips:
        return ""
    return ("**How much of this is luck?** The %s coin-flip bots trade at random. The luckiest is %s at %s, and their "
            "median is %s. With this many bots, some will look brilliant by chance alone, so a strategy counts as skilled "
            "only after %d days, and only if its median bot is in profit after costs, beats the coin flips, and beats "
            "holding on most coins." % (
                _count(len(flips)), flips[0]["title"], pct(flips[0]["ret"]), pct(_median(r["ret"] for r in flips)),
                MIN_SKILL_DAYS))


MONEY_PARTS = ("moves", "spread", "fees", "tax", "funding", "net")


def _money_row(label, splits, capital, strategy):
    row = dict((k, sum(s[k] for s in splits) / (capital * len(splits))) for k in MONEY_PARTS)
    row.update(label=label, bots=len(splits), strategy=strategy)
    return row


def money_table(board, capital):
    """Average per bot, as a share of the starting money, of what price moves made and what each cost took."""
    groups = OrderedDict()
    for r in board:
        if r["money"] is None:
            continue
        if r["family"]:
            label = r["family"].label[0].upper() + r["family"].label[1:]
        else:
            label = "AI desk" if r["desk"] else "Added on 1 Oct" if r.get("added") else "Original bots"
        groups.setdefault(label, (bool(r["family"]), []))[1].append(r["money"])
    rows = sorted((_money_row(label, splits, capital, strategy) for label, (strategy, splits) in groups.items()),
                  key=lambda row: row["net"], reverse=True)
    splits = [r["money"] for r in board if r["money"] is not None]
    return rows, _money_row("All bots", splits, capital, False) if splits else None


def money_line(board, capital):
    rows, total = money_table(board, capital)
    if not total:
        return ""
    strategies = [row for row in rows if row["strategy"]]
    return ("**Where the money went.** On average a bot's trades have made %s of its starting money from price moves, "
            "before any costs. The spread took %s, fees and GST %s, tax %s and futures funding %s, which leaves %s. %d of "
            "the %d strategies are ahead before costs, and %d after them. Tax is charged on every profitable sale and "
            "losses can't be set off against it, so a strategy can pay tax while losing money." % (
                pct(total["moves"]), pct(total["spread"], False), pct(total["fees"], False), pct(total["tax"], False),
                pct(total["funding"], False), pct(total["net"]), sum(1 for row in strategies if row["moves"] > 0),
                len(strategies), sum(1 for row in strategies if row["net"] > 0)))


def _money_lines(board, capital):
    rows, total = money_table(board, capital)
    if not total:
        return []
    lines = [
        "| Strategy | Bots | Price moves | Spread | Fees and GST | Tax | Funding | Result |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows + [total]:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            "**All bots**" if row is total else row["label"], _count(row["bots"]), pct(row["moves"]),
            pct(-row["spread"]), pct(-row["fees"]), pct(-row["tax"]), pct(-row["funding"]) if row["funding"] else "–",
            pct(row["net"])))
    return lines


def _rate(fraction):
    return "%g%%" % round(fraction * 100, 4)


def _cost_share(rows, capital):
    splits = [r["money"] for r in rows if r["money"] is not None]
    return sum(m["spread"] + m["fees"] for m in splits) / (capital * len(splits)) if splits else None


def lowcost_card(board, low, config, days):
    """Each low-cost strategy next to the same strategy at normal costs, on the same coins. Skill and "beat holding" are
    judged against the low-cost coin flip and buy & hold, so every comparison is at the same costs."""
    capital = config["capital_inr"]
    normal = {}
    for r in board:
        if r["family"]:
            normal.setdefault(r["family"].key, []).append(r)
    twins = OrderedDict()
    for r in low:
        twins.setdefault(r["family"].key, []).append(r)
    hold = dict((r["coin"], r["value"]) for r in low if r["family"].base.key == "hold")
    luck = [r["ret"] for r in low if r["family"].luck]
    luck_median = _median(luck) if luck else None
    fee_rate = config["low_cost"]["spot_fee_rate"] * (1 + config["costs"]["gst_rate"])
    cards = []
    for rows in twins.values():
        family = rows[0]["family"]
        base = family.base
        originals = normal.get(base.key, [])
        median = _median(r["ret"] for r in rows)
        beat = sum(1 for r in rows if r["coin"] in hold and r["value"] > hold[r["coin"]])
        cards.append({
            "label": base.label[0].upper() + base.label[1:],
            "name": base.label,
            "normal": _median(r["ret"] for r in originals) if originals else None,
            "median": median,
            "costs_normal": _cost_share(originals, capital),
            "costs_low": _cost_share(rows, capital),
            "profit": sum(1 for r in rows if r["ret"] > 0),
            "beat": None if base.key == "hold" else beat,
            "coins": len(rows),
            "volume": sum(r["fees"] for r in rows) / fee_rate / len(rows),
            "verdict": _verdict(family.luck, base.key == "hold", median, luck_median, beat, len(rows), days),
        })
    cards.sort(key=lambda c: c["median"], reverse=True)
    return cards


def lowcost_lines(state, board, low, config, t):
    days = elapsed_days(state, t)
    cards = lowcost_card(board, low, config, days) if low else []
    if not cards:
        return []
    tier = config["low_cost"]
    lines = [
        "**Low-cost test.** Since 1 Oct the strategies that had an edge before costs in the backtests also run with "
        "CoinDCX's %s fee (%s instead of %s, plus GST). The grids and dip-buyers place limit orders, which pay no spread "
        "but fill at exactly their price and only once the price trades through it; stops and the other exits are market "
        "orders and still pay it. Tax is unchanged, so the gap to the same strategy at normal costs is what fees and spread "
        "took. These %s bots are judged against a buy & hold and a coin flip at the same low cost, and are left out of the "
        "rankings above." % (tier["tier"], _rate(tier["spot_fee_rate"]), _rate(config["costs"]["spot_fee_rate"]),
                             _count(len(low))),
        "",
        "| Strategy | Median, normal costs | Median, low cost | Fees and spread | In profit | Beat holding | Skill shown? |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in cards:
        costs = "–"
        if c["costs_normal"] is not None and c["costs_low"] is not None:
            costs = "%s → %s" % (pct(-c["costs_normal"]), pct(-c["costs_low"]))
        lines.append("| %s | %s | %s | %s | %d/%d | %s | %s |" % (
            c["label"], "–" if c["normal"] is None else pct(c["normal"]), pct(c["median"]), costs, c["profit"], c["coins"],
            "–" if c["beat"] is None else "%d/%d" % (c["beat"], c["coins"]), c["verdict"]))
    if days >= 0.5:
        busiest = max(cards, key=lambda c: c["volume"])
        pace = busiest["volume"] * 30 / days
        lines += ["", "%s needs %s of trading in 30 days. The busiest of these strategies, %s, has traded %s per bot in "
                  "%.1f days, a pace of %s a month%s." % (
                      tier["tier"], inr(tier["monthly_volume_inr"]), busiest["name"], inr(busiest["volume"]), days,
                      inr(pace), ", so a %s account trading this way would not get there on its own" % inr(config["capital_inr"])
                      if pace < tier["monthly_volume_inr"] else "")]
    return lines


def _top_lines(board, config, n):
    lines = [
        "| # | Bot | Value if sold now, after costs and tax | Return | Progress to %s | Closed trades | Worst drop | Now |"
        % inr(config["goal_inr"]),
        "|---|---|---|---|---|---|---|---|",
    ]
    for rank, r in enumerate(board[:n], 1):
        lines.append("| %d | %s | %s | %s | %s | %d | %s | %s |" % (
            rank, r["title"], inr(r["value"]), pct(r["ret"]), pct(r["goal"], False), r["trades"],
            pct(r["max_dd"], False), r["now"]))
    return lines


def _original_lines(board, added=False):
    lines = [
        "| Bot | Value if sold now | Return | Rank | Closed trades | Now |",
        "|---|---|---|---|---|---|",
    ]
    for rank, r in enumerate(board, 1):
        if not r["family"] and not r["desk"] and r.get("added", False) == added:
            lines.append("| %s | %s | %s | %s of %s | %d | %s |" % (
                r["title"], inr(r["value"]), pct(r["ret"]), _count(rank), _count(len(board)), r["trades"], r["now"]))
    return lines


def _desk_plan(plan):
    spot = ", ".join(["%s %d%% (stop -%g%%%s)" % (
        symbol(e["pair"]), round(e["weight"] * 100), round(e["stop"] * 100, 1),
        ", target +%g%%" % round(e["take_profit"] * 100, 1) if e.get("take_profit") else "") for e in plan["spot"]] +
        ["%s kept as it is" % symbol(p) for p in plan.get("keep") or ()])
    f = plan["futures"]
    futures = "%s %s at %gx (stop %g%% away%s)" % (
        f["side"], symbol(f["pair"]), f["leverage"], round(f["stop"] * 100, 1),
        ", target %g%% away" % round(f["take_profit"] * 100, 1) if f.get("take_profit") else "") if f.get("pair") else "flat"
    return "Spot: %s. Futures: %s." % (spot or "all cash", futures)


def _desk_status(book, rows, config):
    joined = [r["joined"] for _, r in rows if r["joined"]]
    last, failure = book.get("last"), book.get("last_failure")
    parts = []
    if joined:
        parts.append("Both books started with %s on %s." % (inr(config["capital_inr"]), ist(min(joined))))
    if book.get("waiting_for_key") and not last:
        parts.append("The desk is waiting for a `GEMINI_API_KEY` repository secret. Until then both books hold cash.")
    if last:
        fg = last.get("fear_greed")
        parts.append("**Latest decision, %s** (market %s, news mood %s%s): %s %s" % (
            ist(last["t"]), last.get("regime") or "unclear", last.get("mood") or "unclear",
            ", Fear & Greed %d" % fg["value"] if fg else "", last.get("minutes") or "", _desk_plan(last["plan"])))
        if last.get("notes"):
            parts.append("Limits applied by the code: %s." % "; ".join(last["notes"]))
    if failure and (not last or failure["t"] > last["t"]):
        parts.append("The meeting at %s could not finish (%s). The books keep their positions and stops, and the desk "
                     "tries again after %s." % (ist(failure["t"]), failure["reason"], ist(book["next_meeting"])))
    if not last and not failure and not book.get("waiting_for_key"):
        parts.append("The first meeting happens at the next run.")
    return " ".join(parts)


def desk_lines(state, board, config, previous=None):
    book = state.get("desk")
    rows = [(rank, r) for rank, r in enumerate(board, 1) if r["desk"]]
    if not book or not rows:
        return []
    head = ["Book", "Value if sold now", "Return"] + (["Last 24 hours"] if previous is not None else []) + ["Rank", "Closed trades", "Now"]
    lines = [
        "**AI trading desk.** A team of AI agents (Google Gemini, free tier) meets every %d hours to run two books: three "
        "analysts (market, news, quant), a bull and a bear who debate, a trader, a three-person risk team, and a portfolio "
        "manager who makes the final call. The desk's limits are enforced in code, not left to the AI." % (
            config.get("desk", {}).get("every_hours", 2)),
        "",
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
    ]
    for rank, r in rows:
        cells = [r["title"], inr(r["value"]), pct(r["ret"])]
        if previous is not None:
            before = previous.get(r["key"])
            cells.append(pct(r["value"] / before - 1) if before and before > 0 else "–")
        cells += ["%s of %s" % (_count(rank), _count(len(board))), str(r["trades"]), r["now"]]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", _desk_status(book, rows, config), "",
              "Minutes of every meeting: https://github.com/%s/blob/main/docs/desk.md" % config["repository"]]
    return lines


def desk_message(state, board, config, now_ms):
    rule_bots = sum(1 for r in board if not r["desk"])
    lines = [
        "@%s an AI trading desk has joined the bots and made its first decision." % config["notify_user"],
        "",
        "- It runs two new paper books with %s each: a spot portfolio of up to 5 coins (at most 30%% in one) and a futures "
        "book with one position at a time, long or short, at up to 3x." % inr(config["capital_inr"]),
        "- Every %d hours a team of AI agents meets. Three analysts read the prices of all %d coins, the latest crypto news "
        "and market mood, and what the %s rule-based bots have learned; a bull and a bear debate; a trader proposes a plan; "
        "a risk team of three reviews it; and a portfolio manager decides. The design follows the open-source TradingAgents "
        "project." % (config.get("desk", {}).get("every_hours", 2), len(config.get("universe", ())), _count(rule_bots)),
        "- The code, not the AI, enforces the limits: position sizes, leverage, a stop loss on every position, and a floor at "
        "70% of the starting money. Orders fill at the next 15-minute close and pay the same fees and tax as every other bot.",
        "- It is still simulated money, and AI traders have no proven edge. The coin-flip bots and buy & hold are there to "
        "keep it honest.",
        "",
    ]
    lines += desk_lines(state, board, config)
    lines += ["", "Dashboard: https://github.com/%s" % config["repository"]]
    return "\n".join(lines)


def dashboard(state, board, config, prices, now_ms, bots=(), low=()):
    capital, goal = config["capital_inr"], config["goal_inr"]
    if state["finished"]:
        heading = "### Final results after %d days" % config["duration_days"]
        status = "The simulation has finished and the automation has switched itself off."
    else:
        heading = "### Live results: day %d of %d" % (day_number(state, config, now_ms), config["duration_days"])
        status = "Refreshed about every 30 minutes; each run catches up on everything it missed."
    lines = [
        heading,
        "",
        "Last updated %s. Runs from %s to %s. %s" % (ist(now_ms), ist(state["sim_start"]), ist(state["sim_end"]), status),
        "",
        "Each bot started with %s of simulated money. The goal is %s (%dx). %s" % (
            inr(capital), inr(goal), goal // capital, _btc_line(state, prices)),
        "",
        summary_line(board, config),
        "",
    ]
    desk = desk_lines(state, board, config)
    if desk:
        lines += desk + [""]
    lines += ["**Top 15 bots**", ""]
    lines += _top_lines(board, config, 15)
    lines += ["", "**The original bots**", ""]
    lines += _original_lines(board)
    if any(r.get("added") for r in board):
        lines += ["", "**Added on 1 Oct, after the [backtests](docs/research.md)**", ""]
        lines += _original_lines(board, added=True)
    cards = report_card(board, elapsed_days(state, state["last_event_t"] or state["sim_start"]))
    if cards:
        lines += [
            "",
            "**Strategy report card.** Each strategy runs separately on every coin. \"Beat holding\" counts the coins where "
            "it is ahead of buying that coin and holding it.",
            "",
        ]
        lines += _card_lines(cards)
        lines += ["", luck_line(board)]
    money = _money_lines(board, capital)
    if money:
        lines += ["", money_line(board, capital) + " Average per bot, as a share of its starting money, counting the "
                  "costs of selling what is still held:", ""] + money
    cheap = lowcost_lines(state, board, low, config, state["last_event_t"] or now_ms)
    if cheap:
        lines += [""] + cheap
    lines += [
        "",
        "![Value of the top bots over time](docs/equity.svg)",
        "",
        "Costs so far across all bots: %s in fees and GST, %s of TDS held back (refundable when you file taxes), "
        "and %s of estimated tax." % (inr(sum(r["fees"] for r in board)), inr(sum(r["tds"] for r in board)),
                                       inr(sum(r["tax"] for r in board))),
    ]
    for bot in bots:
        ranked = bot.insights() if bot.key == "self_learning" else []
        if ranked:
            lines += [
                "",
                "**What the original self-learning bot sees.** Its best strategy variants over the last 3 days, after all costs:",
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


def write_chart(root, state, board, config):
    keys = [r["key"] for r in board[:5]]
    for key in [BENCHMARK] + [r["key"] for r in board if r["desk"]]:
        if key not in keys:
            keys.append(key)
    titles = dict((r["key"], r["title"]) for r in board)
    titles[MEDIAN] = "Median of all %s bots" % _count(len(board))
    series = OrderedDict((key, []) for key in keys + [MEDIAN])
    path = os.path.join(root, "state", "equity.csv")
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            columns = dict((name, n) for n, name in enumerate(next(reader, [])))
            ranked = [columns[r["key"]] for r in board if r["key"] in columns]
            for row in reader:
                t = int(row[0])
                for key in keys:
                    n = columns.get(key)
                    if n is not None and n < len(row) and row[n]:
                        series[key].append((t, float(row[n])))
                values = [float(row[n]) for n in ranked if n < len(row) and row[n]]
                if values:
                    series[MEDIAN].append((t, _median(values)))
    series = OrderedDict((key, points) for key, points in series.items() if key in titles)
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
        "- %s bots, each with %s of simulated money, trade %d CoinDCX INR coins on live prices. "
        "No real money and no API keys are involved." % (_count(bot_count), inr(config["capital_inr"]),
                                                          len(config.get("universe", ()))),
        "- Every strategy runs separately on every coin, next to coin-flip bots that trade at random, so skill can be "
        "told apart from luck. The self-learning bots re-score their strategy variants every hour and follow "
        "whichever is working after costs, or hold cash when none is.",
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


def _standings(board, config, top):
    lines = ["| # | Bot | Value if sold now | Since start | Now |", "|---|---|---|---|---|"]
    for rank, r in enumerate(board[:top], 1):
        lines.append("| %d | %s | %s | %s | %s |" % (rank, r["title"], inr(r["value"]), pct(r["ret"]), r["now"]))
    return lines


def welcome_message(state, board, config, prices, now_ms):
    lines = [
        "Email reports for your paper-trading bots are on.",
        "",
        "- %s bots, each with %s of simulated money, trade on live CoinDCX INR prices. "
        "No real money and no API keys are involved." % (_count(len(board)), inr(config["capital_inr"])),
        "- The simulation runs from %s to %s. Today is day %d of %d." % (
            ist(state["sim_start"]), ist(state["sim_end"]), day_number(state, config, now_ms), config["duration_days"]),
        "- You'll get one email a day, by the first run after %02d:00 IST, and a final one when the simulation ends. "
        "After that the automation switches itself off." % config["report_hour_ist"],
        "",
        "Top 10 at %s:" % ist(now_ms),
        "",
    ]
    lines += _standings(board, config, 10)
    lines += [
        "",
        summary_line(board, config),
        _btc_line(state, prices),
        "",
        "Dashboard: https://github.com/%s" % config["repository"],
    ]
    return "\n".join(lines)


def upgrade_subject(board, config, low=()):
    if low:
        return LOWCOST_TITLE % _count(len(low))
    return UPGRADE_TITLE % (_count(len(board)), len(set(r["coin"] for r in board if r["coin"])))


def upgrade_message(state, board, config, prices, now_ms, low=()):
    coins = len(set(r["coin"] for r in board if r["coin"]))
    lines = [
        "@%s the bots have been upgraded: there are now %s of them on %d volatile CoinDCX coins%s." % (
            config["notify_user"], _count(len(board)), coins, ", plus %s low-cost twins" % _count(len(low)) if low else ""),
        "",
    ]
    if low:
        tier = config["low_cost"]
        names = list(OrderedDict((r["family"].base.label, None) for r in low))
        lines += [
            "- %d strategies now also run with CoinDCX's %s fee (%s instead of %s): %s. The grids and dip-buyers use limit "
            "orders, which pay no spread but only fill once the price trades through them. Tax is unchanged, so the gap to "
            "the normal-cost bots shows what fees and spread take." % (
                len(names), tier["tier"], _rate(tier["spot_fee_rate"]), _rate(config["costs"]["spot_fee_rate"]),
                ", ".join(names)),
            "- %s needs %s of trading a month, about %d times a %s account, so this tests whether costs are what stands in "
            "the way, not a fee a small account would get." % (
                tier["tier"], inr(tier["monthly_volume_inr"]), tier["monthly_volume_inr"] // config["capital_inr"],
                inr(config["capital_inr"])),
            "- " + LOWCOST_BACKTEST,
        ]
    lines += [
        "- All bots were replayed from %s, so they share one timeline and the 15-day end date is unchanged." % ist(state["sim_start"]),
        "",
        "Top 10 at %s:" % ist(now_ms),
        "",
    ]
    lines += _standings(board, config, 10)
    lines += ["", summary_line(board, config)]
    cheap = lowcost_lines(state, board, low, config, state["last_event_t"] or now_ms)
    if cheap:
        lines += [""] + cheap
    lines += ["", "Dashboard: https://github.com/%s" % config["repository"]]
    return "\n".join(lines)


def daily_subject(state, board, config, now_ms):
    best = board[0]
    return "Paper-trading bots, day %d of %d: %s leads at %s" % (
        day_number(state, config, now_ms), config["duration_days"], best["title"], inr(best["value"]))


def daily_message(state, board, config, prices, now_ms, previous, low=()):
    lines = [
        "@%s **Day %d of %d**, %s" % (config["notify_user"], day_number(state, config, now_ms),
                                     config["duration_days"], ist(now_ms, "%d %b %Y")),
        "",
        summary_line(board, config),
        "",
        "**Top 10**",
        "",
        "| # | Bot | Value if sold now | Since start | Last 24 hours | Closed trades |",
        "|---|---|---|---|---|---|",
    ]

    def change(r):
        before = previous.get(r["key"])
        return pct(r["value"] / before - 1) if before and before > 0 else "–"

    for rank, r in enumerate(board[:10], 1):
        lines.append("| %d | %s | %s | %s | %s | %d |" % (rank, r["title"], inr(r["value"]), pct(r["ret"]), change(r), r["trades"]))
    desk = desk_lines(state, board, config, previous)
    if desk:
        lines += [""] + desk
    for added, heading in ((False, "**The original bots**"), (True, "**Added on 1 Oct, after the backtests**")):
        rows = [(rank, r) for rank, r in enumerate(board, 1)
                if not r["family"] and not r["desk"] and r.get("added", False) == added]
        if rows:
            lines += ["", heading, "", "| Bot | Value if sold now | Since start | Last 24 hours | Rank |", "|---|---|---|---|---|"]
            lines += ["| %s | %s | %s | %s | %s |" % (r["title"], inr(r["value"]), pct(r["ret"]), change(r), _count(rank))
                      for rank, r in rows]
    cards = report_card(board, elapsed_days(state, state["last_event_t"] or state["sim_start"]))
    if cards:
        lines += ["", "**Strategy report card**", ""] + _card_lines(cards) + ["", luck_line(board)]
    money = _money_lines(board, config["capital_inr"])
    if money:
        lines += ["", money_line(board, config["capital_inr"]), ""] + money
    cheap = lowcost_lines(state, board, low, config, state["last_event_t"] or now_ms)
    if cheap:
        lines += [""] + cheap
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


def final_message(state, board, config, prices, low=()):
    goal = config["goal_inr"]
    lines = [
        "@%s **Final results after %d days** (%s to %s)" % (
            config["notify_user"], config["duration_days"], ist(state["sim_start"]), ist(state["sim_end"])),
        "",
        summary_line(board, config),
        "",
        "**Top 20**",
        "",
        "| # | Bot | Final value | Return | Closed trades | Win rate | Worst drop | Fees + GST | TDS held | Est. tax |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rank, r in enumerate(board[:20], 1):
        lines.append("| %d | %s | %s | %s | %d | %s | %s | %s | %s | %s |" % (
            rank, r["title"], inr(r["value"]), pct(r["ret"]), r["trades"],
            "–" if r["win_rate"] is None else pct(r["win_rate"], False), pct(r["max_dd"], False),
            inr(r["fees"]), inr(r["tds"]), inr(r["tax"])))
    desk = desk_lines(state, board, config)
    if desk:
        lines += [""] + desk
    lines += ["", "**The original bots**", ""] + _original_lines(board)
    if any(r.get("added") for r in board):
        lines += ["", "**Added on 1 Oct, after the backtests**", ""] + _original_lines(board, added=True)
    cards = report_card(board, elapsed_days(state, state["last_event_t"] or state["sim_start"]))
    if cards:
        lines += ["", "**Strategy report card**", ""] + _card_lines(cards) + ["", luck_line(board)]
    money = _money_lines(board, config["capital_inr"])
    if money:
        lines += ["", money_line(board, config["capital_inr"]), ""] + money
    cheap = lowcost_lines(state, board, low, config, state["last_event_t"] or state["sim_end"])
    if cheap:
        lines += [""] + cheap
    reached = [r["title"] for r in board if r["value"] >= goal]
    best = board[0]
    lines.append("")
    if reached:
        lines.append("Reached the %s goal: %s." % (inr(goal), ", ".join(reached[:20]) + (" and %s more" % _count(len(reached) - 20)
                                                                                       if len(reached) > 20 else "")))
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
