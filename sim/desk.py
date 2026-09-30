"""The AI trading desk: a team of language-model agents that runs two paper books.

The structure follows TradingAgents (github.com/TauricResearch/TradingAgents): analysts report, a bull and a bear
debate, a trader proposes, a risk team reviews, and a portfolio manager decides. The code below, not the models,
enforces every limit, and the books only act on decisions that were recorded before the candle they trade on.
"""
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor

from . import report, research
from .accounts import floor_step
from .bots import BTC, HOUR_MS, Bot, coin
from .llm import KeyRejected, LLMError

SPOT_KEY = "ai_desk_spot"
FUTURES_KEY = "ai_desk_futures"
FIFTEEN_MIN_MS = 15 * 60 * 1000
MINUTE_MS = 60000
FLOOR = 0.7
REBALANCE_BAND = 0.05
MAX_POSITIONS = 5
MAX_WEIGHT = 0.30
MIN_WEIGHT = 0.05
MAX_INVESTED = 0.95
MAX_LEVERAGE = 3.0
# A quiet CoinDCX book shows stale last-trade prices: backtests on them find profits that no order could have taken.
MIN_VOLUME_LAKH = 5.0
MAX_IDLE = 0.25
SPOT_STOP = (0.02, 0.15, 0.08)
FUTURES_STOP = (0.01, 0.10, 0.05)
TAKE_PROFIT = (0.02, 1.0)
RECENT_TRADES = 10
LESSONS = 6
LOG_SIZE = 24
MINUTES_SHOWN = 12
MINUTES_FILE = "desk_minutes.jsonl"
ANALYSTS = ("market", "news", "quant")
RISK_TEAM = ("aggressive", "neutral", "conservative")
DEEP_ROLES = ("trader", "manager")
EXPECTED = {"market": ("regime", "longs"), "news": ("mood", "coins"), "quant": ("summary", "edges"), "bull": ("thesis", "longs"),
            "bear": ("rebuttal", "dangers"), "aggressive": ("verdict", "view"), "neutral": ("verdict", "view"),
            "conservative": ("verdict", "view")}
TITLES = {
    "market": "Market analyst", "news": "News analyst", "quant": "Quant analyst", "bull": "Bull researcher",
    "bear": "Bear researcher", "trader": "Trader", "aggressive": "Risk team, aggressive",
    "neutral": "Risk team, neutral", "conservative": "Risk team, conservative", "manager": "Portfolio manager",
}


def fresh_book():
    return {"decisions": [], "next_meeting": 0, "cooldowns": {}, "last": None, "last_failure": None, "log": [],
            "lessons": [], "calls": {}, "announce": False, "announced": False, "waiting_for_key": False}


def _pending(memo, book, t):
    # Decisions are replayed in order; if several are waiting, only the newest one is traded.
    decisions = book["decisions"]
    n = memo.get("applied", 0)
    latest = None
    while n < len(decisions) and decisions[n]["t"] < t:
        latest = decisions[n]
        n += 1
    memo["applied"] = n
    return latest


class DeskBook(Bot):
    desk = True

    def __init__(self, account, universe, book):
        Bot.__init__(self, account)
        self.book = book
        self.subscriptions = tuple((pair, "15m") for pair in universe)
        memo = account.memo
        memo.setdefault("applied", 0)
        memo.setdefault("stopped", False)
        memo.setdefault("recent", [])
        inner = account.log

        def log(row):
            inner(row)
            if row["pnl"] is not None:
                memo["recent"].append({"t": row["t"], "coin": coin(row["pair"]), "side": row["side"],
                                       "pnl": round(row["pnl"], 2), "reason": row["reason"][:80]})
                del memo["recent"][:-RECENT_TRADES]

        account.log = log

    def on_tick(self, ctx):
        memo = self.acct.memo
        memo.setdefault("joined", ctx.t)
        decision = _pending(memo, self.book, ctx.t)
        if memo["stopped"]:
            return
        if self.acct.liquidation_value(ctx.prices, ctx.t) <= FLOOR * self.acct.s["capital"]:
            self._exit_all(ctx, "capital floor reached, stopping for good")
            memo["stopped"] = True
            return
        if decision is not None:
            self._apply(ctx, decision)


class DeskSpot(DeskBook):
    key = SPOT_KEY
    title = "AI desk: spot portfolio"
    kind = "spot"
    rules = ("Long only. The AI desk sets a target portfolio of up to 5 coins (at most 30% each, the rest in cash) at each "
             "meeting. Orders fill at the next 15-minute close. Stops and take-profits are checked every 15 minutes. "
             "Changes smaller than 5% of the book are skipped to save fees. Stops can be tightened but never loosened. "
             "Below 70% of its starting money it sells everything and stops for good.")

    def on_candle(self, ctx, s, i):
        pos = self.acct.position(s.pair)
        if not pos:
            return
        c = s.candles[i]
        if pos.get("stop") and c["l"] <= pos["stop"]:
            self.acct.sell(s.pair, min(pos["stop"], c["o"]), ctx.t, "stop loss")
        elif pos.get("target") and c["h"] >= pos["target"]:
            self.acct.sell(s.pair, max(pos["target"], c["o"]), ctx.t, "take profit")

    def _exit_all(self, ctx, reason):
        for pair in sorted(self.acct.s["positions"]):
            self.acct.sell(pair, ctx.prices[pair], ctx.t, reason)

    def _apply(self, ctx, decision):
        acct = self.acct
        plan = dict((e["pair"], e) for e in decision["spot"] if e["pair"] in ctx.prices)
        keep = set(decision.get("keep") or ())
        equity = ctx.equity(acct)
        band = max(acct.costs["min_trade_inr"], REBALANCE_BAND * equity)
        for pair, pos in sorted(acct.s["positions"].items()):
            if pair in keep:
                continue
            price = ctx.prices[pair]
            want = plan.get(pair)
            if not want:
                acct.sell(pair, price, ctx.t, "desk: exit")
                continue
            excess = pos["qty"] * price - want["weight"] * equity
            qty = floor_step(excess / price, acct.markets[pair]["step"])
            if excess > band and qty > 0:
                acct.sell(pair, price, ctx.t, "desk: trim to %d%%" % round(want["weight"] * 100), qty=qty)
        for pair, want in sorted(plan.items(), key=lambda kv: (-kv[1]["weight"], kv[0])):
            price = ctx.prices[pair]
            pos = acct.position(pair)
            held = pos["qty"] * price if pos else 0.0
            if want["weight"] * equity - held > band:
                acct.buy(pair, want["weight"] * equity - held, price, ctx.t, "desk: buy to %d%%" % round(want["weight"] * 100))
            pos = acct.position(pair)
            if pos:
                stop = price * (1 - want["stop"])
                pos["stop"] = max(stop, pos.get("stop") or 0.0) if held else stop
                pos["target"] = price * (1 + want["take_profit"]) if want.get("take_profit") else None

    def describe(self):
        memo = self.acct.memo
        if memo.get("stopped"):
            return "cash, stopped at the capital floor"
        held = sorted(coin(p) for p in self.acct.s["positions"])
        if held:
            return "holding " + ", ".join(held)
        return "cash" if memo.get("applied") else "cash, waiting for the first AI meeting"


