# CoinDCX paper-trading bots

1,041 trading bots each get ₹5,000 of **simulated** money and trade for 15 days on live CoinDCX INR prices, across 47 of the most volatile coins. The goal is ₹1,00,000. Every strategy runs separately on every coin, next to coin-flip bots that trade at random, so the results show which strategies have an edge and which are just lucky. No real money, API keys, or exchange accounts are involved. GitHub Actions runs everything on a schedule, so nobody needs to touch it.

<!-- DASHBOARD:START -->
### Live results: day 1 of 15

Last updated 01 Oct 2026, 00:12 IST. Runs from 30 Sep 2026, 18:45 IST to 15 Oct 2026, 18:45 IST. Refreshed about every 30 minutes; each run catches up on everything it missed.

Each bot started with ₹5,000 of simulated money. The goal is ₹1,00,000 (20x). BTC/INR since the start: -1.4% (₹85,22,786 to ₹84,02,372).

1,041 bots on 47 coins. 93 are up and 410 are down; 0 are wiped out. The median bot is at ₹5,000. 865 of 987 bots are ahead of simply holding their coin.

**Top 15 bots**

| # | Bot | Value if sold now, after costs and tax | Return | Progress to ₹1,00,000 | Closed trades | Worst drop | Now |
|---|---|---|---|---|---|---|---|
| 1 | PHA: 10x futures trend | ₹6,291 | +25.8% | 6.3% | 0 | 10.1% | long 10x |
| 2 | PUMP: 10x futures trend | ₹6,286 | +25.7% | 6.3% | 0 | 14.4% | long 10x |
| 3 | NEAR: 10x futures trend | ₹6,196 | +23.9% | 6.2% | 0 | 20.4% | long 10x |
| 4 | POL: 10x futures trend | ₹5,763 | +15.3% | 5.8% | 0 | 6.9% | short 10x |
| 5 | QNT: 10x futures trend | ₹5,636 | +12.7% | 5.6% | 0 | 17.3% | long 10x |
| 6 | DOT: 10x futures trend | ₹5,537 | +10.7% | 5.5% | 0 | 9.3% | long 10x |
| 7 | PHA: 3x futures trend | ₹5,389 | +7.8% | 5.4% | 0 | 3.8% | long 3x |
| 8 | PUMP: 3x futures trend | ₹5,388 | +7.8% | 5.4% | 0 | 4.7% | long 3x |
| 9 | NEAR: 3x futures trend | ₹5,360 | +7.2% | 5.4% | 0 | 6.2% | long 3x |
| 10 | FIL: 10x futures trend | ₹5,332 | +6.6% | 5.3% | 1 | 10.3% | short 10x |
| 11 | SUI: 10x futures trend | ₹5,307 | +6.1% | 5.3% | 0 | 16.5% | long 10x |
| 12 | SIREN: 10x futures trend | ₹5,245 | +4.9% | 5.2% | 0 | 41.3% | short 10x |
| 13 | POL: 3x futures trend | ₹5,230 | +4.6% | 5.2% | 0 | 2.2% | short 3x |
| 14 | QNT: 3x futures trend | ₹5,192 | +3.8% | 5.2% | 0 | 5.9% | long 3x |
| 15 | SHIB: coin flip, 3x futures | ₹5,167 | +3.3% | 5.2% | 0 | 1.0% | short 3x |

**The original bots**

| Bot | Value if sold now | Return | Rank | Closed trades | Now |
|---|---|---|---|---|---|
| Goal chaser (10x futures) | ₹5,098 | +2.0% | 26 of 1,041 | 0 | long 10x |
| Dip buyer (RSI) | ₹5,000 | +0.0% | 94 of 1,041 | 0 | cash |
| Breakout hunter | ₹5,000 | +0.0% | 95 of 1,041 | 0 | cash |
| Grid trader | ₹5,000 | +0.0% | 96 of 1,041 | 0 | cash |
| Self-learning ensemble | ₹5,000 | +0.0% | 97 of 1,041 | 0 | cash, nothing has an edge |
| Trend follower | ₹4,884 | -2.3% | 814 of 1,041 | 3 | cash |
| Buy & hold BTC | ₹4,863 | -2.7% | 847 of 1,041 | 0 | holding BTC |

