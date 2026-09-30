"""The AI trading desk. The agents and the news are faked, so nothing here calls Gemini or downloads anything."""
import copy
import csv
import datetime as dt
import io
import json
import os
import time
import unittest
import urllib.error
from email.utils import format_datetime
from unittest import mock

import test_robustness as rb
from sim import desk, engine, report, research
from sim.accounts import SpotAccount
from sim.llm import DAY_MS, QUOTA_RESET_UTC_MS, Gemini, KeyRejected, LLMError, parse_json
from synthetic import DAY, H1, M15, START, build_market, make_fetch

MINUTE = 60000
UNIVERSE = ("I-DOGE_INR", "I-SOL_INR", "I-XRP_INR", "I-ETH_INR", "I-BTC_INR")
TRADABLE = dict((pair[2:-4], pair) for pair in UNIVERSE)
FIRST = START + DAY + 7 * MINUTE

TRADER = {
    "summary": "Trend and news both favour SOL.",
    "spot": [{"coin": "SOL", "weight_pct": 30, "stop_pct": 5, "take_profit_pct": 12, "why": "uptrend"},
             {"coin": "ETH", "weight_pct": 25, "stop_pct": 6, "why": "steady"}],
    "futures": {"coin": "BTC", "side": "long", "leverage": 2, "stop_pct": 4, "take_profit_pct": 8, "why": "trend up"},
}
MANAGER = {
    "minutes": "We buy SOL and ETH and go long BTC.",
    "lesson": "Trends pay.",
    "spot": TRADER["spot"] + [{"coin": "FOO", "weight_pct": 10, "stop_pct": 5, "why": "made up"}],
    "futures": {"coin": "I-BTC_INR", "side": "long", "leverage": 5, "stop_pct": 20, "take_profit_pct": 8, "why": "trend up"},
}
ANSWERS = {
    "market": {"regime": "risk-on", "summary": "Majors are rising.", "longs": [{"coin": "SOL", "why": "up 3% in 24h"}],
               "shorts": [], "avoid": [{"coin": "DOGE", "why": "choppy"}]},
    "news": {"mood": "greed", "summary": "An ETF headline.", "coins": [{"coin": "SOL", "tone": 2, "why": "ETF approved"}],
             "risks": ["rates"]},
    "quant": {"summary": "Trend bots lead.", "edges": [{"coin": "SOL", "evidence": "trend bots +4%"}], "crowded": []},
    "bull": {"thesis": "SOL leads the market.", "longs": [{"coin": "SOL", "conviction": 4, "why": "trend and news"}],
             "short": None},
    "bear": {"rebuttal": "SOL is stretched.", "dangers": [{"coin": "SOL", "why": "RSI 72"}], "shorts": [], "prefer_cash": False},
    "trader": TRADER,
    "aggressive": {"view": "Size up SOL.", "changes": ["SOL 30%"], "verdict": "approve"},
    "neutral": {"view": "Balanced.", "changes": [], "verdict": "approve"},
    "conservative": {"view": "Stops are fine.", "changes": ["keep BTC small"], "verdict": "adjust"},
    "manager": MANAGER,
}


def news(coins, now_ms):
    return {"headlines": [{"source": "Test Wire", "title": "Solana ETF approved", "age_h": 1.5}],
            "fear_greed": {"value": 71, "label": "Greed", "yesterday": 64},
            "market": {"trending": ["SOL", "PEPE"], "market_cap_change_24h": 1.8, "btc_dominance": 57.9},
            "derivatives": {"BTC": {"funding_8h_pct": 0.01, "open_interest_usd_m": 9000.0, "volume_24h_usd_m": 4000.0}},
            "errors": ["CryptoSlate news: HTTPError"]}


class FakeLLM:
    """Stands in for both the client factory and the client. Each role answers from a list, first acceptable wins."""

    def __init__(self, answers=None, fail=(), error=None):
        self.answers = dict(ANSWERS, **(answers or {}))
        self.fail = set(fail)
        self.error = error
        self.prompts = {}
        self.log = []

    def __call__(self, cooldowns, now_ms):
        self.log = []
        return self

    def ask(self, role, models, system, prompt, deadline, check=None, thinking="low"):
        self.prompts[role] = (system, prompt, thinking)
        if self.error is not None:
            raise self.error
        if role in self.fail:
            self.log.append({"role": role, "model": "fake", "seconds": 0.0, "outcome": "down"})
            raise LLMError("%s is down" % role)
        options = self.answers[role]
        for n, answer in enumerate(options if isinstance(options, list) else [options]):
            if check and check(answer):
                continue
            self.log.append({"role": role, "model": "fake-%d" % n, "seconds": 0.0, "outcome": "ok"})
            return copy.deepcopy(answer), "fake-%d" % n
        raise LLMError("no model gave a usable answer")