class DeskFutures(DeskBook):
    key = FUTURES_KEY
    title = "AI desk: futures, up to 3x"
    kind = "futures"
    rules = ("One futures position at a time, long or short, at 1x to 3x, or flat, as the AI desk decides at each meeting. "
             "Orders fill at the next 15-minute close. It keeps an open position when the new plan has the same coin and "
             "direction. Stops (at most 10% away) and take-profits are checked every 15 minutes, and stops can be "
             "tightened but never loosened. Below 70% of its starting money it closes out and stops for good.")

    def on_candle(self, ctx, s, i):
        pos = self.acct.open_position
        if not pos or pos["pair"] != s.pair:
            return
        c = s.candles[i]
        if self.acct.check_liquidation(c, ctx.t):
            return
        long = pos["side"] == "long"
        stop, target = pos.get("stop"), pos.get("target")
        if stop and (c["l"] <= stop if long else c["h"] >= stop):
            self.acct.close(min(stop, c["o"]) if long else max(stop, c["o"]), ctx.t, "stop loss")
        elif target and (c["h"] >= target if long else c["l"] <= target):
            self.acct.close(max(target, c["o"]) if long else min(target, c["o"]), ctx.t, "take profit")

    def _exit_all(self, ctx, reason):
        pos = self.acct.open_position
        if pos:
            self.acct.close(ctx.prices[pos["pair"]], ctx.t, reason)

    def _apply(self, ctx, decision):
        plan = decision["futures"]
        acct = self.acct
        want = (plan["pair"], plan["side"]) if plan["side"] != "flat" and plan.get("pair") in ctx.prices else None
        pos = acct.open_position
        if pos and (pos["pair"], pos["side"]) != want:
            acct.close(ctx.prices[pos["pair"]], ctx.t, "desk: switch to %s %s" % (want[1], coin(want[0])) if want else "desk: go flat")
            pos = None
        fresh = False
        if want and not pos:
            if not acct.open(want[0], want[1], plan["leverage"], ctx.prices[want[0]], ctx.t, "desk"):
                return
            pos, fresh = acct.open_position, True
        if not pos:
            return
        long = pos["side"] == "long"
        base = pos["entry"] if fresh else ctx.prices[pos["pair"]]
        stop = base * (1 - plan["stop"]) if long else base * (1 + plan["stop"])
        if not fresh and pos.get("stop"):
            stop = max(stop, pos["stop"]) if long else min(stop, pos["stop"])
        pos["stop"] = stop
        tp = plan.get("take_profit")
        pos["target"] = (base * (1 + tp) if long else base * (1 - tp)) if tp else None

    def describe(self):
        memo = self.acct.memo
        if memo.get("stopped"):
            return "flat, stopped at the capital floor"
        pos = self.acct.open_position
        if pos:
            return "%s %s at %gx" % (pos["side"], coin(pos["pair"]), pos["leverage"])
        return "flat" if memo.get("applied") else "flat, waiting for the first AI meeting"


BOOKS = (DeskSpot, DeskFutures)


def specs(state, config):
    book = state.setdefault("desk", fresh_book())
    universe = tuple(config.get("universe") or (BTC,))
    return [(cls.key, cls.kind, lambda account, cls=cls: cls(account, universe, book)) for cls in BOOKS]


def due(state, now_ms):
    book, t = state.get("desk"), state.get("last_tick_t")
    return bool(book and t and not state["finished"] and now_ms >= book.get("next_meeting", 0)
                and now_ms - t <= 2 * HOUR_MS and t < state["sim_end"] - HOUR_MS)


# ---- what the agents are shown -------------------------------------------------------------------------------------

def _price(x):
    if x is None:
        return "–"
    if x >= 100:
        return "₹{:,.0f}".format(x)
    if x >= 1:
        return "₹%.2f" % x
    return "₹%.6g" % x


def _p(x, digits=1):
    return "–" if x is None else ("%+." + str(digits) + "f") % (x * 100)


def _stdev(values):
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def market_rows(universe, series, prices, t, config, gaps):
    rows, tradable = [], {}
    for pair in universe:
        s15, s1h = series.get((pair, "15m")), series.get((pair, "1h"))
        if not s15 or not s1h or len(s15.candles) < 97 or len(s1h.candles) < 49 or pair not in prices:
            continue
        closes, hourly, price = s15.closes, s1h.closes, prices[pair]

        def change(n):
            return price / closes[-1 - n] - 1 if len(closes) > n else None

        returns = [math.log(b / a) for a, b in zip(hourly[-25:-1], hourly[-24:])]
        high = max(c["h"] for c in s1h.candles[-168:])
        market = config["markets"].get(pair, {})
        day = s15.candles[-96:]
        row = {
            "coin": coin(pair), "pair": pair, "price": price, "ch_1h": change(4), "ch_4h": change(16),
            "ch_24h": change(96), "ch_7d": change(672), "rsi": s1h.get("rsi", 14)[-1],
            "trend": "up" if s1h.get("ema", 12)[-1] > s1h.get("ema", 48)[-1] else "down",
            "vol_24h": _stdev(returns) * math.sqrt(24), "off_high_7d": price / high - 1,
            "spread": 2 * market.get("slippage", config["costs"]["slippage"]),
            "volume_lakh": sum(c["v"] * c["c"] for c in day) / 1e5,
            "idle": sum(1 for c in day if not c["v"]) / float(len(day)),
            "fresh": s15.candles[-1]["t"] + FIFTEEN_MIN_MS >= t - HOUR_MS and "%s|15m" % pair not in gaps,
        }
        row["liquid"] = row["volume_lakh"] >= MIN_VOLUME_LAKH and row["idle"] <= MAX_IDLE
        rows.append(row)
        if row["fresh"] and row["liquid"] and pair in config["markets"]:
            tradable[row["coin"]] = pair
    return rows, tradable


