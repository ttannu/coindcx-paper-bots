import math
import random

from sim.coindcx import INTERVAL_MS, parse_candles

M15, H1, DAY = 900000, 3600000, 86400000
START = 1790000000000 // H1 * H1
HISTORY_15M = 4100
SIM_15M = 15 * 96 + 32
BASE = {"I-BTC_INR": 8.5e6, "I-ETH_INR": 2.7e5, "I-SOL_INR": 1.2e4, "I-XRP_INR": 150.0, "I-DOGE_INR": 9.75}
SCENARIOS = ("calm", "bull", "bear", "chop", "crash", "pump_dump", "flash", "collapse", "gaps")


def _hourly(rows):
    out = []
    for row in rows:
        hour = row["t"] // H1 * H1
        if out and out[-1]["t"] == hour:
            last = out[-1]
            last["h"] = max(last["h"], row["h"])
            last["l"] = min(last["l"], row["l"])
            last["c"] = row["c"]
            last["v"] += row["v"]
        else:
            out.append({"t": hour, "o": row["o"], "h": row["h"], "l": row["l"], "c": row["c"], "v": row["v"]})
    return out


def build_market(scenario, seed, pairs=()):
    rng = random.Random(seed)
    market = {}
    prices = dict(BASE)
    for pair in pairs:
        prices.setdefault(pair, 100.0)
    for pair, price in prices.items():
        rows = []
        for k in range(-HISTORY_15M, SIM_15M):
            day = k / 96.0
            drift, vol = 0.0, 0.004
            if scenario == "bull":
                drift = 0.0004
            elif scenario == "bear":
                drift = -0.0004
            elif scenario == "chop":
                vol = 0.012
            elif scenario == "crash" and 5 <= day < 5 + 1 / 3.0:
                drift = -0.02
            elif scenario == "pump_dump" and 3 <= day < 3.5:
                drift = 0.012
            elif scenario == "pump_dump" and 3.5 <= day < 4:
                drift = -0.015
            elif scenario == "collapse" and pair == "I-DOGE_INR" and day >= 0:
                drift = -0.002
            close = price * math.exp(drift + vol * rng.gauss(0, 1))
            high = max(price, close) * (1 + abs(rng.gauss(0, vol / 2)))
            low = min(price, close) * (1 - abs(rng.gauss(0, vol / 2)))
            if scenario == "flash" and k == 400:
                low = min(price, close) * 0.55
            if scenario == "flash" and k == 900:
                high = max(price, close) * 1.6
            rows.append({"t": START + k * M15, "o": price, "h": high, "l": low, "c": close, "v": 1.0})
            price = close
        if scenario == "gaps":
            rows = [r for r in rows if rng.random() > 0.05]
        market[(pair, "15m")] = rows
        market[(pair, "1h")] = _hourly(rows)
    return market


def make_fetch(market, garbage=False):
    def fetch(pair, interval, now_ms):
        rows = [r for r in market[(pair, interval)] if r["t"] <= now_ms][-1000:]
        api = [{"time": r["t"], "open": r["o"], "high": r["h"], "low": r["l"], "close": r["c"], "volume": r["v"]}
               for r in reversed(rows)]
        if garbage and api:
            api.insert(1, {"time": "soon", "open": None})
            api.insert(2, {"time": api[0]["time"], "open": -1, "high": 0, "low": 0, "close": "nan"})
            api.append(dict(api[-1]))
            api.append("not a candle")
        span = INTERVAL_MS[interval]
        return [c for c in parse_candles(api) if c["t"] + span <= now_ms]
    return fetch