def no_key(cooldowns, now_ms):
    return None


def read_config():
    with open(os.path.join(rb.ROOT, "config.json"), encoding="utf-8") as fh:
        return json.load(fh)


def trades(ws, bot):
    path = os.path.join(ws.root, "state", "trades.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [row for row in csv.DictReader(fh) if row["bot"] == bot]


def read(ws, *parts):
    with open(os.path.join(ws.root, *parts), encoding="utf-8") as fh:
        return fh.read()


class SanitizeTest(unittest.TestCase):
    def test_every_plan_is_held_to_the_limits(self):
        plan, notes = desk.sanitize({
            "spot": [{"coin": "SOL", "weight_pct": 45, "stop_pct": 40, "take_profit_pct": 500},
                     {"coin": "I-ETH_INR", "weight_pct": 25},
                     {"coin": "FOO", "weight_pct": 20},
                     {"coin": "doge/inr", "weight_pct": 3},
                     {"coin": "xrp", "weight_pct": 28, "stop_pct": 0.5},
                     {"coin": "BTC", "weight_pct": 29, "stop_pct": 0.05},
                     "not a position"],
            "futures": {"coin": "BTC", "side": "LONG", "leverage": 25, "stop_pct": 30}}, TRADABLE)
        spot = dict((e["pair"], e) for e in plan["spot"])
        self.assertEqual([e["pair"] for e in plan["spot"]], ["I-SOL_INR", "I-BTC_INR", "I-XRP_INR", "I-ETH_INR"])
        self.assertAlmostEqual(sum(e["weight"] for e in plan["spot"]), desk.MAX_INVESTED, places=3)
        self.assertTrue(all(e["weight"] <= desk.MAX_WEIGHT for e in plan["spot"]))
        self.assertEqual((spot["I-SOL_INR"]["stop"], spot["I-SOL_INR"]["take_profit"]), (0.15, 1.0))
        self.assertEqual(spot["I-XRP_INR"]["stop"], 0.02)
        self.assertAlmostEqual(spot["I-BTC_INR"]["stop"], 0.05)
        self.assertEqual(spot["I-ETH_INR"]["stop"], desk.SPOT_STOP[2])
        self.assertEqual(plan["futures"], {"side": "long", "pair": "I-BTC_INR", "leverage": 3.0, "stop": 0.10,
                                           "take_profit": None, "why": ""})
        for expected in ("SOL: cut from 45% to 30%", "dropped FOO: not a coin the desk can trade now",
                         "dropped DOGE: 3% is too small to be worth the fees", "XRP: stop moved from 0.5% to 2%",
                         "SOL: stop moved from 40% to 15%", "ETH: no stop given, used 8%",
                         "scaled the spot book from 112% to 95% invested", "futures: leverage set to 3x instead of 25x",
                         "futures BTC: stop moved from 30% to 10%"):
            self.assertIn(expected, notes)

    def test_odd_answers_become_safe_plans(self):
        plan, notes = desk.sanitize({"spot": [{"coin": "SOL", "weight_pct": 0.2, "stop_pct": 0.04},
                                              {"coin": "sol", "weight_pct": 0.15, "stop_pct": 4}]}, TRADABLE)
        self.assertEqual(plan["spot"], [{"pair": "I-SOL_INR", "weight": 0.3, "stop": 0.04, "take_profit": None, "why": ""}])
        self.assertIn("read the spot weights as fractions of the book", notes)
        self.assertIn("SOL: cut from 35% to 30%", notes)
        self.assertEqual(plan["futures"], {"side": "flat", "why": ""})

        plan, notes = desk.sanitize({"spot": "all in", "futures": "to the moon"}, TRADABLE)
        self.assertEqual(plan, {"spot": [], "futures": {"side": "flat", "why": ""}})
        self.assertEqual(notes, ["spot plan was not a list, so the spot book holds cash"])
        self.assertEqual(desk.sanitize({}, TRADABLE), ({"spot": [], "futures": {"side": "flat", "why": ""}}, []))

        plan, notes = desk.sanitize({"futures": {"coin": "PEPE", "side": "short", "leverage": 2}}, TRADABLE)
        self.assertEqual(plan["futures"]["side"], "flat")
        self.assertIn("futures: PEPE is not a coin the desk can trade now, so the book stays flat", notes)
        plan, notes = desk.sanitize({"futures": {"coin": "ETH", "side": "buy"}}, TRADABLE)
        self.assertEqual(plan["futures"]["side"], "flat")
        self.assertIn("futures: side 'buy' is not long, short or flat, so the book stays flat", notes)

        plan, notes = desk.sanitize({"futures": {"coin": "eth", "side": "short", "leverage": "2.3", "stop_pct": "nan",
                                                 "take_profit_pct": 0.1}}, TRADABLE)
        self.assertEqual(plan["futures"], {"side": "short", "pair": "I-ETH_INR", "leverage": 2.5, "stop": desk.FUTURES_STOP[2],
                                           "take_profit": 0.1, "why": ""})
        self.assertEqual(notes, ["futures: leverage set to 2.5x instead of 2.3x", "futures ETH: no stop given, used 5%"])

    def test_only_the_five_largest_positions_are_kept(self):
        tradable = dict(("C%d" % n, "I-C%d_INR" % n) for n in range(7))
        plan, notes = desk.sanitize({"spot": [{"coin": "C%d" % n, "weight_pct": 10 + n, "stop_pct": 5} for n in range(7)]},
                                    tradable)
        self.assertEqual([e["pair"] for e in plan["spot"]], ["I-C6_INR", "I-C5_INR", "I-C4_INR", "I-C3_INR", "I-C2_INR"])
        self.assertAlmostEqual(sum(e["weight"] for e in plan["spot"]), 0.70)
        self.assertEqual(notes, ["kept the 5 largest of 7 spot positions"])


class DeskRunTest(unittest.TestCase):
    def setUp(self):
        self.ws = rb.Workspace(universe=UNIVERSE)

    def tearDown(self):
        self.ws.close()

    def run_at(self, now, llm, fetch, notify=False):
        return self.ws.run(now, fetch, notify=notify, desk_llm=llm, gather=news)

    def test_the_desk_meets_and_trades_at_the_next_close(self):
        fetch = make_fetch(build_market("calm", seed=3))
        fake = FakeLLM()
        self.run_at(FIRST, fake, fetch)
        state = self.ws.state()
        book = state["desk"]
        self.assertEqual(len(book["decisions"]), 1)
        decision = book["decisions"][0]
        self.assertEqual(decision["t"], state["last_tick_t"])
        self.assertEqual(decision["spot"], [{"pair": "I-SOL_INR", "weight": 0.3, "stop": 0.05, "take_profit": 0.12},
                                            {"pair": "I-ETH_INR", "weight": 0.25, "stop": 0.06, "take_profit": None}])
        self.assertEqual(decision["futures"], {"pair": "I-BTC_INR", "side": "long", "leverage": 3.0, "stop": 0.1,
                                               "take_profit": 0.08})
        self.assertEqual(book["last"]["notes"], ["dropped FOO: not a coin the desk can trade now",
                                                 "futures: leverage set to 3x instead of 5x",
                                                 "futures BTC: stop moved from 20% to 10%"])
        self.assertEqual(book["lessons"][0]["text"], "Trends pay.")
        self.assertEqual(book["next_meeting"], FIRST + 2 * H1 - 20 * MINUTE)
        self.assertEqual(sum(book["calls"].values()), len(desk.TITLES))

        self.assertEqual(sorted(fake.prompts), sorted(desk.TITLES))
        self.assertEqual(fake.prompts["trader"][2], "medium")
        self.assertEqual(fake.prompts["market"][2], "low")
        system, prompt, _ = fake.prompts["market"]
        self.assertIn("15-day experiment", system)
        for name in TRADABLE:
            self.assertIn("\n%s|" % name, prompt)
        self.assertIn("Solana ETF approved", fake.prompts["news"][1])
        self.assertIn("71 (Greed), yesterday 64", fake.prompts["news"][1])
        self.assertIn("BTC|+0.0100|9000.0|4000.0", fake.prompts["quant"][1])
        self.assertIn("Bear: {", fake.prompts["trader"][1])
        self.assertIn("Risk team, conservative: {", fake.prompts["manager"][1])
        self.assertIn("This is the desk's first meeting.", fake.prompts["manager"][1])

        # Nothing trades until the next candle closes.
        for key in (desk.SPOT_KEY, desk.FUTURES_KEY):
            self.assertEqual(trades(self.ws, key), [])
        readme = read(self.ws, "README.md")
        self.assertIn("**AI trading desk.**", readme)
        self.assertIn("Spot: SOL 30% (stop -5%, target +12%), ETH 25% (stop -6%). Futures: long BTC at 3x (stop 10% away, "
                      "target 8% away).", readme)
        minutes = read(self.ws, "docs", "desk.md")
        self.assertIn("**Portfolio manager** (fake-0): We buy SOL and ETH and go long BTC. Lesson: Trends pay.", minutes)
        self.assertIn("Spot: SOL 30%, stop 5% (uptrend); ETH 25%, stop 6% (steady). Futures: long BTC at 2x, stop 4% "
                      "(trend up).", minutes)
        self.assertIn("| Spot | SOL | 30% | -5% | +12% | uptrend |", minutes)
        self.assertIn("unavailable: CryptoSlate news: HTTPError", minutes)

        self.run_at(FIRST + 30 * MINUTE, fake, fetch)
        state = self.ws.state()
        spot, fut = state["bots"][desk.SPOT_KEY], state["bots"][desk.FUTURES_KEY]
        self.assertEqual([(r["side"], r["pair"], r["reason"]) for r in trades(self.ws, desk.SPOT_KEY)],
                         [("BUY", "SOL/INR", "desk: buy to 30%"), ("BUY", "ETH/INR", "desk: buy to 25%")])
        self.assertAlmostEqual(float(trades(self.ws, desk.SPOT_KEY)[0]["value"]), 1500, delta=30)
        sol = spot["positions"]["I-SOL_INR"]
        entry = sol["cost"] / sol["qty"]
        self.assertTrue(0.94 < sol["stop"] / entry < 0.95, sol)
        self.assertTrue(1.11 < sol["target"] / entry < 1.12, sol)
        self.assertIsNone(spot["positions"]["I-ETH_INR"]["target"])
        pos = fut["position"]
        self.assertEqual((pos["pair"], pos["side"], pos["leverage"]), ("I-BTC_INR", "long", 3.0))
        self.assertAlmostEqual(pos["stop"], pos["entry"] * 0.9)
        self.assertAlmostEqual(pos["target"], pos["entry"] * 1.08)
        self.assertIn("holding ETH, SOL", read(self.ws, "README.md"))
        self.assertIn("long BTC at 3x", read(self.ws, "README.md"))

        # The next meeting is about two hours later. A looser stop is ignored, and an unchanged plan does not trade.
        self.run_at(FIRST + 90 * MINUTE, fake, fetch)
        self.assertEqual(len(self.ws.state()["desk"]["decisions"]), 1)
        fake.answers["manager"] = dict(MANAGER, spot=[dict(TRADER["spot"][0], stop_pct=10), TRADER["spot"][1]])
        self.run_at(FIRST + 2 * H1, fake, fetch)
        self.assertEqual(len(self.ws.state()["desk"]["decisions"]), 2)
        self.assertIn("Since the last meeting", fake.prompts["manager"][1])
        self.run_at(FIRST + 2 * H1 + 30 * MINUTE, fake, fetch)
        state = self.ws.state()
        self.assertEqual(state["bots"][desk.SPOT_KEY]["positions"]["I-SOL_INR"]["stop"], sol["stop"])
        self.assertEqual(len(trades(self.ws, desk.SPOT_KEY)), 2)
        self.assertEqual(len(trades(self.ws, desk.FUTURES_KEY)), 1)
        self.assertEqual(state["bots"][desk.FUTURES_KEY]["position"]["entry"], pos["entry"])
        rb.check_invariants(self, state)

    def test_stops_limit_the_damage_in_a_crash(self):
        fetch = make_fetch(build_market("crash", seed=4))
        fake = FakeLLM(answers={"manager": dict(MANAGER, futures=dict(MANAGER["futures"], leverage=2, stop_pct=4))})
        before = START + 4 * DAY + 7 * MINUTE
        self.run_at(before, fake, fetch)
        self.run_at(before + 30 * MINUTE, fake, fetch)
        state = self.ws.state()
        self.assertTrue(state["bots"][desk.SPOT_KEY]["positions"])
        self.assertIsNotNone(state["bots"][desk.FUTURES_KEY]["position"])
        self.run_at(START + 6 * DAY + 7 * MINUTE, no_key, fetch)
        state = self.ws.state()
        spot, fut = state["bots"][desk.SPOT_KEY], state["bots"][desk.FUTURES_KEY]
        self.assertEqual(spot["positions"], {})
        self.assertIsNone(fut["position"])
        exits = [r["reason"] for r in trades(self.ws, desk.SPOT_KEY) if r["side"] == "SELL"]
        self.assertEqual(len(exits), 2)
        self.assertTrue(set(exits) <= {"stop loss", "take profit"}, exits)
        closes = [r for r in trades(self.ws, desk.FUTURES_KEY) if r["side"] != "OPEN LONG"]
        self.assertEqual([r["side"] for r in closes], ["CLOSE LONG"])
        self.assertIn(closes[0]["reason"], ("stop loss", "take profit"))
        self.assertEqual(fut["liquidations"], 0)
        self.assertGreater(spot["last_value"], 4700)
        self.assertGreater(fut["last_value"], 4300)
        self.assertGreater(spot["last_value"], state["bots"]["hodl_btc"]["last_value"])
        rb.check_invariants(self, state)

    def test_a_failed_meeting_is_skipped_and_retried(self):
        fetch = make_fetch(build_market("calm", seed=5))
        down = FakeLLM(fail=desk.ANALYSTS)
        self.run_at(FIRST, down, fetch)
        book = self.ws.state()["desk"]
        self.assertEqual(book["decisions"], [])
        self.assertEqual(book["last_failure"]["reason"], "only 0 of the 3 analysts answered")
        self.assertEqual(book["next_meeting"], FIRST + 30 * MINUTE)
        self.assertIn("could not finish (only 0 of the 3 analysts answered)", read(self.ws, "README.md"))
        self.assertIn("The meeting could not finish: only 0 of the 3 analysts answered.", read(self.ws, "docs", "desk.md"))
        self.assertNotIn("trader", down.prompts)

        self.run_at(FIRST + 15 * MINUTE, down, fetch)
        self.assertEqual(len(read(self.ws, "state", desk.MINUTES_FILE).splitlines()), 1)

        partial = FakeLLM(fail=("news",))
        self.run_at(FIRST + 30 * MINUTE, partial, fetch)
        book = self.ws.state()["desk"]
        self.assertEqual(len(book["decisions"]), 1)
        self.assertIsNone(book["last_failure"])
        self.assertEqual(book["last"]["failed"], ["news"])
        self.assertNotIn("News analyst", partial.prompts["bull"][1])
        self.assertNotIn("could not finish", read(self.ws, "README.md"))
        self.assertIn("no answer from: News analyst", read(self.ws, "docs", "desk.md"))

    def test_a_plan_without_both_books_falls_back_to_the_next_model(self):
        fetch = make_fetch(build_market("calm", seed=5))
        fake = FakeLLM(answers={"manager": [{"minutes": "I forgot the plan."}, MANAGER]})
        self.run_at(FIRST, fake, fetch)
        book = self.ws.state()["desk"]
        self.assertEqual(book["last"]["models"]["manager"], "fake-1")
        self.assertEqual(len(book["decisions"][0]["spot"]), 2)

    def test_a_rejected_key_waits_six_hours(self):
        fetch = make_fetch(build_market("calm", seed=5))
        rejected = FakeLLM(error=KeyRejected("the API key was rejected (HTTP 403): Permission denied"))
        self.run_at(FIRST, rejected, fetch)
        book = self.ws.state()["desk"]
        self.assertEqual(book["decisions"], [])
        self.assertEqual(book["next_meeting"], FIRST + 6 * H1)
        readme = read(self.ws, "README.md")
        self.assertIn("the API key was rejected", readme)
        self.assertIn("tries again after %s" % report.ist(FIRST + 6 * H1), readme)

    def test_without_a_key_the_desk_waits_in_cash(self):
        fetch = make_fetch(build_market("calm", seed=6))
        self.ws.run(FIRST, fetch, notify=False)
        state = self.ws.state()
        self.assertTrue(state["desk"]["waiting_for_key"])
        self.assertEqual(state["desk"]["decisions"], [])
        readme = read(self.ws, "README.md")
        self.assertIn("waiting for a `GEMINI_API_KEY`", readme)
        self.assertIn("cash, waiting for the first AI meeting", readme)
        self.assertFalse(os.path.exists(os.path.join(self.ws.root, "docs", "desk.md")))

    def test_the_first_decision_is_announced_once(self):
        fetch = make_fetch(build_market("calm", seed=7))
        github, mailer = rb.FakeGitHub(), rb.FakeMailer()
        fake = FakeLLM()
        with mock.patch.object(engine.GitHub, "from_env", return_value=github), \
                mock.patch.object(engine.Mailer, "from_env", return_value=mailer):
            self.run_at(FIRST, fake, fetch, notify=True)
            self.run_at(FIRST + 2 * H1, fake, fetch, notify=True)
        self.assertEqual(len(self.ws.state()["desk"]["decisions"]), 2)
        comments = [c for c in github.calls if c[0] == "comment" and "AI trading desk has joined" in c[2]]
        self.assertEqual(len(comments), 1)
        bodies = [body for subject, body in mailer.sent if subject == report.DESK_TITLE]
        self.assertEqual(len(bodies), 1)
        self.assertIn("TradingAgents", bodies[0])
        self.assertIn("no proven edge", bodies[0])

    def test_an_upgrade_replays_the_desk_exactly(self):
        fetch = make_fetch(build_market("chop", seed=8))
        fake = FakeLLM()
        now = FIRST
        for n in range(9):
            if n == 4:
                fake.answers["manager"] = dict(MANAGER, spot=[TRADER["spot"][1]],
                                               futures=dict(MANAGER["futures"], coin="SOL", side="short"))
            self.run_at(now, fake, fetch)
            now += 30 * MINUTE
        before = self.ws.state()
        self.assertEqual(len(before["desk"]["decisions"]), 3)
        desk_trades = dict((key, trades(self.ws, key)) for key in (desk.SPOT_KEY, desk.FUTURES_KEY))
        self.assertTrue(any(r["side"] == "OPEN SHORT" for r in desk_trades[desk.FUTURES_KEY]))
        before["version"] = 1
        with open(os.path.join(self.ws.root, "state", "state.json"), "w", encoding="utf-8") as fh:
            json.dump(before, fh)
        self.run_at(now - 30 * MINUTE, no_key, fetch)
        after = self.ws.state()
        self.assertEqual(after["version"], engine.STATE_VERSION)
        for key in (desk.SPOT_KEY, desk.FUTURES_KEY):
            self.assertEqual(after["bots"][key], before["bots"][key], key)
            self.assertEqual(trades(self.ws, key), desk_trades[key], key)


class FloorTest(unittest.TestCase):
    def test_a_book_that_falls_to_the_floor_stops_for_good(self):
        config = read_config()
        acct = SpotAccount(SpotAccount.fresh(5000), config["costs"], config["markets"], lambda row: None)
        book = desk.fresh_book()
        bot = desk.DeskSpot(acct, ("I-SOL_INR",), book)
        ctx = engine.Context({"I-SOL_INR": 12000.0}, {})
        acct.buy("I-SOL_INR", 2000, 12000.0, START, "test")
        ctx.prices["I-SOL_INR"] = 120.0
        ctx.t = START + M15
        bot.on_tick(ctx)
        self.assertTrue(acct.memo["stopped"])
        self.assertEqual(acct.s["positions"], {})
        book["decisions"].append({"t": START + M15, "spot": [{"pair": "I-SOL_INR", "weight": 0.3, "stop": 0.05,
                                                              "take_profit": None}], "futures": {"side": "flat"}})
        ctx.t = START + 2 * M15
        bot.on_tick(ctx)
        self.assertEqual(acct.s["positions"], {})
        self.assertEqual(bot.describe(), "cash, stopped at the capital floor")


def http_error(code, error):
    return urllib.error.HTTPError("https://example.test", code, "error", {}, io.BytesIO(json.dumps({"error": error}).encode()))


def reply(text, thought=None):
    parts = ([{"text": thought, "thought": True}] if thought else []) + [{"text": text}]
    return {"candidates": [{"content": {"parts": parts}, "finishReason": "STOP"}]}


class Transport:
    def __init__(self, script):
        self.script = script
        self.calls = []

    def __call__(self, url, body, headers, timeout):
        model = url.split("/models/")[1].split(":")[0]
        self.calls.append((model, copy.deepcopy(body), headers))
        outcome = self.script[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class GeminiTest(unittest.TestCase):
    NOW = START + 3 * H1
    KEY = "not-a-real-key-0123456789"

    def client(self, script, cooldowns=None):
        self.transport = Transport(script)
        self.sleeps = []
        return Gemini(self.KEY, {} if cooldowns is None else cooldowns, self.NOW, transport=self.transport,
                      sleep=self.sleeps.append)

    def ask(self, gemini, models, **kwargs):
        return gemini.ask("market", models, "system", "prompt", time.time() + 60, **kwargs)

    def test_it_falls_back_when_a_model_is_busy(self):
        gemini = self.client({"a": [http_error(503, {"message": "The model is overloaded."})],
                              "b": [reply('{"regime": "neutral"}')]})
        self.assertEqual(self.ask(gemini, ["a", "b"]), ({"regime": "neutral"}, "b"))
        self.assertEqual([(c["model"], c["outcome"]) for c in gemini.log],
                         [("a", "HTTP 503: The model is overloaded."), ("b", "ok")])
        self.assertEqual(self.transport.calls[0][2]["x-goog-api-key"], self.KEY)
        self.assertEqual(gemini.cooldowns, {"a": self.NOW + 15 * MINUTE})

    def test_a_used_up_daily_quota_rests_the_model_until_it_resets(self):
        daily = {"message": "You exceeded your current quota.", "details": [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
             "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "20s"}]}
        cooldowns = {}
        gemini = self.client({"a": [http_error(429, daily)], "b": [reply('{"x": 1}'), reply('{"x": 2}')]}, cooldowns)
        self.assertEqual(self.ask(gemini, ["a", "b"]), ({"x": 1}, "b"))
        self.assertEqual(self.ask(gemini, ["a", "b"]), ({"x": 2}, "b"))
        self.assertEqual([c[0] for c in self.transport.calls], ["a", "b", "b"])
        self.assertEqual(self.sleeps, [])
        self.assertTrue(self.NOW < cooldowns["a"] <= self.NOW + DAY_MS)
        self.assertEqual(cooldowns["a"] % DAY_MS, QUOTA_RESET_UTC_MS)

    def test_a_per_minute_limit_waits_once_and_retries(self):
        minute = {"message": "Too many requests.", "details": [
            {"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}, {"retryDelay": "3s"}]}
        cooldowns = {}
        gemini = self.client({"a": [http_error(429, minute), reply('{"x": 1}')]}, cooldowns)
        self.assertEqual(self.ask(gemini, ["a"]), ({"x": 1}, "a"))
        self.assertEqual(self.sleeps, [4.0])
        self.assertEqual(cooldowns, {})

    def test_a_missing_model_rests_for_a_day(self):
        cooldowns = {}
        gemini = self.client({"a": [http_error(404, {"message": "models/a is not found"})], "b": [reply('{"x": 1}')]},
                             cooldowns)
        self.assertEqual(self.ask(gemini, ["a", "b"]), ({"x": 1}, "b"))
        self.assertEqual(cooldowns["a"], self.NOW + DAY_MS)

    def test_resting_models_are_skipped(self):
        gemini = self.client({}, {"a": self.NOW + 1})
        with self.assertRaises(LLMError) as caught:
            self.ask(gemini, ["a"])
        self.assertIn("resting", str(caught.exception))
        self.assertEqual(self.transport.calls, [])

    def test_it_retries_without_thinking_when_a_model_refuses_it(self):
        model = "gemini-3-flash-preview"
        gemini = self.client({model: [http_error(400, {"message": "Thinking level is not supported for this model."}),
                                      reply('{"x": 1}')]})
        self.assertEqual(self.ask(gemini, [model], thinking="medium"), ({"x": 1}, model))
        configs = [c[1]["generationConfig"] for c in self.transport.calls]
        self.assertEqual(configs[0]["thinkingConfig"], {"thinkingLevel": "medium"})
        self.assertNotIn("thinkingConfig", configs[1])
        gemini = self.client({"gemma-4-26b-a4b-it": [reply('{"x": 1}')]})
        self.ask(gemini, ["gemma-4-26b-a4b-it"])
        self.assertNotIn("thinkingConfig", self.transport.calls[0][1]["generationConfig"])

    def test_a_rejected_key_stops_at_once_and_is_never_shown(self):
        gemini = self.client({"a": [http_error(400, {"message": "API key not valid: %s" % self.KEY})], "b": [reply("{}")]})
        with self.assertRaises(KeyRejected) as caught:
            self.ask(gemini, ["a", "b"])
        self.assertNotIn(self.KEY, str(caught.exception))
        self.assertIn("[hidden]", str(caught.exception))
        self.assertEqual([c[0] for c in self.transport.calls], ["a"])
        gemini = self.client({"a": [http_error(403, {"message": "Permission denied."})]})
        self.assertRaises(KeyRejected, self.ask, gemini, ["a"])
        gemini = self.client({"a": [OSError("reset while sending key=%s" % self.KEY)], "b": [reply('{"x": 1}')]})
        self.assertEqual(self.ask(gemini, ["a", "b"]), ({"x": 1}, "b"))
        self.assertNotIn(self.KEY, json.dumps(gemini.log))

    def test_answers_are_read_as_json_and_checked(self):
        gemini = self.client({"a": [reply('```json\n{"regime": "risk-off"}\n```', thought='{"not": "this"}')]})
        self.assertEqual(self.ask(gemini, ["a"]), ({"regime": "risk-off"}, "a"))
        self.assertEqual(parse_json('Here it is: {"a": {"b": 1}} Thanks!'), {"a": {"b": 1}})
        for bad in ("[1, 2]", "", "no json here", "{broken"):
            self.assertRaises(LLMError, parse_json, bad)
        check = desk._answer_problem("manager")
        gemini = self.client({"a": [reply('{"minutes": "no plan"}')], "b": [reply('{"spot": [], "futures": {"side": "flat"}}')]})
        self.assertEqual(self.ask(gemini, ["a", "b"], check=check), ({"spot": [], "futures": {"side": "flat"}}, "b"))
        self.assertEqual(gemini.log[0]["outcome"], "the answer did not contain a plan for both books")
        gemini = self.client({"a": [{"candidates": []}], "b": [reply("   ")]})
        with self.assertRaises(LLMError) as caught:
            self.ask(gemini, ["a", "b"])
        self.assertIn("a: no answer", str(caught.exception))
        self.assertIn("b: empty answer", str(caught.exception))

    def test_it_needs_a_key(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "  "}):
            self.assertIsNone(Gemini.from_env({}, self.NOW))
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": self.KEY}):
            self.assertEqual(Gemini.from_env({}, self.NOW).key, self.KEY)


def stamp(now_ms, hours):
    return format_datetime(dt.datetime.fromtimestamp(now_ms / 1000.0 - hours * 3600, tz=dt.timezone.utc))


def rss(*items):
    body = "".join("<item><title>%s</title>%s</item>" % (title, "<pubDate>%s</pubDate>" % date if date else "")
                   for title, date in items)
    return ("<?xml version=\"1.0\"?><rss><channel>%s</channel></rss>" % body).encode("utf-8")


class ResearchTest(unittest.TestCase):
    NOW = START

    def test_headlines_are_recent_unique_and_newest_first(self):
        pages = {
            "CoinDesk": rss(("Bitcoin tops $150k", stamp(self.NOW, 2)), ("Old story", stamp(self.NOW, 30)), ("No date", None)),
            "Cointelegraph": rss(("bitcoin tops $150K", stamp(self.NOW, 1))),
            "Bitcoin Magazine": b"<html>not a feed",
            "CryptoSlate": rss(("Solana ETF approved", stamp(self.NOW, 0.5))),
        }
        urls = dict((url, name) for name, url in research.FEEDS)

        def fetch(url, data=None):
            name = urls[url]
            if name not in pages:
                raise OSError("offline")
            return pages[name]

        items, errors = research.headlines(self.NOW, fetch)
        self.assertEqual([(i["source"], i["title"], i["age_h"]) for i in items],
                         [("CryptoSlate", "Solana ETF approved", 0.5), ("Cointelegraph", "bitcoin tops $150K", 1.0)])
        self.assertEqual(errors, ["Decrypt news: OSError", "Bitcoin Magazine news: ParseError"])

    def test_futures_positioning_covers_renamed_coins(self):
        payload = json.dumps([
            {"universe": [{"name": "BTC"}, {"name": "kPEPE"}, {"name": "ETH"}]},
            [{"funding": "0.0000125", "openInterest": "1000", "markPx": "100000", "dayNtlVlm": "2500000000"},
             {"funding": "-0.00005", "openInterest": "5000000000", "markPx": "0.012", "dayNtlVlm": "90000000"},
             {"funding": "0.00001", "openInterest": "10", "markPx": "4000", "dayNtlVlm": "1"}]]).encode()
        out = research.derivatives(["BTC", "PEPE", "QNT"], fetch=lambda url, data=None: payload)
        self.assertEqual(sorted(out), ["BTC", "PEPE"])
        self.assertEqual(out["BTC"], {"funding_8h_pct": 0.01, "open_interest_usd_m": 100.0, "volume_24h_usd_m": 2500.0})
        self.assertEqual((out["PEPE"]["funding_8h_pct"], out["PEPE"]["open_interest_usd_m"]), (-0.04, 60.0))

    def test_every_source_is_optional(self):
        pages = {
            research.FEAR_GREED: {"data": [{"value": "71", "value_classification": "Greed"}, {"value": "64"}]},
            research.TRENDING: {"coins": [{"item": {"symbol": "sol"}}, {"item": {"symbol": "pepe"}}]},
            research.GLOBAL: {"data": {"market_cap_change_percentage_24h_usd": 1.8123, "market_cap_percentage": {"btc": 57.94}}},
        }

        def fetch(url, data=None):
            if url not in pages:
                raise OSError("offline")
            return json.dumps(pages[url]).encode()

        out = research.gather(["BTC"], self.NOW, fetch=fetch)
        self.assertEqual(out["fear_greed"], {"value": 71, "label": "Greed", "yesterday": 64})
        self.assertEqual(out["market"], {"trending": ["SOL", "PEPE"], "market_cap_change_24h": 1.81, "btc_dominance": 57.9})
        self.assertEqual((out["headlines"], out["derivatives"]), ([], {}))
        self.assertEqual(len(out["errors"]), len(research.FEEDS) + 1)

        def offline(url, data=None):
            raise OSError("offline")

        out = research.gather(["BTC"], self.NOW, fetch=offline)
        self.assertEqual((out["headlines"], out["fear_greed"], out["market"], out["derivatives"]), ([], None, None, {}))
        self.assertEqual(len(out["errors"]), len(research.FEEDS) + 3)


if __name__ == "__main__":
    unittest.main()