def swarm_rows(board):
    groups = {}
    for r in board:
        if r["family"] and r["coin"]:
            groups.setdefault(r["coin"], []).append(r)
    rows = []
    for name, group in sorted(groups.items()):
        hold = [r for r in group if r["family"].key == "hold"]
        skill = [r for r in group if not r["family"].luck and r["family"].key != "hold"]
        luck = [r["ret"] for r in group if r["family"].luck]
        if not hold or not skill:
            continue
        best = max(skill, key=lambda r: r["value"])
        rows.append({"coin": name, "hold": hold[0]["ret"], "best": best["family"].label, "best_ret": best["ret"],
                     "in_profit": sum(1 for r in skill if r["ret"] > 0), "beat_hold": sum(1 for r in skill if r["value"] > hold[0]["value"]),
                     "count": len(skill), "luck": report._median(luck) if luck else None})
    return rows


def _market_table(rows):
    lines = ["coin|price|ch_1h|ch_4h|ch_24h|ch_7d|rsi_1h|trend|vol_24h|off_high_7d|spread|volume_lakh|idle_pct|tradable"]
    for r in rows:
        lines.append("%s|%s|%s|%s|%s|%s|%s|%s|%.1f|%s|%.2f|%.1f|%.0f|%s" % (
            r["coin"], _price(r["price"]), _p(r["ch_1h"]), _p(r["ch_4h"]), _p(r["ch_24h"]), _p(r["ch_7d"]),
            "–" if r["rsi"] is None else "%.0f" % r["rsi"], r["trend"], r["vol_24h"] * 100, _p(r["off_high_7d"]),
            r["spread"] * 100, r["volume_lakh"], r["idle"] * 100,
            "no: stale" if not r["fresh"] else "no: thin" if not r["liquid"] else "yes"))
    return "\n".join(lines)


def _swarm_table(rows):
    lines = ["coin|hold|best strategy|best|in profit|beat holding|coin-flip median"]
    for r in rows:
        lines.append("%s|%s|%s|%s|%d/%d|%d/%d|%s" % (r["coin"], _p(r["hold"]), r["best"], _p(r["best_ret"]), r["in_profit"],
                                                     r["count"], r["beat_hold"], r["count"], _p(r["luck"])))
    return "\n".join(lines)


def _card_text(board, capital):
    cards = report.report_card(board)
    money = dict((row["label"], row) for row in report.money_table(board, capital)[0])
    lines = []
    for c in cards:
        m = money.get(c["label"])
        lines.append("%s: median %s%%, %s%s" % (c["label"], _p(c["median"]), c["verdict"], "; on average price moves "
                     "%s%% and costs %s%%" % (_p(m["moves"]), _p(m["net"] - m["moves"])) if m else ""))
    return "\n".join(lines)


def _derivatives_table(derivs):
    if not derivs:
        return "Futures positioning data could not be downloaded this time."
    lines = ["coin|funding_8h_pct|open_interest_usd_m|volume_24h_usd_m"]
    for name, d in sorted(derivs.items()):
        lines.append("%s|%+.4f|%.1f|%.1f" % (name, d["funding_8h_pct"], d["open_interest_usd_m"], d["volume_24h_usd_m"]))
    return "\n".join(lines)


def _books_text(spot, fut, prices, t):
    lines = []
    capital = spot.acct.s["capital"]
    value = spot.value(prices, t)
    lines.append("Spot book: worth %s (%s%% since it joined), %s in cash%s." % (
        report.inr(value), _p(value / capital - 1), report.inr(spot.acct.cash),
        "; it has stopped for good at the capital floor" if spot.acct.memo.get("stopped") else ""))
    for pair, pos in sorted(spot.acct.s["positions"].items()):
        price = prices[pair]
        entry = pos["cost"] / pos["qty"]
        worth = pos["qty"] * price
        lines.append("- %s: %s, %.0f%% of the book, bought at %s, now %s (%s%%), stop %s%s" % (
            coin(pair), report.inr(worth), 100 * worth / max(value, 1.0), _price(entry), _price(price),
            _p(price / entry - 1), _price(pos.get("stop")), ", take-profit %s" % _price(pos["target"]) if pos.get("target") else ""))
    value = fut.value(prices, t)
    pos = fut.acct.open_position
    if pos:
        price = prices[pos["pair"]]
        move = (price / pos["entry"] - 1) * (1 if pos["side"] == "long" else -1)
        lines.append("Futures book: worth %s (%s%% since it joined). %s %s at %gx: entry %s, now %s (%s%% before leverage), "
                     "stop %s, take-profit %s, liquidation %s." % (
                         report.inr(value), _p(value / capital - 1), pos["side"], coin(pos["pair"]), pos["leverage"],
                         _price(pos["entry"]), _price(price), _p(move), _price(pos.get("stop")), _price(pos.get("target")),
                         _price(pos["liq"])))
    else:
        lines.append("Futures book: worth %s (%s%% since it joined), flat%s." % (
            report.inr(value), _p(value / capital - 1),
            "; it has stopped for good at the capital floor" if fut.acct.memo.get("stopped") else ""))
    return "\n".join(lines)


def _recent_text(spot, fut):
    rows = sorted(spot.acct.memo.get("recent", []) + fut.acct.memo.get("recent", []), key=lambda r: r["t"])[-8:]
    if not rows:
        return "The desk has not closed any trades yet."
    return "\n".join("- %s: %s %s, %s after all costs (%s)" % (report.ist(r["t"], "%d %b %H:%M"), r["side"].lower(), r["coin"],
                                                                 report.inr(r["pnl"]), r["reason"]) for r in rows)


def _costs_text(bot, prices, t):
    m = bot.acct.breakdown(prices, t)
    return "price moves %s%s, spread %s, fees and GST %s, tax %s%s" % (
        "+" if m["moves"] >= 0 else "", report.inr(m["moves"]), report.inr(-m["spread"]), report.inr(-m["fees"]),
        report.inr(-m["tax"]), ", funding %s" % report.inr(-m["funding"]) if round(m["funding"]) else "")


def _since_text(book, spot, fut, prices, t):
    if not book["log"]:
        return "This is the desk's first meeting."
    last = book["log"][-1]
    return ("Since the last meeting (%s): spot book %s to %s, futures book %s to %s.\nWhere each book's result since it "
            "started came from, counting the costs of selling what it holds now: spot %s; futures %s." % (
                report.ist(last["t"], "%d %b %H:%M"), report.inr(last["spot"]), report.inr(spot.value(prices, t)),
                report.inr(last["futures"]), report.inr(fut.value(prices, t)), _costs_text(spot, prices, t),
                _costs_text(fut, prices, t)))


