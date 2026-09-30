# CoinDCX paper-trading bots

Seven trading bots each get ₹5,000 of **simulated** money and trade for 15 days on live CoinDCX INR prices. The goal is ₹1,00,000. One of the bots is self-learning. No real money, API keys, or exchange accounts are involved. GitHub Actions runs everything on a schedule, so nobody needs to touch it.

<!-- DASHBOARD:START -->
### Live results: day 1 of 15

Last updated 30 Sep 2026, 23:42 IST. Runs from 30 Sep 2026, 18:45 IST to 15 Oct 2026, 18:45 IST. GitHub is asked to refresh this every 30 minutes but often runs late; each run catches up on everything it missed.

Each bot started with ₹5,000 of simulated money. The goal is ₹1,00,000 (20x). BTC/INR since the start: -1.7% (₹85,22,786 to ₹83,81,384).

| # | Bot | Value if sold now, after costs and tax | Return | Progress to ₹1,00,000 | Closed trades | Win rate | Worst drop | Now |
|---|---|---|---|---|---|---|---|---|
| 1 | Goal chaser (10x futures) | ₹5,012 | +0.2% | 5.0% | 0 | – | 5.0% | long 10x |
| 2 | Dip buyer (RSI) | ₹5,000 | +0.0% | 5.0% | 0 | – | 0.0% | cash |
| 3 | Breakout hunter | ₹5,000 | +0.0% | 5.0% | 0 | – | 0.0% | cash |
| 4 | Grid trader | ₹5,000 | +0.0% | 5.0% | 0 | – | 0.0% | cash |
| 5 | Self-learning ensemble | ₹5,000 | +0.0% | 5.0% | 0 | – | 0.0% | cash, nothing has an edge |
| 6 | Trend follower | ₹4,899 | -2.0% | 4.9% | 3 | 0.0% | 2.0% | cash |
| 7 | Buy & hold BTC | ₹4,865 | -2.7% | 4.9% | 0 | – | 3.0% | holding BTC |

![Value of each bot over time](docs/equity.svg)

Costs so far across all bots: ₹116 in fees and GST, ₹0 of TDS held back (refundable when you file taxes), and ₹0 of estimated tax.

**What the self-learning bot sees.** Its best strategy variants over the last 3 days, after all costs:

| Variant | Last 3 days | Signal now |
|---|---|---|
| BTC RSI reversion | +1.0% | flat |
| BTC hold short | +0.8% | short |
| ETH hold short | +0.4% | short |
| BTC 72h breakout | +0.0% | flat |
| ETH RSI reversion | +0.0% | flat |
<!-- DASHBOARD:END -->

## The bots

| Bot | Rules |
|---|---|
| Self-learning ensemble | Runs 22 strategy variants on BTC and ETH (trend, breakout, mean reversion, hold long, hold short) as unfunded shadow accounts that pay the same costs, and scores each on its last 3 days after fees and tax. Every hour it follows the best one. It switches only when another is ahead by more than 2 points and at least 12 hours have passed since its last change, and it holds cash when none has made at least 2%. Trades futures at 1x or less (no leverage, no liquidation risk, about a tenth of spot fees) and takes smaller positions when the market is swinging hard. Studies the previous 7 days before its first trade. Checked every 15 minutes: if it falls 8% below its best value it holds cash for 24 hours, and if it falls 15% below its starting money it stops trading for good. |
| Buy & hold BTC | Benchmark. Buys Bitcoin once with all ₹5,000 and never sells. |
| Trend follower | 1-hour candles on BTC, ETH, SOL. Buys when the 20-hour average is above the 50-hour average and price bounces back above the 20-hour average. Sells on a trailing stop (2.5x ATR) or when price closes below the 50-hour average. |
| Dip buyer (RSI) | 15-minute candles on BTC and ETH. Buys when RSI(14) falls below 30. Sells at +3% profit, -3% loss, when RSI recovers above 55, or after 12 hours. |
| Breakout hunter | 1-hour candles on BTC, ETH, SOL, XRP, DOGE. Buys when price closes above its 20-hour high. Sells when price closes below its 10-hour low or hits a stop 2x ATR below entry. |
| Grid trader | 15-minute candles on BTC. Splits the money into 6 lots, buys a lot each time price falls another 2%, and sells each lot 2% above where it bought. Re-centres when price runs up. |
| Goal chaser (10x futures) | What chasing 20x in 15 days looks like. Always all-in on BTC futures at 10x leverage: long when the 9-hour average is above the 21-hour average, short otherwise. A 9.5% move the wrong way wipes out the position. |

