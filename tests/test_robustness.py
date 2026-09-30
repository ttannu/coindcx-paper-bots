import contextlib
import csv
import io
import json
import math
import os
import random
import shutil
import smtplib
import tempfile
import unittest
from unittest import mock

from sim import engine
from sim.bots import BTC, FIXED_BOTS, Bot
from sim.coindcx import DataUnavailable, parse_candles
from sim.learner import SelfLearner
from sim.mailer import to_html
from synthetic import DAY, H1, SCENARIOS, START, build_market, make_fetch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MINUTE = 60000

for _name in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "GEMINI_API_KEY"):
    os.environ.pop(_name, None)


TEST_UNIVERSE = ("I-DOGE_INR", "I-SOL_INR")


class Workspace:
    def __init__(self, universe=TEST_UNIVERSE):
        self.root = tempfile.mkdtemp(prefix="paperbots-")
        shutil.copy(os.path.join(ROOT, "README.md"), self.root)
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as fh:
            config = json.load(fh)
        config["universe"] = list(universe)
        with open(os.path.join(self.root, "config.json"), "w", encoding="utf-8") as fh:
            json.dump(config, fh)
        self.output = io.StringIO()

    def run(self, now, fetch, notify=True, **kwargs):
        with contextlib.redirect_stdout(self.output), contextlib.redirect_stderr(self.output):
            return engine.run(self.root, now, start_ms=START, notify=notify, fetch=fetch, **kwargs)

    def state(self):
        with open(os.path.join(self.root, "state", "state.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class FakeGitHub:
    def __init__(self):
        self.calls = []
        self.failing = set()

    def _record(self, name, *args):
        self.calls.append((name,) + args)
        if name in self.failing:
            raise OSError("GitHub is down")

    def create_issue(self, title, body):
        self._record("create_issue", title)
        return 7

    def comment(self, number, body):
        self._record("comment", number, body.splitlines()[0])

    def close_issue(self, number, title):
        self._record("close_issue", number, title)

    def disable_workflow(self, file_name):
        self._record("disable_workflow", file_name)


class FakeMailer:
    def __init__(self):
        self.sent = []
        self.attempts = 0
        self.error = None

    def send(self, subject, markdown):
        self.attempts += 1
        if self.error:
            raise self.error
        self.sent.append((subject, markdown))


class Exploding(Bot):
    key = "exploding"
    title = "Exploding"
    subscriptions = ((BTC, "15m"),)

    def on_candle(self, ctx, s, i):
        self.acct.memo["n"] = self.acct.memo.get("n", 0) + 1
        if self.acct.memo["n"] == 10:
            raise RuntimeError("boom")


def check_invariants(test, state):
    for key, b in state["bots"].items():
        test.assertNotEqual(b["status"], "error", "%s: %s" % (key, b.get("error")))
        test.assertTrue(math.isfinite(b["last_value"]), (key, b["last_value"]))
        test.assertGreaterEqual(b["last_value"] + b["tax_due"], -1e-6, key)
        test.assertGreaterEqual(b["cash"], -1e-6, key)
        test.assertGreaterEqual(b["spread"], 0.0, key)
        for pos in b.get("positions", {}).values():
            test.assertGreater(pos["qty"], 0, key)
        if key == SelfLearner.key or key.endswith(".learner"):
            test.assertEqual(b["liquidations"], 0, key)
            if b["position"]:
                test.assertLessEqual(b["position"]["leverage"], 1, key)
            test.assertGreater(b["last_value"], 0.8 * b["capital"], key)


class ScenarioTest(unittest.TestCase):
    def test_full_fifteen_days_in_every_scenario(self):
        for n, scenario in enumerate(SCENARIOS):
            with self.subTest(scenario=scenario):
                rng = random.Random(n)
                fetch = make_fetch(build_market(scenario, seed=n), garbage=scenario == "gaps")
                ws = Workspace()
                try:
                    now = START + 7 * MINUTE
                    while True:
                        ws.run(now, fetch)
                        state = ws.state()
                        check_invariants(self, state)
                        if state["finished"]:
                            break
                        now += rng.choice((30 * MINUTE, 2 * H1, 5 * H1, 9 * H1, 20 * H1))
                    self.assertTrue(state["reports"]["final_posted"])
                    self.assertIn("Final results", ws.output.getvalue())
                    learner = state["bots"][SelfLearner.key]
                    self.assertLess(learner["max_dd"], 0.5, scenario)
                    with open(os.path.join(ws.root, "state", "equity.csv"), encoding="utf-8") as fh:
                        times = [int(r["t_ms"]) for r in csv.DictReader(fh)]
                    self.assertEqual(times, sorted(times))
                    self.assertTrue(os.path.exists(os.path.join(ws.root, "docs", "equity.svg")))
                    print("  %-10s %s" % (scenario, "  ".join(
                        "%s %.0f" % (k, b["last_value"]) for k, b in sorted(state["bots"].items()) if "." not in k)))
                finally:
                    ws.close()


class ReplayTest(unittest.TestCase):
    def test_split_runs_match_one_long_run(self):
        fetch = make_fetch(build_market("chop", seed=42))
        end = START + 3 * DAY + 7 * MINUTE
        split, whole = Workspace(), Workspace()
        try:
            rng = random.Random(1)
            now = START + 7 * MINUTE
            while now < end:
                split.run(now, fetch, notify=False)
                now += rng.choice((30 * MINUTE, 2 * H1, 5 * H1))
            split.run(end, fetch, notify=False)
            whole.run(end, fetch, notify=False)
            a, b = split.state()["bots"], whole.state()["bots"]
            for key in a:
                for field in ("cash", "trades", "fees", "tax_due", "last_value"):
                    self.assertAlmostEqual(a[key][field], b[key][field], places=6, msg="%s %s" % (key, field))
            self.assertEqual(a[SelfLearner.key]["memo"]["leader"], b[SelfLearner.key]["memo"]["leader"])
        finally:
            split.close()
            whole.close()

    def test_a_repeat_run_processes_nothing(self):
        fetch = make_fetch(build_market("calm", seed=3))
        ws = Workspace()
        try:
            ws.run(START + DAY, fetch, notify=False)
            before = ws.state()
            ws.run(START + DAY, fetch, notify=False)
            after = ws.state()
            self.assertEqual(before["bots"], after["bots"])
            self.assertEqual(before["cursor"], after["cursor"])
        finally:
            ws.close()


class FaultTest(unittest.TestCase):
    def test_a_broken_bot_is_isolated(self):
        fetch = make_fetch(build_market("calm", seed=5))
        ws = Workspace()
        try:
            with mock.patch.object(engine, "ALL_BOTS", FIXED_BOTS + (Exploding, SelfLearner)):
                ws.run(START + DAY, fetch, notify=False)
            state = ws.state()
            self.assertEqual(state["bots"]["exploding"]["status"], "error")
            self.assertIn("boom", state["bots"]["exploding"]["error"])
            for key, b in state["bots"].items():
                if key != "exploding":
                    self.assertIn(b["status"], ("active", "busted") if "." in key else ("active",), key)
            with open(os.path.join(ws.root, "README.md"), encoding="utf-8") as fh:
                self.assertIn("stopped by an error", fh.read())
        finally:
            ws.close()

    def test_a_data_outage_changes_nothing(self):
        market = build_market("calm", seed=6)
        fetch = make_fetch(market)
        ws = Workspace()
        try:
            ws.run(START + DAY, fetch, notify=False)
            path = os.path.join(ws.root, "state", "state.json")
            with open(path, "rb") as fh:
                before = fh.read()

            def broken(pair, interval, now_ms):
                if pair != BTC:
                    raise DataUnavailable("CoinDCX is down")
                return fetch(pair, interval, now_ms)

            with self.assertRaises(DataUnavailable):
                ws.run(START + 2 * DAY, broken, notify=False)
            with open(path, "rb") as fh:
                self.assertEqual(before, fh.read())
            ws.run(START + 2 * DAY, fetch, notify=False)
            check_invariants(self, ws.state())
        finally:
            ws.close()

    def test_bad_candles_are_dropped(self):
        rows = [
            {"time": 2000, "open": 10, "high": 9, "low": 11, "close": 10.5, "volume": 1},
            {"time": 1000, "open": 10, "high": 12, "low": 9, "close": 11, "volume": None},
            {"time": 3000, "open": 0, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": "later", "open": 1},
            None,
            {"time": 1000, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1},
        ]
        candles = parse_candles(rows)
        self.assertEqual([c["t"] for c in candles], [1000, 2000])
        self.assertEqual((candles[1]["h"], candles[1]["l"]), (11, 9))
        with self.assertRaises(ValueError):
            parse_candles({"message": "rate limited"})


class NotificationTest(unittest.TestCase):
    def test_reports_retry_until_they_succeed_and_never_repeat(self):
        fetch = make_fetch(build_market("calm", seed=8))
        github = FakeGitHub()
        ws = Workspace()
        try:
            with mock.patch.object(engine.GitHub, "from_env", return_value=github):
                github.failing = {"create_issue"}
                ws.run(START + 7 * MINUTE, fetch)
                self.assertIsNone(ws.state()["reports"]["issue"])

                github.failing = set()
                ws.run(START + 37 * MINUTE, fetch)
                self.assertEqual(ws.state()["reports"]["issue"], 7)

                first_morning = (START // DAY + 1) * DAY + 4 * H1
                ws.run(first_morning, fetch)
                ws.run(first_morning + H1, fetch)
                daily = [c for c in github.calls if c[0] == "comment"]
                self.assertEqual(len(daily), 1)
                self.assertIn("Day 1 of 15", daily[0][2])

                end = ws.state()["sim_end"] + 3 * H1
                github.failing = {"close_issue"}
                ws.run(end, fetch)
                reports = ws.state()["reports"]
                self.assertTrue(reports["final_posted"])
                self.assertFalse(reports.get("issue_closed"))

                github.failing = set()
                ws.run(end + 30 * MINUTE, fetch)
                ws.run(end + H1, fetch)
                names = [c[0] for c in github.calls]
                self.assertEqual(sum(1 for c in github.calls if c[0] == "comment" and "Final results" in c[2]), 1)
                self.assertEqual(names.count("disable_workflow"), 1)
                self.assertEqual(names[-1], "disable_workflow")
                self.assertIn("already finished", ws.output.getvalue())
        finally:
            ws.close()


class MailTest(unittest.TestCase):
    def test_emails_catch_up_without_flooding_and_back_off_on_a_bad_password(self):
        fetch = make_fetch(build_market("calm", seed=9))
        github, mailer = FakeGitHub(), FakeMailer()
        morning = lambda day: (START // DAY + day) * DAY + 4 * H1
        ws = Workspace()
        try:
            with mock.patch.object(engine.GitHub, "from_env", return_value=github):
                ws.run(START + 7 * MINUTE, fetch)
                for day in (1, 2, 3):
                    ws.run(morning(day), fetch)
                outbox = ws.state()["reports"]["outbox"]
                self.assertEqual([m["kind"] for m in outbox], ["daily"])
                self.assertTrue(outbox[0]["body"].startswith("**Day 3 of 15**"))

                with mock.patch.object(engine.Mailer, "from_env", return_value=mailer):
                    mailer.error = smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
                    ws.run(morning(3) + H1, fetch)
                    ws.run(morning(3) + 2 * H1, fetch)
                    self.assertEqual(mailer.attempts, 1)

                    mailer.error = None
                    ws.run(morning(3) + 7 * H1, fetch)
                    self.assertEqual([s for s, _ in mailer.sent], [
                        "Paper-trading bots: email reports are on",
                        mailer.sent[1][0],
                    ])
                    self.assertIn("day 3 of 15", mailer.sent[1][0])
                    self.assertIn("Top 10 at", mailer.sent[0][1])
                    ws.run(morning(3) + 8 * H1, fetch)
                    ws.run(morning(4), fetch)
                    self.assertEqual(len(mailer.sent), 3)
                    self.assertEqual(ws.state()["reports"]["outbox"], [])

                    end = ws.state()["sim_end"] + 3 * H1
                    mailer.error = OSError("network is unreachable")
                    ws.run(end, fetch)
                    self.assertTrue(ws.state()["reports"]["final_posted"])
                    self.assertNotIn("disable_workflow", [c[0] for c in github.calls])

                    mailer.error = None
                    ws.run(end + 30 * MINUTE, fetch)
                    ws.run(end + H1, fetch)
                    self.assertEqual(mailer.sent[-1][0], "Paper-trading bots: final results")
                    self.assertEqual(sum(1 for s, _ in mailer.sent if "final" in s), 1)
                    self.assertEqual([c[0] for c in github.calls].count("disable_workflow"), 1)
                    self.assertIn("already finished", ws.output.getvalue())
        finally:
            ws.close()

    def test_a_mail_outage_cannot_keep_the_workflow_alive(self):
        fetch = make_fetch(build_market("calm", seed=10))
        github, mailer = FakeGitHub(), FakeMailer()
        mailer.error = OSError("smtp.gmail.com is unreachable")
        ws = Workspace()
        try:
            with mock.patch.object(engine.GitHub, "from_env", return_value=github), \
                    mock.patch.object(engine.Mailer, "from_env", return_value=mailer):
                ws.run(START + 7 * MINUTE, fetch)
                end = ws.state()["sim_end"]
                ws.run(end + 3 * H1, fetch)
                self.assertFalse(ws.state()["reports"].get("workflow_disabled"))
                ws.run(end + DAY + H1, fetch)
                self.assertTrue(ws.state()["reports"]["workflow_disabled"])
        finally:
            ws.close()

    def test_a_bug_in_reporting_still_saves_the_results(self):
        fetch = make_fetch(build_market("calm", seed=11))
        mailer = FakeMailer()
        mailer.error = TypeError("unexpected bug")
        ws = Workspace()
        try:
            with mock.patch.object(engine.GitHub, "from_env", return_value=FakeGitHub()), \
                    mock.patch.object(engine.Mailer, "from_env", return_value=mailer), \
                    mock.patch.object(engine.report, "daily_message", side_effect=RuntimeError("template bug")):
                ws.run(START + 7 * MINUTE, fetch)
                ws.run(START + DAY, fetch)
            state = ws.state()
            self.assertEqual(state["runs"], 2)
            self.assertEqual(state["reports"]["issue"], 7)
            self.assertIn("unexpected bug", ws.output.getvalue())
            self.assertIn("template bug", ws.output.getvalue())
        finally:
            ws.close()

    def test_html_rendering(self):
        page = to_html("**Day 2 of 15**, <b>\n\n| # | Bot |\n|---|---|\n| 1 | Hold |\n\n- one\nhttps://github.com/x/y")
        self.assertIn("<b>Day 2 of 15</b>, &lt;b&gt;", page)
        self.assertEqual(page.count("<tr>"), 2)
        self.assertIn("<th", page)
        self.assertIn("&bull; one", page)
        self.assertIn('<a href="https://github.com/x/y">', page)
        self.assertNotIn("**", page)


if __name__ == "__main__":
    unittest.main()