def _lessons_text(book):
    if not book["lessons"]:
        return "No lessons noted yet."
    return "\n".join("- %s" % item["text"] for item in book["lessons"])


def _backtests_text(findings):
    if not findings:
        return ""
    return "Backtests of these strategies on earlier CoinDCX prices, with the same costs:\n%s\n\n" % "\n".join(
        "- %s" % line for line in findings)


def _tradable_text(rows, tradable):
    return ", ".join("%s %s (24h volatility %.1f%%)" % (r["coin"], _price(r["price"]), r["vol_24h"] * 100)
                     for r in rows if r["coin"] in tradable)


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


RULES = """You are part of an AI trading desk. It trades CoinDCX's Indian-rupee (INR) markets with simulated money in a \
{days}-day experiment ({start} to {end}); it is now {now}, day {day}.
It runs two books, each started with {capital}:
- Spot book: long only. Up to 5 coins, at most 30% of the book in any one coin, the rest in cash. Every position has a stop \
loss 2-15% below the price, and may have a take-profit.
- Futures book: one position at a time, long or short, at 1x to 3x leverage, with a stop loss 1-10% away. It may stay flat.
The aim is the highest value at the end of the experiment, after all costs. The desk is compared with buying and holding, \
and with the rule-based bots that trade the same coins.
Costs matter: a spot round trip costs about 1.2% plus the coin's spread, and a futures round trip about 0.12% plus funding. \
31.2% tax is due on every profitable sale and losses don't offset it. Churning small positions loses money, while a \
well-chosen position held through a trend can clear the costs many times over. Cash is a position too: choose it when the \
evidence is weak, not by default.
Only coins with at least ₹{min_volume:g} lakh of CoinDCX INR volume in the last 24 hours, and no trades in at most \
{max_idle}% of those 15-minute candles, can be traded: a quiet book shows stale prices, and a real order there would move them. \
A coin the desk holds that can't be traded any more is kept as it is, with its stop, until it can.
The desk meets every {every} hours. Orders fill at the next 15-minute close, and stops and take-profits are enforced \
automatically between meetings.
Use only the data you are given. Never invent prices, news, or events, and say so when the evidence is weak.
Answer with a single JSON object and nothing else."""

ROLES = {
    "market": "You are the desk's market analyst. You study price action, momentum, and volatility across every coin.",
    "news": "You are the desk's news and sentiment analyst. You read the latest crypto headlines and the market's mood.",
    "quant": "You are the desk's quant analyst. You study what the desk's rule-based bots have learned on each coin, and how "
             "futures traders are positioned.",
    "bull": "You are the desk's bull researcher. Make the strongest evidence-based case for taking positions now: the best "
            "coins to buy, and the best futures trade. Leave the case for caution to the bear and the risk team.",
    "bear": "You are the desk's bear researcher. Challenge the bull's case, point out what could go wrong, and name the coins "
            "to avoid or short.",
    "trader": "You are the desk's trader. Turn the research and the debate into a concrete plan for both books.",
    "aggressive": "You are the aggressive member of the desk's risk team. The goal is to grow each book as much as possible in "
                  "the time left. Argue for more risk where the reward justifies it.",
    "neutral": "You are the neutral member of the desk's risk team. Weigh risk and reward evenly.",
    "conservative": "You are the conservative member of the desk's risk team. Protect the capital: flag concentration, high "
                    "volatility, crowded trades, stops that are too wide, and overtrading.",
    "manager": "You are the desk's portfolio manager. You make the final decision for both books after hearing the analysts, "
               "the debate, the trader, and the risk team, and you learn from how the desk's trades have worked out. Weigh "
               "the evidence rather than siding with the most cautious or the boldest voice.",
}

PLAN_SHAPE = """{"spot": [{"coin": "SYMBOL", "weight_pct": 5 to 30, "stop_pct": 2 to 15, "take_profit_pct": number or null, \
"why": "one sentence"}],
 "futures": {"coin": "SYMBOL or null", "side": "long" | "short" | "flat", "leverage": 1 to 3, "stop_pct": 1 to 10, \
"take_profit_pct": number or null, "why": "one sentence"}}
The spot list is the whole target portfolio: coins you leave out are sold, and an empty list means all cash. Keep a \
position you still like rather than trading around it."""


def _system(role, context):
    return ROLES[role] + "\n\n" + RULES.format(**context)


