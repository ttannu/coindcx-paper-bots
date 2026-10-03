"""Check paper spot orders against the last completed 15-minute candle's volume.

This is a warning screen, not an order-book fill model. In particular, a
strategy acting on a candle's close cannot know the depth available just after
that close. The screen catches fills for which the candle supplies no evidence
of enough trading at the quoted price.
"""

import csv
import datetime as dt
import math
import os


FIFTEEN_MIN_MS = 15 * 60 * 1000
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
BUCKETS = ("within_tenth", "over_tenth", "over_full", "zero", "unmatched")


def fresh(start_ms):
    return {"since_ms": start_ms, "initialized": False, "spot": _counts(), "bots": {}}


def _counts():
    return dict((key, 0) for key in BUCKETS)


def record(audit, bot, kind, order, market):
    """Count a simulated spot order once. ``market[pair]`` is (close time, INR volume)."""
    if kind != "spot" or order.get("side") not in ("BUY", "SELL"):
        return
    tape = market.get(order["pair"])
    value = float(order["value"])
    if not tape or tape[0] != order["t"] or not math.isfinite(value) or value < 0:
        bucket = "unmatched"
    else:
        volume = tape[1]
        if not math.isfinite(volume) or volume < 0:
            bucket = "unmatched"
        elif volume == 0:
            bucket = "zero"
        elif value > volume:
            bucket = "over_full"
        elif value > volume * 0.1:
            bucket = "over_tenth"
        else:
            bucket = "within_tenth"
    audit["spot"][bucket] += 1
    audit["bots"].setdefault(bot, _counts())[bucket] += 1


def backfill(audit, state_dir, series, accounts):
    """Audit trades saved before this screen was introduced, using the fetched candles.

    CoinDCX only returns about ten days of 15-minute candles. Older trades are
    marked unmatched rather than being assumed liquid.
    """
    if audit["initialized"]:
        return
    candles = {}
    for (pair, interval), data in series.items():
        if interval == "15m":
            for candle in data.candles:
                candles[pair, candle["t"] + FIFTEEN_MIN_MS] = candle["v"] * candle["c"]
    path = os.path.join(state_dir, "trades.csv")
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                bot = row["bot"]
                account = accounts.get(bot)
                if not account or account.get("kind") != "spot" or row["side"] not in ("BUY", "SELL"):
                    continue
                pair = "I-%s_INR" % row["pair"].split("/")[0]
                stamp = dt.datetime.strptime(row["time_ist"], "%Y-%m-%d %H:%M").replace(tzinfo=IST)
                t = int(stamp.timestamp() * 1000)
                volume = candles.get((pair, t))
                market = {pair: (t, volume)} if volume is not None else {}
                record(audit, bot, "spot", {"side": row["side"], "pair": pair, "t": t,
                                             "value": float(row["value"])}, market)
    audit["initialized"] = True


def total(counts):
    return sum(counts.get(key, 0) for key in BUCKETS)
