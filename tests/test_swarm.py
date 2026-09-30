import csv
import json
import os
import time
import unittest
from unittest import mock

import test_desk
import test_robustness as rb
from sim import desk, engine, liquid, report, swarm
from sim.coindcx import DataUnavailable
from synthetic import DAY, H1, START, build_market, make_fetch

MINUTE = 60000
SOL = "I-SOL_INR"


def read_config():
    with open(os.path.join(rb.ROOT, "config.json"), encoding="utf-8") as fh:
        return json.load(fh)


def equity_times(ws):
    with open(os.path.join(ws.root, "state", "equity.csv"), newline="", encoding="utf-8") as fh:
        return [int(row["t_ms"]) for row in csv.DictReader(fh)]


class SwarmTest(unittest.TestCase):
    def test_every_coin_gets_every_strategy_once(self):
        config = read_config()
        universe = config["universe"]
        for pair in universe:
            self.assertIn(pair, config["markets"])
        bots = engine._build_bots({"bots": {}}, config, [])
        keys = [bot.key for bot in bots]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(bots), len(engine.ALL_BOTS) + len(liquid.specs(universe)) + len(universe) * len(swarm.FAMILIES) +
                         len(desk.BOOKS))
        self.assertGreaterEqual(len(bots), 1000)
        for bot in bots:
            if getattr(bot, "family", None):
                self.assertEqual(bot.acct.kind, bot.family.kind, bot.key)
                self.assertEqual(set(pair for pair, _ in bot.subscriptions), {bot.pair}, bot.key)

    def test_coin_flips_are_fixed_and_fair(self):
        self.assertEqual(swarm.draw("btc.flip_1", 123), swarm.draw("btc.flip_1", 123))
        self.assertNotEqual(swarm.draw("btc.flip_1", 123), swarm.draw("btc.flip_2", 123))
        draws = [swarm.draw("x", t) for t in range(20000)]
        self.assertAlmostEqual(sum(draws) / len(draws), 0.5, delta=0.01)
        self.assertAlmostEqual(sum(d < swarm.FLIP_ODDS for d in draws) / float(len(draws)), swarm.FLIP_ODDS, delta=0.01)


class ScaleTest(unittest.TestCase):
    def test_the_full_universe_runs_quickly_and_stays_small(self):
        universe = read_config()["universe"]
        fetch = make_fetch(build_market("chop", seed=21, pairs=universe))
        ws = rb.Workspace(universe=universe)
        try:
            now = START + DAY + 7 * MINUTE
            fake = test_desk.FakeLLM()
            began = time.time()
            ws.run(now, fetch, notify=False, desk_llm=fake, gather=test_desk.news)
            first = time.time() - began
            self.assertEqual(len(ws.state()["desk"]["decisions"]), 1)
            self.assertIn("\nSIREN|", fake.prompts["market"][1])
            sizes = dict((role, len(system) + len(prompt)) for role, (system, prompt, _) in fake.prompts.items())
            self.assertLess(max(sizes.values()), 24000, sizes)
            timings = []
            for _ in range(3):
                now += 30 * MINUTE
                began = time.time()
                ws.run(now, fetch, notify=False)
                timings.append(time.time() - began)
            state = ws.state()
            self.assertEqual(len(state["bots"]), len(engine.ALL_BOTS) + 2 + 22 * len(universe) + len(desk.BOOKS))
            self.assertEqual(len(state["bots"][liquid.LiquidBasket.key]["positions"]), 5)
            rb.check_invariants(self, state)
            self.assertLess(max(timings), 20, timings)
            self.assertLess(os.path.getsize(os.path.join(ws.root, "state", "state.json")), 4000000)
            self.assertLess(os.path.getsize(os.path.join(ws.root, "README.md")), 60000)
            times = equity_times(ws)
            self.assertEqual(times, sorted(set(times)))
            print("\n  %d bots: a 30-minute run takes %.1fs, state.json is %.1f MB; the first day with a desk meeting took "
                  "%.1fs, and its largest prompt (%s) is %d characters" % (
                      len(state["bots"]), max(timings), os.path.getsize(os.path.join(ws.root, "state", "state.json")) / 1e6,
                      first, max(sizes, key=sizes.get), max(sizes.values())))
        finally:
            ws.close()


