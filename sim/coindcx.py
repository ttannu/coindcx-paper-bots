import http.client
import json
import math
import time
import urllib.parse
import urllib.request

CANDLES_URL = "https://public.coindcx.com/market_data/candles"
INTERVAL_MS = {"15m": 15 * 60 * 1000, "1h": 60 * 60 * 1000}


class DataUnavailable(Exception):
    pass


def parse_candles(rows):
    if not isinstance(rows, list):
        raise ValueError("expected a list of candles, got %.200r" % (rows,))
    by_time = {}
    for row in rows:
        try:
            t = int(row["time"])
            o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
            v = float(row.get("volume") or 0)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if not all(math.isfinite(p) and p > 0 for p in (o, h, l, c)):
            continue
        by_time[t] = {"t": t, "o": o, "h": max(o, h, l, c), "l": min(o, h, l, c), "c": c, "v": v}
    return [by_time[t] for t in sorted(by_time)]


def fetch_candles(pair, interval, limit=1000, retries=4):
    url = CANDLES_URL + "?" + urllib.parse.urlencode({"pair": pair, "interval": interval, "limit": limit})
    request = urllib.request.Request(url, headers={"User-Agent": "coindcx-paper-bots"})
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return parse_candles(json.load(response))
        except (OSError, ValueError, http.client.HTTPException) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(3 * 2 ** attempt)
    raise DataUnavailable("%s %s: %s" % (pair, interval, last_error))


def closed_candles(pair, interval, now_ms):
    span = INTERVAL_MS[interval]
    return [c for c in fetch_candles(pair, interval) if c["t"] + span <= now_ms]