def _prompts(ctx):
    rows, research_data = ctx["rows"], ctx["research"]
    fg = research_data.get("fear_greed")
    market = research_data.get("market")
    news = "\n".join("%sh | %s | %s" % (h["age_h"], h["source"], h["title"]) for h in research_data.get("headlines", []))
    return {
        "market": "Market data at %s. Prices are CoinDCX INR. Changes are in %%. rsi_1h is RSI(14) on hourly candles; trend "
                  "compares the 12- and 48-hour averages; vol_24h is the realised volatility of the last 24 hours in %%; "
                  "off_high_7d is how far the price is below its 7-day high; spread is the cost of crossing the bid-ask "
                  "spread once, in %%; volume_lakh is CoinDCX INR volume over 24 hours in lakh rupees; idle_pct is the "
                  "share of those 24 hours' 15-minute candles with no trades. tradable says 'no: stale' when prices have "
                  "stopped updating and 'no: thin' when the market is too quiet to trade.\n\n%s\n\n%s\n\n"
                  "Reply with this JSON:\n{\"regime\": \"risk-on\" | \"neutral\" | \"risk-off\", \"summary\": \"two sentences on "
                  "the market\", \"longs\": [{\"coin\": \"SYMBOL\", \"why\": \"one sentence with numbers\"}], \"shorts\": "
                  "[{\"coin\": \"SYMBOL\", \"why\": \"...\"}], \"avoid\": [{\"coin\": \"SYMBOL\", \"why\": \"...\"}]}\nAt most 6 "
                  "longs, 4 shorts, and 6 to avoid." % (
                      ctx["now"], _market_table(rows),
                      "Whole crypto market: total value %s%% in 24 hours, bitcoin dominance %s%%." % (
                          "%+.2f" % market["market_cap_change_24h"], market["btc_dominance"]) if market else
                      "Whole-market data could not be downloaded this time."),
        "news": "Crypto headlines from the last 24 hours (age in hours | source | title):\n%s\n\nFear & Greed index: %s.\n"
                "Trending on CoinGecko: %s.\nCoins the desk can trade: %s.\n\nReply with this JSON:\n{\"mood\": \"fear\" | "
                "\"neutral\" | \"greed\", \"summary\": \"two sentences on what the news means for prices\", \"coins\": "
                "[{\"coin\": \"SYMBOL\", \"tone\": -2 to 2, \"why\": \"which headline, and why\"}], \"risks\": [\"one line per "
                "risk\"]}\nOnly list coins the desk can trade, and only when a headline is actually about them (at most 8)." % (
                    news or "No headlines could be downloaded this time.",
                    "%d (%s), yesterday %s" % (fg["value"], fg["label"], fg["yesterday"]) if fg else "not available",
                    ", ".join(market["trending"]) if market and market.get("trending") else "not available",
                    ", ".join(r["coin"] for r in rows)),
        "quant": "What the desk's rule-based bots have found since %s. Each coin has %s strategy bots, a buy & hold bot, and "
                 "coin-flip bots that trade at random, which show how much of a result could be luck. Returns are in %%.\n\n"
                 "%s\n\nStrategy report card across all coins:\n%s\n\n%sPerpetual futures on Hyperliquid (global, in dollars): "
                 "funding every 8 hours in %% (positive means longs pay shorts, so longs are crowded), open interest and "
                 "24-hour volume in $ millions.\n%s\n\nReply with this JSON:\n{\"summary\": \"two sentences\", \"edges\": "
                 "[{\"coin\": \"SYMBOL\", \"evidence\": \"which strategies work there, with numbers\"}], \"crowded\": "
                 "[{\"coin\": \"SYMBOL\", \"side\": \"long\" | \"short\", \"why\": \"...\"}]}\nAt most 6 edges and 4 crowded "
                 "trades. Treat results no better than the coin flips as luck." % (
                     ctx["start"], ctx["swarm"][0]["count"] if ctx["swarm"] else "several", _swarm_table(ctx["swarm"]),
                     ctx["card"], _backtests_text(ctx["backtests"]), _derivatives_table(research_data.get("derivatives"))),
    }


def _answer_problem(role):
    def check(answer):
        if role in DEEP_ROLES:
            if not isinstance(answer.get("spot"), list) or not isinstance(answer.get("futures"), dict):
                return "the answer did not contain a plan for both books"
        elif not any(key in answer for key in EXPECTED[role]):
            return "the answer did not have the requested fields"
        return None
    return check


def _reports_text(analysts):
    return "\n".join("%s: %s" % (TITLES[role], _dump(analysts[role])) for role in ANALYSTS if analysts.get(role))


# ---- enforcing the limits ------------------------------------------------------------------------------------------

def _number(value, default=None):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def _symbol(text):
    s = str(text or "").upper().strip()
    if s.startswith("I-"):
        s = s[2:]
    for suffix in ("_INR", "/INR", "-INR", "INR"):
        if s.endswith(suffix) and len(s) > len(suffix):
            s = s[:-len(suffix)]
            break
    return s.strip()


def _percent(value):
    # Models sometimes write 0.05 for 5%. Nothing below 0.3% is a sensible stop or target, so read those as fractions.
    x = _number(value)
    if x is None or x <= 0:
        return None
    return x * 100 if x < 0.3 else x


def _stop(value, bounds, name, notes):
    lo, hi, default = bounds
    x = _percent(value)
    if x is None:
        notes.append("%s: no stop given, used %d%%" % (name, round(default * 100)))
        return default
    clamped = min(hi, max(lo, x / 100.0))
    if abs(clamped - x / 100.0) > 1e-9:
        notes.append("%s: stop moved from %g%% to %g%%" % (name, round(x, 2), round(clamped * 100, 1)))
    return clamped


def _take_profit(value):
    x = _percent(value)
    return None if x is None else min(TAKE_PROFIT[1], max(TAKE_PROFIT[0], x / 100.0))


def sanitize(plan, tradable):
    """Holds whatever a model proposed to the desk's hard limits. Returns the clean plan and a note for each change."""
    notes = []
    entries = plan.get("spot")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        notes.append("spot plan was not a list, so the spot book holds cash")
        entries = []
    entries = [e for e in entries if isinstance(e, dict)]
    weights = [max(0.0, _number(e.get("weight_pct"), 0.0)) for e in entries]
    scale = 1.0 / 100
    if weights and 0 < max(weights) <= 1.0 and sum(weights) <= 1.0 + 1e-9:
        notes.append("read the spot weights as fractions of the book")
        scale = 1.0
    spot = {}
    for entry, asked in zip(entries, weights):
        name = _symbol(entry.get("coin"))
        pair = tradable.get(name)
        if not pair:
            notes.append("dropped %s: not a coin the desk can trade now" % (name or "an unnamed coin"))
            continue
        weight = asked * scale + (spot[pair]["weight"] if pair in spot else 0.0)
        if weight > MAX_WEIGHT:
            notes.append("%s: cut from %g%% to %d%%" % (name, round(weight * 100, 1), MAX_WEIGHT * 100))
            weight = MAX_WEIGHT
        if weight < MIN_WEIGHT:
            notes.append("dropped %s: %g%% is too small to be worth the fees" % (name, round(weight * 100, 1)))
            continue
        spot[pair] = {"pair": pair, "weight": round(weight, 4), "stop": _stop(entry.get("stop_pct"), SPOT_STOP, name, notes),
                      "take_profit": _take_profit(entry.get("take_profit_pct")), "why": str(entry.get("why") or "")[:240]}
    ranked = sorted(spot.values(), key=lambda e: (-e["weight"], e["pair"]))
    if len(ranked) > MAX_POSITIONS:
        notes.append("kept the %d largest of %d spot positions" % (MAX_POSITIONS, len(ranked)))
        ranked = ranked[:MAX_POSITIONS]
    total = sum(e["weight"] for e in ranked)
    if total > MAX_INVESTED:
        notes.append("scaled the spot book from %d%% to %d%% invested" % (round(total * 100), MAX_INVESTED * 100))
        for e in ranked:
            e["weight"] = round(e["weight"] * MAX_INVESTED / total, 4)
    raw = plan.get("futures") if isinstance(plan.get("futures"), dict) else {}
    side = str(raw.get("side") or "flat").lower().strip()
    futures = {"side": "flat", "why": str(raw.get("why") or "")[:240]}
    if side in ("long", "short"):
        name = _symbol(raw.get("coin"))
        pair = tradable.get(name)
        if not pair:
            notes.append("futures: %s is not a coin the desk can trade now, so the book stays flat" % (name or "no coin given"))
        else:
            asked = _number(raw.get("leverage"), 1.0)
            leverage = min(MAX_LEVERAGE, max(1.0, round(asked * 2) / 2.0))
            if abs(leverage - asked) > 1e-9:
                notes.append("futures: leverage set to %gx instead of %gx" % (leverage, asked))
            futures.update(pair=pair, side=side, leverage=leverage,
                           stop=_stop(raw.get("stop_pct"), FUTURES_STOP, "futures " + name, notes),
                           take_profit=_take_profit(raw.get("take_profit_pct")))
    elif side != "flat":
        notes.append("futures: side %r is not long, short or flat, so the book stays flat" % side[:20])
    return {"spot": ranked, "futures": futures}, notes