**Strategy report card.** Each strategy runs separately on every coin. "Beat holding" counts the coins where it is ahead of buying that coin and holding it.

| Strategy | Median return | Best coin | Worst coin | In profit | Beat holding | Wiped out | Skill shown? |
|---|---|---|---|---|---|---|---|
| Coin flip, 3x futures | +0.0% | SHIB +3.3% | PHA -12.8% | 3/47 | 38/47 | 0 | luck control |
| Self-learning | +0.0% | TRUMP +1.3% | HYPE -4.4% | 14/47 | 46/47 | 0 | not yet |
| Coin flip #2 | +0.0% | NEAR +0.9% | PENGU -4.1% | 2/47 | 45/47 | 0 | luck control |
| Coin flip #3 | +0.0% | PUMP +0.8% | SUI -4.3% | 2/47 | 44/47 | 0 | luck control |
| Trend 12/48h | +0.0% | SAGA +0.0% | TRUMP -5.2% | 0/47 | 45/47 | 0 | not yet |
| Trend 24/96h | +0.0% | SAGA +0.0% | TRUMP -5.2% | 0/47 | 44/47 | 0 | not yet |
| RSI dip <25 ±3% | +0.0% | SAGA +0.0% | BTC +0.0% | 0/47 | 45/47 | 0 | not yet |
| RSI dip <30 ±3% | +0.0% | SAGA +0.0% | BTC +0.0% | 0/47 | 45/47 | 0 | not yet |
| RSI dip <30 ±6% | +0.0% | SAGA +0.0% | BTC +0.0% | 0/47 | 45/47 | 0 | not yet |
| Breakout 20/10h | +0.0% | SAGA +0.0% | NEAR -2.2% | 0/47 | 43/47 | 0 | not yet |
| Breakout 48/24h | +0.0% | SAGA +0.0% | NEAR -2.2% | 0/47 | 44/47 | 0 | not yet |
| Pump rider | +0.0% | SAGA +0.0% | ENA -5.3% | 0/47 | 43/47 | 0 | not yet |
| Coin flip #1 | +0.0% | QNT +0.0% | SAGA -5.8% | 0/47 | 41/47 | 0 | luck control |
| Long/short 12/48h | -0.1% | PHA +2.6% | HYPE -4.4% | 22/47 | 46/47 | 0 | not yet |
| Grid 3% | -0.2% | MUBARAK +0.1% | PENGU -1.7% | 7/47 | 44/47 | 0 | not yet |
| Grid 1.5% | -0.8% | ZEC +0.0% | PENGU -4.2% | 0/47 | 43/47 | 0 | not yet |
| 3x futures trend | -0.8% | PHA +7.8% | HYPE -13.1% | 19/47 | 36/47 | 0 | not yet |
| Trend 6/24h | -1.1% | NEAR +0.5% | UNI -5.9% | 1/47 | 42/47 | 0 | not yet |
| Fast trend 5/20h | -2.6% | NEAR +0.5% | TRX -12.1% | 1/47 | 35/47 | 0 | not yet |
| 10x futures trend | -2.8% | PHA +25.8% | HYPE -43.2% | 19/47 | 27/47 | 0 | not yet |
| Fast trend 2/8h | -3.8% | ONE +0.0% | BNB -14.9% | 0/47 | 24/47 | 0 | not yet |
| Buy & hold | -4.3% | PUMP +1.0% | PENGU -9.4% | 2/47 | – | 0 | benchmark |

**How much of this is luck?** The 188 coin-flip bots trade at random. The luckiest is SHIB: coin flip, 3x futures at +3.3%, and their median is +0.0%. With this many bots, some will look brilliant by chance alone, so a strategy counts as skilled only if its median return beats the coin flips and it beats holding on most coins.

![Value of the top bots over time](docs/equity.svg)

