import datetime as dt
import http.client
import json
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime

UA = {"User-Agent": "Mozilla/5.0 (compatible; coindcx-paper-bots; +https://github.com/ttannu/coindcx-paper-bots)"}
FEEDS = (
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
    ("CryptoSlate", "https://cryptoslate.com/feed/"),
)
FEAR_GREED = "https://api.alternative.me/fng/?limit=2"
TRENDING = "https://api.coingecko.com/api/v3/search/trending"
GLOBAL = "https://api.coingecko.com/api/v3/global"
HYPERLIQUID = "https://api.hyperliquid.xyz/info"
# Hyperliquid quotes these per 1,000 coins.
PERP_ALIASES = {"BONK": "kBONK", "PEPE": "kPEPE", "SHIB": "kSHIB"}
TIMEOUT = 15
MAX_HEADLINES = 40
MAX_AGE_H = 24
NETWORK_ERRORS = (OSError, ValueError, KeyError, TypeError, IndexError, ET.ParseError, http.client.HTTPException)


def _get(url, data=None):
    headers = dict(UA)
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def parse_feed(source, raw, now_ms):
    out = []
    for item in ET.fromstring(raw).iter("item"):
        title = " ".join((item.findtext("title") or "").split())
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
            age_h = (now_ms / 1000.0 - published.timestamp()) / 3600.0
        except (TypeError, ValueError, IndexError):
            continue
        if title and -1 <= age_h <= MAX_AGE_H:
            out.append({"source": source, "title": title[:180], "age_h": round(max(age_h, 0.0), 1)})
    return out


def headlines(now_ms, fetch=_get):
    items, errors = [], []

    def one(feed):
        return parse_feed(feed[0], fetch(feed[1]), now_ms)

    with ThreadPoolExecutor(max_workers=len(FEEDS)) as pool:
        jobs = [(feed[0], pool.submit(one, feed)) for feed in FEEDS]
        for name, job in jobs:
            try:
                items += job.result()
            except NETWORK_ERRORS as exc:
                errors.append("%s news: %s" % (name, type(exc).__name__))
    seen, unique = set(), []
    for item in sorted(items, key=lambda i: i["age_h"]):
        key = item["title"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:MAX_HEADLINES], errors


def fear_greed(fetch=_get):
    data = json.loads(fetch(FEAR_GREED))["data"]
    return {"value": int(data[0]["value"]), "label": data[0]["value_classification"],
            "yesterday": int(data[1]["value"]) if len(data) > 1 else None}


def coingecko(fetch=_get):
    trending = [c["item"]["symbol"].upper() for c in json.loads(fetch(TRENDING)).get("coins", [])]
    market = json.loads(fetch(GLOBAL))["data"]
    return {"trending": trending[:15],
            "market_cap_change_24h": round(float(market["market_cap_change_percentage_24h_usd"]), 2),
            "btc_dominance": round(float(market["market_cap_percentage"]["btc"]), 1)}


def derivatives(coins, fetch=_get):
    meta, contexts = json.loads(fetch(HYPERLIQUID, {"type": "metaAndAssetCtxs"}))
    index = dict((asset["name"], n) for n, asset in enumerate(meta["universe"]))
    out = {}
    for coin in coins:
        n = index.get(PERP_ALIASES.get(coin, coin))
        if n is None:
            continue
        ctx = contexts[n]
        mark = float(ctx["markPx"])
        out[coin] = {"funding_8h_pct": round(float(ctx["funding"]) * 8 * 100, 4),
                     "open_interest_usd_m": round(float(ctx["openInterest"]) * mark / 1e6, 1),
                     "volume_24h_usd_m": round(float(ctx["dayNtlVlm"]) / 1e6, 1)}
    return out


def gather(coins, now_ms, fetch=_get):
    """Everything the analysts read besides CoinDCX prices. Each source is optional: a failure is noted and skipped."""
    out = {"headlines": [], "fear_greed": None, "market": None, "derivatives": {}, "errors": []}
    with ThreadPoolExecutor(max_workers=4) as pool:
        news = pool.submit(headlines, now_ms, fetch)
        jobs = {"fear_greed": pool.submit(fear_greed, fetch), "market": pool.submit(coingecko, fetch),
                "derivatives": pool.submit(derivatives, coins, fetch)}
        try:
            out["headlines"], errors = news.result()
            out["errors"] += errors
        except NETWORK_ERRORS as exc:
            out["errors"].append("news: %s" % type(exc).__name__)
        for name, job in jobs.items():
            try:
                out[name] = job.result()
            except NETWORK_ERRORS as exc:
                out["errors"].append("%s: %s" % (name.replace("_", " "), type(exc).__name__))
    return out