def _decision(t, plan):
    return {"t": t, "spot": [dict((k, e[k]) for k in ("pair", "weight", "stop", "take_profit")) for e in plan["spot"]],
            "keep": list(plan.get("keep") or ()), "futures": dict((k, v) for k, v in plan["futures"].items() if k != "why")}


# ---- the meeting ---------------------------------------------------------------------------------------------------

def hold_meeting(root, state, config, series, prices, board, bots, now_ms, llm, gather=research.gather):
    settings = config["desk"]
    book = state["desk"]
    t = state["last_tick_t"]
    by_key = dict((bot.key, bot) for bot in bots)
    spot, fut = by_key[SPOT_KEY], by_key[FUTURES_KEY]
    if spot.acct.memo.get("stopped") and fut.acct.memo.get("stopped"):
        book["next_meeting"] = state["sim_end"]
        return None
    began = time.time()
    deadline = began + settings["time_budget_seconds"]
    rows, tradable = market_rows(config.get("universe") or (BTC,), series, prices, t, config, state.get("data_gaps", {}))
    outside = gather([r["coin"] for r in rows], now_ms)
    context = {"days": config["duration_days"], "start": report.ist(state["sim_start"], "%d %b %Y"),
               "end": report.ist(state["sim_end"], "%d %b %Y"), "now": report.ist(now_ms),
               "day": report.day_number(state, config, now_ms), "capital": report.inr(config["capital_inr"]),
               "every": settings["every_hours"], "min_volume": MIN_VOLUME_LAKH, "max_idle": int(round(MAX_IDLE * 100))}
    ctx = {"rows": rows, "research": outside, "now": report.ist(now_ms), "start": context["start"],
           "swarm": swarm_rows(board), "card": _card_text(board, config["capital_inr"]),
           "backtests": settings.get("backtests") or []}
    minutes = {"t": now_ms, "data_t": t, "agents": {}, "models": {}, "failed": {},
               "sources": {"coins": len(rows), "tradable": len(tradable), "headlines": len(outside.get("headlines", [])),
                           "fear_greed": outside.get("fear_greed"), "derivatives": len(outside.get("derivatives") or {}),
                           "errors": outside.get("errors", [])}}
    quick, deep = settings["quick_models"], settings["deep_models"] + settings["quick_models"]

    def ask(role, models, prompt):
        answer, model = llm.ask(role, models, _system(role, context), prompt, deadline, check=_answer_problem(role),
                                thinking="medium" if role in DEEP_ROLES else "low")
        minutes["agents"][role], minutes["models"][role] = answer, model
        return answer

    def attempt(role, models, prompt):
        try:
            return ask(role, models, prompt)
        except KeyRejected:
            raise
        except LLMError as exc:
            minutes["failed"][role] = str(exc)[:300]
            return None

    books = _books_text(spot, fut, prices, t)
    try:
        if len(tradable) < 3:
            raise LLMError("only %d coins have fresh prices" % len(tradable))
        prompts = _prompts(ctx)
        with ThreadPoolExecutor(max_workers=len(ANALYSTS)) as pool:
            jobs = [(role, pool.submit(attempt, role, quick, prompts[role])) for role in ANALYSTS]
            analysts = dict((role, job.result()) for role, job in jobs)
        if sum(1 for v in analysts.values() if v) < 2:
            raise LLMError("only %d of the 3 analysts answered" % sum(1 for v in analysts.values() if v))
        reports = _reports_text(analysts)
        bull = attempt("bull", quick, "Reports from the analysts:\n%s\n\nThe desk's books now:\n%s\n\nReply with this JSON:\n"
                                      "{\"thesis\": \"three sentences\", \"longs\": [{\"coin\": \"SYMBOL\", \"conviction\": 1 to 5, "
                                      "\"why\": \"...\"}], \"short\": {\"coin\": \"SYMBOL\", \"conviction\": 1 to 5, \"why\": "
                                      "\"...\"} or null}\nAt most 5 longs." % (reports, books))
        bear = attempt("bear", quick, "Reports from the analysts:\n%s\n\nThe bull researcher argues:\n%s\n\nThe desk's books "
                                      "now:\n%s\n\nReply with this JSON:\n{\"rebuttal\": \"three sentences answering the bull\", "
                                      "\"dangers\": [{\"coin\": \"SYMBOL\", \"why\": \"...\"}], \"shorts\": [{\"coin\": \"SYMBOL\", "
                                      "\"conviction\": 1 to 5, \"why\": \"...\"}], \"prefer_cash\": true or false}" % (
                                          reports, _dump(bull) if bull else "(no answer)", books))
        shared = ("Reports from the analysts:\n%s\n\nThe debate:\nBull: %s\nBear: %s\n\nThe desk's books now:\n%s\n\n%s\n\n"
                  "Recent closed trades:\n%s\n\nLessons the desk has noted:\n%s\n\nCoins the desk can trade now: %s" % (
                      reports, _dump(bull) if bull else "(no answer)", _dump(bear) if bear else "(no answer)", books,
                      _since_text(book, spot, fut, prices, t), _recent_text(spot, fut), _lessons_text(book),
                      _tradable_text(rows, tradable)))
        proposal = ask("trader", deep, "%s\n\nReply with this JSON:\n{\"summary\": \"two sentences\",\n %s" % (shared, PLAN_SHAPE[1:]))
        checked, _ = sanitize(proposal, tradable)
        review = "The trader proposes:\n%s\n\nThe desk's hard limits would turn it into:\n%s\n\nThe desk's books now:\n%s\n\n" \
                 "Market regime: %s. News mood: %s.\nCoins in the plan: %s\n\nReply with this JSON:\n{\"view\": \"two " \
                 "sentences\", \"changes\": [\"one concrete change per line, or none\"], \"verdict\": \"approve\" | \"adjust\" " \
                 "| \"reject\"}" % (
                     _dump(proposal), _dump(checked), books, (analysts.get("market") or {}).get("regime", "unknown"),
                     (analysts.get("news") or {}).get("mood", "unknown"),
                     _plan_coins_text(checked, rows, outside.get("derivatives") or {}))
        with ThreadPoolExecutor(max_workers=len(RISK_TEAM)) as pool:
            jobs = [(role, pool.submit(attempt, role, quick, review)) for role in RISK_TEAM]
            risk = dict((role, job.result()) for role, job in jobs)
        final = ask("manager", deep, "%s\n\nThe trader proposes:\n%s\n\nThe risk team:\n%s\n\nMake the final decision. Reply "
                                     "with this JSON:\n{\"minutes\": \"three to five sentences explaining the decision\",\n %s\n"
                                     "Also include \"lesson\": one sentence the desk should remember, based on how its recent "
                                     "trades worked out (or null if it is too early to tell)." % (
                                         shared, _dump(proposal),
                                         "\n".join("%s: %s" % (TITLES[r], _dump(risk[r]) if risk[r] else "(no answer)") for r in RISK_TEAM),
                                         PLAN_SHAPE[1:]))
    except KeyRejected as exc:
        return _failed(root, book, minutes, llm, now_ms, str(exc), retry_ms=6 * HOUR_MS)
    except LLMError as exc:
        return _failed(root, book, minutes, llm, now_ms, str(exc), retry_ms=30 * MINUTE_MS)

    plan, notes = sanitize(final, tradable)
    plan["keep"] = sorted(p for p in spot.acct.s["positions"] if p not in tradable.values())
    for pair in plan["keep"]:
        notes.append("kept %s as it is: it can't be traded now" % coin(pair))
    if spot.acct.memo.get("stopped"):
        plan["spot"] = []
    if fut.acct.memo.get("stopped"):
        plan["futures"] = {"side": "flat", "why": "stopped at the capital floor"}
    book["decisions"].append(_decision(t, plan))
    lesson = final.get("lesson")
    if isinstance(lesson, str) and lesson.strip() and lesson.strip().lower() not in ("null", "none"):
        book["lessons"].append({"t": now_ms, "text": " ".join(lesson.split())[:240]})
        del book["lessons"][:-LESSONS]
    minutes.update(plan=plan, notes=notes, seconds=round(time.time() - began, 1), calls=list(llm.log))
    book["last"] = {"t": now_ms, "plan": plan, "notes": notes[:8], "minutes": " ".join(str(final.get("minutes") or "").split())[:900],
                    "regime": (analysts.get("market") or {}).get("regime"), "mood": (analysts.get("news") or {}).get("mood"),
                    "fear_greed": outside.get("fear_greed"), "models": dict(minutes["models"]), "failed": sorted(minutes["failed"])}
    book["last_failure"] = None
    book["log"].append({"t": now_ms, "spot": round(spot.value(prices, t), 2), "futures": round(fut.value(prices, t), 2),
                        "plan": plan_text(plan)})
    del book["log"][:-LOG_SIZE]
    _count_calls(book, llm, now_ms)
    book["next_meeting"] = now_ms + settings["every_hours"] * HOUR_MS - 20 * MINUTE_MS
    if not book["announced"]:
        book["announce"] = book["announced"] = True
    save_minutes(root, minutes)
    print("AI desk met in %.0fs: %s" % (minutes["seconds"], plan_text(plan)))
    return minutes