Costs so far across all bots: ₹16,040 in fees and GST, ₹0 of TDS held back (refundable when you file taxes), and ₹468 of estimated tax.

**What the original self-learning bot sees.** Its best strategy variants over the last 3 days, after all costs:

| Variant | Last 3 days | Signal now |
|---|---|---|
| BTC RSI reversion | +1.0% | flat |
| BTC hold short | +0.8% | short |
| ETH hold short | +0.4% | short |
| BTC 72h breakout | +0.0% | flat |
| ETH RSI reversion | +0.0% | flat |
<!-- DASHBOARD:END -->

## The bots

**The swarm.** Each of the 47 coins gets the same 22 bots, 1,034 in all:

| Strategy | Trades | Rules |
|---|---|---|
| Buy & hold | spot | Buys the coin once with all its money and never sells. Every other strategy on the coin is measured against this. |
| Trend 6/24h | spot | 1-hour candles. Buys when the 6-hour average is above the 24-hour average and price crosses or bounces above the faster one. Sells on a trailing stop 2.5x ATR below the high, or a close below the slower average. |
| Trend 12/48h | spot | The same with 12- and 48-hour averages. |
| Trend 24/96h | spot | The same with 24- and 96-hour averages. |
| Fast trend 2/8h | spot | The same on 15-minute candles, with 8- and 32-candle averages (2 and 8 hours). |
| Fast trend 5/20h | spot | The same on 15-minute candles, with 20- and 80-candle averages (5 and 20 hours). |
| RSI dip <25 ±3% | spot | 15-minute candles. Buys when RSI(14) falls below 25. Sells at +3%, -3%, when RSI recovers above 55, or after 12 hours. |
| RSI dip <30 ±3% | spot | The same, buying below RSI 30. |
| RSI dip <30 ±6% | spot | The same, buying below RSI 30 and selling at +6% or -6%. |
| Breakout 20/10h | spot | 1-hour candles. Buys a close above the 20-hour high. Sells a close below the 10-hour low, or at a stop 2x ATR below entry. |
| Breakout 48/24h | spot | The same with the 48-hour high and the 24-hour low. |
| Grid 1.5% | spot | 15-minute candles. Splits the money into 6 lots, buys a lot each time price falls another 1.5%, and sells each lot 1.5% above where it bought. Re-centres when price runs up. |
| Grid 3% | spot | The same with 3% steps. |
| Pump rider | spot | 1-hour candles. Buys when the coin is up 8% or more in 24 hours, the last candle closed green, and price is above its 20-hour average. Sells on a trailing stop 3x ATR below the high, a close below the 20-hour average, or after 24 hours. |
| Coin flip #1, #2, #3 | spot | Luck controls. After every hourly candle a fixed pseudo-random draw decides: in cash, the bot buys with 1-in-12 odds; holding, it sells with 1-in-12 odds. They pay the same costs as the others. |
| 3x futures trend | futures | Always all-in on futures at 3x: long when the 9-hour average is above the 21-hour average, short otherwise. A 33% move the wrong way wipes out the position. |
| 10x futures trend | futures | The same at 10x. A 9.5% move the wrong way wipes out the position. |
| Long/short 12/48h | futures | Futures at 1x (no liquidation risk): long when the 12-hour average is above the 48-hour average, short otherwise. |
| Coin flip, 3x futures | futures | Luck control on futures at 3x. After every hourly candle, with 1-in-12 odds, it opens a random long or short when flat, or closes its position. |
| Self-learning | futures | The self-learning bot below, on this coin alone: 11 shadow variants (trend long/short and long-only, breakouts, RSI reversion, hold long, hold short), following the best one after costs, at 1x or less, with the same loss brake and capital floor. |

The strategy report card on the dashboard ranks the 22 strategies by their median return across all 47 coins. A strategy is marked as showing skill only when its median beats the coin-flip bots' median and it is ahead of simply holding the coin on more than half of the coins. With over a thousand bots, the best few usually owe much of their lead to luck, which is why the coin-flip bots are there.