class CoinOutageTest(unittest.TestCase):
    def test_a_coin_that_misses_some_runs_catches_up_exactly(self):
        fetch = make_fetch(build_market("chop", seed=22))
        down = {"on": False}

        def flaky(pair, interval, now_ms):
            if down["on"] and pair == SOL:
                raise DataUnavailable("SOL is not responding")
            return fetch(pair, interval, now_ms)

        ws, ref = rb.Workspace(), rb.Workspace()
        try:
            now = START + DAY + 7 * MINUTE
            ws.run(now, flaky, notify=False)
            ref.run(now, fetch, notify=False)
            down["on"] = True
            for _ in range(8):
                now += 30 * MINUTE
                ws.run(now, flaky, notify=False)
                ref.run(now, fetch, notify=False)
            self.assertIn(SOL + "|15m", ws.state()["data_gaps"])
            down["on"] = False
            now += 30 * MINUTE
            ws.run(now, flaky, notify=False)
            ref.run(now, fetch, notify=False)
            a, b = ws.state(), ref.state()
            self.assertEqual(a["data_gaps"], {})
            self.assertEqual(a["cursor"], b["cursor"])
            for key in a["bots"]:
                # The learner acts on the clock, which never replays; everything else acts on candles alone.
                if key.startswith("sol.") and key != "sol.learner":
                    for field in ("cash", "trades", "fees", "tax_due"):
                        self.assertAlmostEqual(a["bots"][key][field], b["bots"][key][field], places=6, msg="%s %s" % (key, field))
            times = equity_times(ws)
            self.assertEqual(times, sorted(set(times)))
            rb.check_invariants(self, a)
        finally:
            ws.close()
            ref.close()

    def test_a_coin_that_goes_silent_is_frozen_after_twelve_hours(self):
        fetch = make_fetch(build_market("calm", seed=23))

        def delisted(pair, interval, now_ms):
            if pair == SOL and now_ms > START + DAY:
                raise DataUnavailable("SOL was delisted")
            return fetch(pair, interval, now_ms)

        ws = rb.Workspace()
        try:
            ws.run(START + DAY, delisted, notify=False)
            for hours in (6, 12, 17):
                ws.run(START + DAY + hours * H1, delisted, notify=False)
            self.assertEqual(ws.state()["bots"]["sol.trend_6_24h"]["status"], "active")
            ws.run(START + DAY + 19 * H1, delisted, notify=False)
            state = ws.state()
            for key, b in state["bots"].items():
                if key.startswith("sol."):
                    self.assertEqual(b["status"], "no data", key)
                    self.assertIn("SOL", b["error"])
                else:
                    self.assertIn(b["status"], ("active", "busted"), key)
            self.assertEqual(state["bots"]["trend_ema"]["status"], "active")
            rb.check_invariants(self, state)
        finally:
            ws.close()