def _plan_coins_text(plan, rows, derivs):
    by_coin = dict((r["coin"], r) for r in rows)
    names = [coin(e["pair"]) for e in plan["spot"]] + ([coin(plan["futures"]["pair"])] if plan["futures"].get("pair") else [])
    out = []
    for name in sorted(set(names)):
        r = by_coin.get(name)
        if r:
            d = derivs.get(name)
            out.append("%s: 24h %s%%, 7d %s%%, 24h volatility %.1f%%, RSI %s%s" % (
                name, _p(r["ch_24h"]), _p(r["ch_7d"]), r["vol_24h"] * 100, "–" if r["rsi"] is None else "%.0f" % r["rsi"],
                ", funding %+.4f%% per 8h" % d["funding_8h_pct"] if d else ""))
    return "; ".join(out) or "none (all cash and flat)"


def _failed(root, book, minutes, llm, now_ms, reason, retry_ms):
    book["last_failure"] = {"t": now_ms, "reason": reason[:300]}
    book["next_meeting"] = now_ms + retry_ms
    _count_calls(book, llm, now_ms)
    minutes.update(error=reason[:300], calls=list(llm.log))
    save_minutes(root, minutes)
    print("AI desk meeting skipped: %s" % reason[:300])
    return minutes


def _count_calls(book, llm, now_ms):
    day = report.ist(now_ms, "%Y-%m-%d")
    calls = book.setdefault("calls", {})
    calls[day] = calls.get(day, 0) + sum(1 for c in llm.log if c["outcome"] == "ok")
    for old in sorted(calls)[:-3]:
        del calls[old]


def plan_text(plan):
    spot = ", ".join(["%s %d%%" % (coin(e["pair"]), round(e["weight"] * 100)) for e in plan["spot"]] +
                     ["%s kept as it is" % coin(p) for p in plan.get("keep") or ()]) or "all cash"
    f = plan["futures"]
    futures = "%s %s %gx" % (f["side"], coin(f["pair"]), f["leverage"]) if f.get("pair") else "flat"
    return "spot: %s; futures: %s" % (spot, futures)


# ---- the minutes ---------------------------------------------------------------------------------------------------

