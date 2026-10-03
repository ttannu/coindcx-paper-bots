"""Read-only, optimistic triangular-arbitrage screen for one CoinDCX snapshot.

For each coin, compare INR -> coin -> USDT -> INR and the reverse route. Only
the best displayed bid/ask is used, with no depth, rounding, latency or hedge
risk. Therefore a negative gross return rules out a profitable market-order
cycle at that snapshot; a positive result is only a lead for deeper research.
No authenticated endpoint is called and this script cannot place orders.
"""

import argparse
import concurrent.futures
import datetime as dt
import json
import math
import os
import urllib.parse
import urllib.request


URL = "https://public.coindcx.com/market_data/orderbook"
COINS = ("BTC", "ETH", "SOL", "XRP")
INR_FEE = 0.005 * 1.18
# Optimistic current public C2C rate; an account-specific rate may be different.
C2C_FEE = 0.0017 * 1.18


def parse_book(pair, data):
    if not isinstance(data, dict):
        raise ValueError("%s: expected a book object" % pair)
    stamp = int(data["timestamp"])

    def side(name, reverse):
        raw = data[name]
        if not isinstance(raw, dict) or not raw:
            raise ValueError("%s: empty %s" % (pair, name))
        quotes = [(float(price), float(qty)) for price, qty in raw.items()]
        if any(p <= 0 or q <= 0 or not math.isfinite(p) or not math.isfinite(q) for p, q in quotes):
            raise ValueError("%s: malformed %s" % (pair, name))
        quotes.sort(reverse=reverse)
        return {"price": quotes[0][0], "quantity": quotes[0][1]}

    return {"timestamp_ms": stamp, "bid": side("bids", True), "ask": side("asks", False)}


def fetch_book(pair):
    url = URL + "?" + urllib.parse.urlencode({"pair": pair})
    request = urllib.request.Request(url, headers={"User-Agent": "coindcx-paper-bots-arbitrage-research"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return pair, parse_book(pair, json.load(response))


def routes(coin, books, inr_fee=INR_FEE, c2c_fee=C2C_FEE):
    rupees_per_usdt_bid = books["I-USDT_INR"]["bid"]["price"]
    rupees_per_usdt_ask = books["I-USDT_INR"]["ask"]["price"]
    rupees_per_coin_ask = books["I-%s_INR" % coin]["ask"]["price"]
    rupees_per_coin_bid = books["I-%s_INR" % coin]["bid"]["price"]
    usdt_per_coin_bid = books["B-%s_USDT" % coin]["bid"]["price"]
    usdt_per_coin_ask = books["B-%s_USDT" % coin]["ask"]["price"]
    forward_gross = usdt_per_coin_bid * rupees_per_usdt_bid / rupees_per_coin_ask - 1
    reverse_gross = rupees_per_coin_bid / (usdt_per_coin_ask * rupees_per_usdt_ask) - 1
    forward_net = ((1 - c2c_fee) * (1 - inr_fee) * (1 + forward_gross) / (1 + inr_fee) - 1)
    reverse_net = ((1 - inr_fee) * (1 + reverse_gross) / ((1 + inr_fee) * (1 + c2c_fee)) - 1)
    return {
        "inr_coin_usdt_inr": {"gross_upper_bound": forward_gross, "net_upper_bound": forward_net},
        "inr_usdt_coin_inr": {"gross_upper_bound": reverse_gross, "net_upper_bound": reverse_net},
    }


def snapshot():
    pairs = ["I-USDT_INR"] + ["%s-%s_%s" % (prefix, coin, quote)
                               for coin in COINS for prefix, quote in (("I", "INR"), ("B", "USDT"))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(pairs)) as pool:
        books = dict(pool.map(fetch_book, pairs))
    now = dt.datetime.now(dt.timezone.utc)
    stamps = [book["timestamp_ms"] for book in books.values()]
    if max(stamps) - min(stamps) > 5_000:
        raise ValueError("books are more than five seconds apart; the apparent cycle may be stale")
    if any(now.timestamp() * 1000 - stamp > 30_000 or stamp - now.timestamp() * 1000 > 5_000 for stamp in stamps):
        raise ValueError("one or more books are stale or dated in the future")
    return {
        "fetched_at_utc": now.isoformat(),
        "book_skew_ms": max(stamps) - min(stamps),
        "assumed_inr_fee_with_gst": INR_FEE,
        "assumed_c2c_fee_with_gst": C2C_FEE,
        "capital_context_inr": 5_000,
        "qualification": "Best displayed quotes only. No depth, rounding, transfer, atomic execution or adverse movement. "
                         "Negative gross return excludes a profitable market-order cycle at this snapshot; "
                         "positive gross or net return would not establish an executable opportunity.",
        "books": books,
        "routes": {coin: routes(coin, books) for coin in COINS},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "orderbook_snapshot.json"))
    args = parser.parse_args()
    result = snapshot()
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("Public CoinDCX books at %s (skew %.1fs). Best-quote upper bounds:" %
          (result["fetched_at_utc"], result["book_skew_ms"] / 1000))
    for coin, directions in result["routes"].items():
        for route, value in directions.items():
            print("%s %-20s gross %+.2f%%, after assumed fees %+.2f%%" %
                  (coin, route, 100 * value["gross_upper_bound"], 100 * value["net_upper_bound"]))


if __name__ == "__main__":
    main()