The six fixed bots never change their rules. They are the control group that shows whether the self-learning bot's choices actually help.

## What the simulation charges

The costs follow what a CoinDCX INR account in India pays. They are set in [`config.json`](config.json).

- **Spot trading fee:** 0.5% of each trade, plus 18% GST on the fee.
- **Futures fee (INR margin):** 0.05% plus GST, and 0.01% funding every 8 hours. Futures are priced off CoinDCX's INR spot candles.
- **Slippage:** buys fill 0.1% above the candle price and sells 0.1% below (0.05% for futures).
- **TDS:** 1% of each spot sale is held back once a bot's total sales pass ₹50,000. It is refundable when you file your return, so it counts toward the bot's value. Futures have no TDS.
- **Tax:** an estimated 31.2% (30% plus 4% cess) of the gain on every profitable sale. Losses can't be set off against gains, and fees aren't deductible. Because of this, a bot that wins early and then loses everything can end with a negative value: it still owes tax on the early wins.
- **Minimum order:** ₹100, and quantities are rounded down to each coin's lot size.

"Value if sold now" is what a bot would keep if it sold everything at that moment and paid all of the above.

## How it runs

- GitHub is asked to run the [`simulate`](.github/workflows/simulate.yml) workflow every 30 minutes. Each run downloads the latest closed 15-minute and 1-hour candles from CoinDCX's public API and replays every candle since the last run, in order. GitHub often starts scheduled runs late or skips some, sometimes for hours; that only delays the dashboard, because the next run replays everything it missed.
- As a backup, a small Google Apps Script ([`scheduler/trigger.gs`](scheduler/trigger.gs)) also starts the workflow every 30 minutes through the GitHub API, using a token that can only run this repository's workflows. Once the workflow has switched itself off, or the token expires, the script deletes its own trigger.
- Each run saves its progress to [`state/`](state): `state.json` (balances, positions, and what the self-learning bot has learned), `equity.csv` (each bot's value every hour), and `trades.csv` (every simulated trade, with the reason for it). It also refreshes the dashboard above and the chart in [`docs/equity.svg`](docs/equity.svg).
- A daily report is posted as a comment on the "Paper-trading bots: daily reports" issue by the first run after 09:00 IST.
- If the repository has `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` secrets, the reports are also emailed to that address from itself through Gmail, starting with a welcome email showing the current standings. Without them, email is skipped.
- After 15 days the workflow posts the final results, closes the issue, and switches itself off.

## What keeps it running unattended

- If CoinDCX is down, the run is skipped without touching the saved state, and the next run catches up. Malformed or impossible candles (missing fields, zero or negative prices) are dropped.
- Each bot runs in isolation. If one hits a bug, it is frozen and shown as "stopped by an error" while the others carry on.
- Progress is saved before the dashboard is drawn, so a drawing problem can't lose data, and a bug in reporting or email is logged without stopping the run from saving. Saving to the repo retries up to 5 times.
- The start message, daily reports, emails, final report, closing the issue, and switching off each retry on later runs until they succeed, and none of them is ever posted twice.
- Only the newest unsent email of each kind is kept, so a late or broken email setup can't flood the inbox. If Gmail rejects the password, the next attempt waits 6 hours. The workflow switches off once the final report and email are out, or a day after the end at the latest.
- Before launch the code was stress-tested on synthetic 15-day markets: calm, bull, bear, violent chop, a 48% crash, a pump and dump, flash wicks of -45% and +60%, a coin falling 95%, and missing, duplicated, and garbage candles, all with irregular run schedules. The tests are in [`tests/`](tests).

## Controls

- **Stop early:** Actions tab, then `simulate`, then "Disable workflow".
- **Run another 15 days:** delete the `state` folder, then re-enable the `simulate` workflow.
- **Run one step locally:** `python3 -m sim --no-notify`. Tests: `python3 -m unittest discover -s tests`.

## Limits

No bot here, including the self-learning one, is guaranteed to make money. In the synthetic stress tests the self-learning bot gained about 23% on average when the market trended, lost about 5% on average when it went nowhere, and never lost more than about 16%. Fills happen at candle prices, so the simulation can't see order-book depth or outages. The tax figure is an estimate, not tax advice. A strategy that does well for 15 days in a simulation can still lose real money. None of this is financial advice.