def save_minutes(root, minutes):
    state_dir = os.path.join(root, "state")
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, MINUTES_FILE)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(minutes, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    with open(path, encoding="utf-8") as fh:
        recent = [json.loads(line) for line in fh.readlines()[-MINUTES_SHOWN:] if line.strip()]
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    with open(os.path.join(root, "docs", "desk.md"), "w", encoding="utf-8") as fh:
        fh.write(render_minutes(list(reversed(recent))))


def _cell(value):
    return " ".join(str(value if value is not None else "").split()).replace("|", "/")


def _items(value, *fields):
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return _cell(value) or "none"
    out = []
    for item in value:
        if isinstance(item, dict):
            head = _cell(item.get("coin") or "")
            extra = [_cell(item[f]) for f in fields if item.get(f) not in (None, "")]
            out.append("%s%s%s" % (head, ": " if head and extra else "", ", ".join(extra)))
        elif item not in (None, ""):
            out.append(_cell(item))
    return "; ".join(o for o in out if o) or "none"


def _agent_text(role, a):
    if role == "market":
        return "%s. %s Longs: %s. Shorts: %s. Avoid: %s." % (
            _cell(a.get("regime")), _cell(a.get("summary")), _items(a.get("longs"), "why"), _items(a.get("shorts"), "why"),
            _items(a.get("avoid"), "why"))
    if role == "news":
        return "Mood: %s. %s Coins: %s. Risks: %s." % (_cell(a.get("mood")), _cell(a.get("summary")),
                                                       _items(a.get("coins"), "tone", "why"), _items(a.get("risks")))
    if role == "quant":
        return "%s Edges: %s. Crowded: %s." % (_cell(a.get("summary")), _items(a.get("edges"), "evidence"),
                                               _items(a.get("crowded"), "side", "why"))
    if role == "bull":
        return "%s Longs: %s. Short: %s." % (_cell(a.get("thesis")), _items(a.get("longs"), "conviction", "why"),
                                             _items(a.get("short"), "conviction", "why"))
    if role == "bear":
        return "%s Dangers: %s. Shorts: %s. Prefers cash: %s." % (
            _cell(a.get("rebuttal")), _items(a.get("dangers"), "why"), _items(a.get("shorts"), "conviction", "why"),
            _cell(a.get("prefer_cash")))
    if role == "trader":
        return "%s %s" % (_cell(a.get("summary")), _proposal_text(a))
    if role in RISK_TEAM:
        return "%s: %s Changes: %s." % (_cell(a.get("verdict")), _cell(a.get("view")), _items(a.get("changes")))
    lesson = _cell(a.get("lesson"))
    return "%s%s" % (_cell(a.get("minutes")), " Lesson: %s" % lesson if lesson and lesson.lower() not in ("null", "none") else "")


def _proposal_text(a):
    spot = []
    for e in a.get("spot") if isinstance(a.get("spot"), list) else ():
        if isinstance(e, dict):
            spot.append("%s %s%%, stop %s%%%s" % (_cell(e.get("coin")), _cell(e.get("weight_pct")), _cell(e.get("stop_pct")),
                                                  " (%s)" % _cell(e["why"]) if e.get("why") else ""))
    f = a.get("futures") if isinstance(a.get("futures"), dict) else {}
    side = _cell(f.get("side")).lower() or "flat"
    futures = "flat" if side == "flat" else "%s %s at %sx, stop %s%%" % (
        side, _cell(f.get("coin")), _cell(f.get("leverage")), _cell(f.get("stop_pct")))
    return "Spot: %s. Futures: %s%s." % ("; ".join(spot) or "all cash", futures, " (%s)" % _cell(f["why"]) if f.get("why") else "")


def plan_rows(plan):
    lines = ["| Book | Coin | Size | Stop | Take-profit | Why |", "|---|---|---|---|---|---|"]
    for e in plan["spot"]:
        lines.append("| Spot | %s | %d%% | -%g%% | %s | %s |" % (
            coin(e["pair"]), round(e["weight"] * 100), round(e["stop"] * 100, 1),
            "+%g%%" % round(e["take_profit"] * 100, 1) if e.get("take_profit") else "–", _cell(e.get("why"))))
    if not plan["spot"]:
        lines.append("| Spot | – | all cash | – | – | |")
    f = plan["futures"]
    if f.get("pair"):
        lines.append("| Futures | %s | %s %gx | %g%% away | %s | %s |" % (
            coin(f["pair"]), f["side"], f["leverage"], round(f["stop"] * 100, 1),
            "%g%% away" % round(f["take_profit"] * 100, 1) if f.get("take_profit") else "–", _cell(f.get("why"))))
    else:
        lines.append("| Futures | – | flat | – | – | %s |" % _cell(f.get("why")))
    return lines


def render_minutes(meetings):
    lines = [
        "# AI trading desk: meeting minutes",
        "",
        "Newest first; the last %d meetings are kept here, and every meeting is archived in "
        "[`state/%s`](../state/%s). At each meeting three analysts report, a bull and a bear debate, the trader proposes "
        "a plan, three risk reviewers critique it, and the portfolio manager decides. The code then applies the desk's hard "
        "limits, and the orders fill at the next 15-minute close. Everything is simulated." % (MINUTES_SHOWN, MINUTES_FILE, MINUTES_FILE),
    ]
    for m in meetings:
        lines += ["", "## %s" % report.ist(m["t"])]
        if m.get("error"):
            lines += ["", "The meeting could not finish: %s. The books kept their positions and stops." % _cell(m["error"])]
        else:
            lines += ["", "**Decision.** %s" % _cell((m["agents"].get("manager") or {}).get("minutes")), ""]
            lines += plan_rows(m["plan"])
            if m.get("notes"):
                lines += ["", "Limits applied by the code: %s." % "; ".join(_cell(n) for n in m["notes"])]
        agents = [(role, m["agents"][role]) for role in TITLES if role in m.get("agents", {})]
        if agents:
            lines += ["", "<details><summary>What each agent said</summary>", ""]
            for role, answer in agents:
                lines.append("- **%s** (%s): %s" % (TITLES[role], m["models"].get(role, "?"),
                                                    _agent_text(role, answer) if isinstance(answer, dict) else _cell(answer)))
            lines += ["", "</details>"]
        src = m.get("sources", {})
        fg = src.get("fear_greed")
        lines += ["", "Inputs: prices for %s coins (%s tradable), %s headlines, Fear & Greed %s, futures positioning for %s coins%s. "
                  "%d AI calls%s%s." % (
                      src.get("coins", 0), src.get("tradable", 0), src.get("headlines", 0),
                      "%d (%s)" % (fg["value"], fg["label"]) if fg else "unavailable", src.get("derivatives", 0),
                      "; unavailable: %s" % ", ".join(src["errors"]) if src.get("errors") else "",
                      sum(1 for c in m.get("calls", ()) if c["outcome"] == "ok"),
                      " in %.0f seconds" % m["seconds"] if m.get("seconds") else "",
                      "; no answer from: %s" % ", ".join(TITLES.get(r, r) for r in sorted(m["failed"])) if m.get("failed") else "")]
    return "\n".join(lines) + "\n"