**The coins.** Picked on 30 Sep 2026 from CoinDCX's 339 active INR markets: at least ₹5 lakh traded in the previous 24 hours, a bid-ask spread of 1.5% or less, and a price that moved in at least 148 of the previous 168 hours. Stablecoins and tokenised gold were left out. From most to least volatile: SAGA, QNT, SIREN, ONE, PHA, MUBARAK, PUMP, ENA, ONDO, NEAR, HBAR, PENGU, SEI, INJ, FIL, VVV, APT, ICP, BONK, GALA, KAS, SUI, ARB, RENDER, AAVE, XLM, UNI, POL, ZEC, LINK, VET, TAO, AVAX, BCH, DOT, PEPE, TRUMP, ADA, DOGE, XRP, SHIB, SOL, HYPE, TRX, BNB, ETH, BTC. Each also has an INR-margined futures contract on CoinDCX.

**The original bots.** The first 7 bots keep running unchanged:

| Bot | Rules |
|---|---|
| Self-learning ensemble | Runs 22 strategy variants on BTC and ETH (trend, breakout, mean reversion, hold long, hold short) as unfunded shadow accounts that pay the same costs, and scores each on its last 3 days after fees and tax. Every hour it follows the best one. It switches only when another is ahead by more than 2 points and at least 12 hours have passed since its last change, and it holds cash when none has made at least 2%. Trades futures at 1x or less (no leverage, no liquidation risk, about a tenth of spot fees) and takes smaller positions when the market is swinging hard. Studies the previous 7 days before its first trade. Checked every 15 minutes: if it falls 8% below its best value it holds cash for 24 hours, and if it falls 15% below its starting money it stops trading for good. |
| Buy & hold BTC | Benchmark. Buys Bitcoin once with all ₹5,000 and never sells. |
| Trend follower | 1-hour candles on BTC, ETH, SOL. Buys when the 20-hour average is above the 50-hour average and price bounces back above the 20-hour average. Sells on a trailing stop (2.5x ATR) or when price closes below the 50-hour average. |
| Dip buyer (RSI) | 15-minute candles on BTC and ETH. Buys when RSI(14) falls below 30. Sells at +3% profit, -3% loss, when RSI recovers above 55, or after 12 hours. |
| Breakout hunter | 1-hour candles on BTC, ETH, SOL, XRP, DOGE. Buys when price closes above its 20-hour high. Sells when price closes below its 10-hour low or hits a stop 2x ATR below entry. |
| Grid trader | 15-minute candles on BTC. Splits the money into 6 lots, buys a lot each time price falls another 2%, and sells each lot 2% above where it bought. Re-centres when price runs up. |
| Goal chaser (10x futures) | What chasing 20x in 15 days looks like. Always all-in on BTC futures at 10x leverage: long when the 9-hour average is above the 21-hour average, short otherwise. A 9.5% move the wrong way wipes out the position. |

No bot ever changes its rules. The self-learning bots only choose between fixed variants, and the fixed bots are the control group that shows whether those choices actually help.

## What the simulation charges

The costs follow what a CoinDCX INR account in India pays. They are set in [`config.json`](config.json).

- **Spot trading fee:** 0.5% of each trade, plus 18% GST on the fee.
- **Futures fee (INR margin):** 0.05% plus GST, and 0.01% funding every 8 hours. Futures are priced off CoinDCX's INR spot candles.
- **Slippage:** spot buys fill above the candle price and sells below it by half of the coin's bid-ask spread, measured on 30 Sep 2026: from 0.1% (the minimum) for the most liquid coins up to 0.73% for the thinnest. Futures fill 0.05% away.
- **TDS:** 1% of each spot sale is held back once a bot's total sales pass ₹50,000. It is refundable when you file your return, so it counts toward the bot's value. Futures have no TDS.
- **Tax:** an estimated 31.2% (30% plus 4% cess) of the gain on every profitable sale. Losses can't be set off against gains, and fees aren't deductible. Because of this, a bot that wins early and then loses everything can end with a negative value: it still owes tax on the early wins.
- **Minimum order:** ₹100, and quantities are rounded down to each coin's lot size.

