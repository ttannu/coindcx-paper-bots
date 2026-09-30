import argparse
import datetime as dt
import os
import sys
import time

from .coindcx import DataUnavailable
from .engine import run


def main():
    parser = argparse.ArgumentParser(prog="python3 -m sim", description="Run one step of the paper-trading simulation.")
    parser.add_argument("--root", default=os.getcwd(), help="project folder (default: current folder)")
    parser.add_argument("--start", help="ISO start time, used only when there is no saved state yet (for testing)")
    parser.add_argument("--now", help="ISO time to treat as now (for testing)")
    parser.add_argument("--no-notify", action="store_true", help="don't post to the GitHub issue")
    args = parser.parse_args()
    now_ms = _parse_ms(args.now) if args.now else int(time.time() * 1000)
    start_ms = _parse_ms(args.start) if args.start else None
    try:
        run(os.path.abspath(args.root), now_ms, start_ms=start_ms, notify=not args.no_notify)
    except DataUnavailable as exc:
        print("CoinDCX data unavailable, skipping this run: %s" % exc)
    return 0


def _parse_ms(text):
    moment = dt.datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return int(moment.timestamp() * 1000)


if __name__ == "__main__":
    sys.exit(main())