class NewCoinTest(unittest.TestCase):
    def test_a_coin_added_mid_run_gets_its_own_columns_and_history(self):
        fetch = make_fetch(build_market("bull", seed=26))
        ws = rb.Workspace(universe=("I-DOGE_INR",))
        try:
            ws.run(START + DAY, fetch, notify=False)
            path = os.path.join(ws.root, "config.json")
            with open(path, encoding="utf-8") as fh:
                config = json.load(fh)
            config["universe"].append("I-XRP_INR")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(config, fh)
            ws.run(START + 2 * DAY, fetch, notify=False)
            state = ws.state()
            self.assertGreater(state["bots"]["xrp.hold"]["trades"] + len(state["bots"]["xrp.hold"]["positions"]), 0)
            with open(os.path.join(ws.root, "state", "equity.csv"), newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertIn("xrp.hold", rows[0])
            self.assertEqual(rows[0]["xrp.hold"], "")
            self.assertNotEqual(rows[-1]["xrp.hold"], "")
            self.assertNotEqual(rows[0]["doge.hold"], "")
            times = [int(r["t_ms"]) for r in rows]
            self.assertEqual(times, sorted(set(times)))
            rb.check_invariants(self, state)
        finally:
            ws.close()


class UpgradeTest(unittest.TestCase):
    def test_a_version_1_state_is_replayed_from_its_original_start(self):
        fetch = make_fetch(build_market("calm", seed=24))
        github, mailer = rb.FakeGitHub(), rb.FakeMailer()
        old, fresh = rb.Workspace(), rb.Workspace()
        try:
            with mock.patch.object(engine.GitHub, "from_env", return_value=github), \
                    mock.patch.object(engine.Mailer, "from_env", return_value=mailer):
                old.run(START + 7 * MINUTE, fetch)
                old.run(START + 12 * H1, fetch)
                state = old.state()
                state["version"] = 1
                state["bots"] = dict((k, v) for k, v in state["bots"].items() if "." not in k)
                for k in ("last_tick_t", "data_gaps"):
                    del state[k]
                with open(os.path.join(old.root, "state", "state.json"), "w", encoding="utf-8") as fh:
                    json.dump(state, fh)
                with open(os.path.join(old.root, "state", "equity.csv"), "w", encoding="utf-8") as fh:
                    fh.write("t_ms,time_ist,bot,value\n%d,x,hodl_btc,5000.00\n" % (START + H1))

                def down(pair, interval, now_ms):
                    raise DataUnavailable("CoinDCX is down")

                with self.assertRaises(DataUnavailable):
                    old.run(START + DAY, down)
                self.assertEqual(old.state()["version"], 1)
                for name in ("equity.csv", "trades.csv"):
                    self.assertTrue(os.path.exists(os.path.join(old.root, "state", name)), name)
                old.run(START + DAY, fetch)
                old.run(START + DAY + H1, fetch)
            fresh.run(START + DAY + H1, fetch, notify=False)
            a, b = old.state(), fresh.state()
            self.assertEqual(a["version"], engine.STATE_VERSION)
            self.assertEqual(a["sim_start"], START)
            self.assertEqual(a["reports"]["issue"], 7)
            self.assertTrue(a["reports"]["mail_welcomed"])
            self.assertEqual(sorted(a["bots"]), sorted(b["bots"]))
            for key in a["bots"]:
                for field in ("cash", "trades", "fees", "last_value"):
                    self.assertAlmostEqual(a["bots"][key][field], b["bots"][key][field], places=6, msg="%s %s" % (key, field))
            upgrades = [c for c in github.calls if c[0] == "comment" and "upgraded" in c[2]]
            self.assertEqual(len(upgrades), 1)
            self.assertEqual(sum(1 for s, _ in mailer.sent if s.startswith("Paper-trading bots: now")), 1)
            for name in ("equity.csv", "trades.csv"):
                with open(os.path.join(old.root, "state", name), encoding="utf-8") as fh_a, \
                        open(os.path.join(fresh.root, "state", name), encoding="utf-8") as fh_b:
                    self.assertEqual(fh_a.read(), fh_b.read(), name)
        finally:
            old.close()
            fresh.close()


class ReportTest(unittest.TestCase):
    def test_the_dashboard_summarises_the_swarm(self):
        fetch = make_fetch(build_market("chop", seed=25))
        ws = rb.Workspace()
        try:
            ws.run(START + 3 * DAY, fetch, notify=False)
            with open(os.path.join(ws.root, "README.md"), encoding="utf-8") as fh:
                readme = fh.read()
            block = readme[readme.index(report.START_MARK):readme.index(report.END_MARK)]
            top = block.split("**Top 15 bots**")[1].split("**The original bots**")[0]
            self.assertEqual(sum(1 for line in top.splitlines() if line[:2] == "| " and line[2].isdigit()), 15)
            card = block.split("**Strategy report card.**")[1].split("How much of this is luck?")[0]
            rows = [line for line in card.splitlines() if line[:2] == "| " and not line.startswith("| Strategy")]
            self.assertEqual(len(rows), len(swarm.FAMILIES))
            self.assertEqual(sum(1 for line in rows if "luck control" in line), 4)
            with open(os.path.join(ws.root, "docs", "equity.svg"), encoding="utf-8") as fh:
                svg = fh.read()
            self.assertIn(svg.count("<polyline"), range(7, 10))
            self.assertIn("Median of all %d bots" % len(ws.state()["bots"]), svg)
            self.assertIn("AI desk: spot portfolio", svg)
            self.assertIn("AI desk: futures, up to 3x", svg)
            self.assertLess(block.index("**AI trading desk.**"), block.index("**Top 15 bots**"))
            originals = block.split("**The original bots**")[1].split("**Strategy report card.**")[0]
            self.assertNotIn("AI desk", originals)
        finally:
            ws.close()


if __name__ == "__main__":
    unittest.main()