"Value if sold now" is what a bot would keep if it sold everything at that moment and paid all of the above.

## How it runs

- GitHub is asked to run the [`simulate`](.github/workflows/simulate.yml) workflow every 30 minutes. Each run downloads the latest closed 15-minute and 1-hour candles for all 47 coins from CoinDCX's public API and replays every candle since the last run, in order. GitHub often starts scheduled runs late or skips some, sometimes for hours; that only delays the dashboard, because the next run replays everything it missed.
- As a backup, a small Google Apps Script ([`scheduler/trigger.gs`](scheduler/trigger.gs)) also starts the workflow every 30 minutes through the GitHub API, using a token that can only run this repository's workflows. Once the workflow has switched itself off, or the token expires, the script deletes its own trigger.
- Each run saves its progress to [`state/`](state): `state.json` (balances, positions, and what the self-learning bots have learned), `equity.csv` (every bot's value in rupees, one column per bot, every hour and at the end of each run), and `trades.csv` (every simulated trade, with the reason for it). It also refreshes the dashboard above and the chart in [`docs/equity.svg`](docs/equity.svg).
- A daily report is posted as a comment on the "Paper-trading bots: daily reports" issue by the first run after 09:00 IST.
- If the repository has `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` secrets, the reports are also emailed to that address from itself through Gmail, starting with a welcome email showing the current standings. Without them, email is skipped.
- After 15 days the workflow posts the final results, closes the issue, and switches itself off.

## What keeps it running unattended

- BTC's prices are downloaded first. If CoinDCX is down, or more than half of the price downloads fail, the run is skipped without touching the saved state, and the next run catches up. Malformed or impossible candles (missing fields, zero or negative prices) are dropped.
- If only some coins fail to download, the run goes ahead without them, and they replay what they missed once they're back. A coin that sends no prices for 12 hours is treated as delisted: its bots are frozen at their last value and marked as frozen.
- Each bot runs in isolation. If one hits a bug, it is frozen and shown as "stopped by an error" while the others carry on.
- Progress is saved before the dashboard is drawn, so a drawing problem can't lose data, and a bug in reporting or email is logged without stopping the run from saving. Saving to the repo retries up to 5 times.
- The start message, daily reports, emails, final report, closing the issue, and switching off each retry on later runs until they succeed, and none of them is ever posted twice.
- Only the newest unsent email of each kind is kept, so a late or broken email setup can't flood the inbox. If Gmail rejects the password, the next attempt waits 6 hours. The workflow switches off once the final report and email are out, or a day after the end at the latest.
- Before launch the code was stress-tested on synthetic 15-day markets: calm, bull, bear, violent chop, a 48% crash, a pump and dump, flash wicks of -45% and +60%, a coin falling 95%, and missing, duplicated, and garbage candles, all with irregular run schedules. It was also run at full size (1,041 bots on 47 coins, about a second per run), with coins dropping out and coming back. The tests are in [`tests/`](tests).

## Controls

- **Stop early:** Actions tab, then `simulate`, then "Disable workflow".
- **Run another 15 days:** delete the `state` folder, then re-enable the `simulate` workflow.
- **Run one step locally:** `python3 -m sim --no-notify`. Tests: `python3 -m unittest discover -s tests`.

## Limits

No bot here, including the self-learning ones, is guaranteed to make money, and no strategy wins on every coin: trend followers lose in choppy markets, dip buyers and grids lose in crashes, and leverage gets wiped out by sharp moves either way. With 1,041 bots, the best few will usually look impressive by chance alone, so check any bot against the coin-flip bots and against holding its coin before reading anything into it. In the synthetic stress tests the original self-learning bot gained about 23% on average when the market trended, lost about 5% on average when it went nowhere, and never lost more than about 16%. Fills happen at candle prices, so the simulation can't see order-book depth or outages. The tax figure is an estimate, not tax advice. A strategy that does well for 15 days in a simulation can still lose real money. None of this is financial advice.
