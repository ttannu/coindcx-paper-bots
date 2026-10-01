# CoinDCX paper-trading bots

1,043 rule-based trading bots each get ₹5,000 of **simulated** money and trade for 15 days on live CoinDCX INR prices, across 47 of the most volatile coins. The goal is ₹1,00,000. Every strategy runs separately on every coin, next to coin-flip bots that trade at random, so the results show which strategies have an edge and which are just lucky. Every strategy was also replayed over the six months before the launch, and none made money on average after fees and tax ([what the backtests found](#what-the-backtests-found)). Since 1 Oct, 282 low-cost twins also run the closest of them with CoinDCX's VIP fee and limit orders, to test whether cheaper trading would be enough; in the backtests it wasn't. Alongside them, an AI trading desk of ten Gemini agents reads the prices, the news, and what the bots have learned, and runs two more books. No real money, exchange accounts, or exchange API keys are involved. GitHub Actions runs everything on a schedule, so nobody needs to touch it.

<!-- DASHBOARD:START -->
### Live results: day 2 of 15

Last updated 02 Oct 2026, 02:42 IST. Runs from 30 Sep 2026, 18:45 IST to 15 Oct 2026, 18:45 IST. Refreshed about every 30 minutes; each run catches up on everything it missed.

Each bot started with ₹5,000 of simulated money. The goal is ₹1,00,000 (20x). BTC/INR since the start: -1.1% (₹85,22,786 to ₹84,28,635).

1,045 bots on 47 coins. 95 are up and 635 are down; 0 are wiped out. The median bot is at ₹4,920. 679 of 987 bots are ahead of simply holding their coin.

**AI trading desk.** A team of AI agents (Google Gemini, free tier) meets every 2 hours to run two books: three analysts (market, news, quant), a bull and a bear who debate, a trader, a three-person risk team, and a portfolio manager who makes the final call. The desk's limits are enforced in code, not left to the AI.

| Book | Value if sold now | Return | Rank | Closed trades | Now |
|---|---|---|---|---|---|
| AI desk: spot portfolio | ₹4,601 | -8.0% | 810 of 1,045 | 5 | holding BTC, PUMP, SUI |
| AI desk: futures, up to 3x | ₹3,905 | -21.9% | 983 of 1,045 | 4 | short NEAR at 2x |

Both books started with ₹5,000 on 30 Sep 2026, 19:00 IST. **Latest decision, 02 Oct 2026, 01:42 IST** (market neutral, news mood greed, Fear & Greed 74): We are rebalancing the spot book to maximize exposure to high-momentum assets, increasing SUI and adding PUMP while maintaining our core BTC position. GALA is being exited as it lacks the relative strength seen in other mid-caps. In the futures book, we are rotating from the SAGA short into a NEAR short to exploit the specific catalyst of a $3.8M protocol exploit combined with extreme long crowding and maximum funding rates. Spot: BTC 30% (stop -5%, target +20%), SUI 30% (stop -8%, target +20%), PUMP 15% (stop -12%, target +30%). Futures: short NEAR at 2x (stop 6% away, target 15% away).

Minutes of every meeting: https://github.com/ttannu/coindcx-paper-bots/blob/main/docs/desk.md

**Top 15 bots**

| # | Bot | Value if sold now, after costs and tax | Return | Progress to ₹1,00,000 | Closed trades | Worst drop | Now |
|---|---|---|---|---|---|---|---|
| 1 | POL: 10x futures trend | ₹6,766 | +35.3% | 6.8% | 0 | 16.1% | short 10x |
| 2 | NEAR: coin flip, 3x futures | ₹6,137 | +22.7% | 6.1% | 1 | 3.8% | flat |
| 3 | FIL: 10x futures trend | ₹6,049 | +21.0% | 6.0% | 1 | 23.5% | short 10x |
| 4 | QNT: coin flip, 3x futures | ₹5,756 | +15.1% | 5.8% | 1 | 15.1% | flat |
| 5 | ENA: 10x futures trend | ₹5,721 | +14.4% | 5.7% | 1 | 50.2% | short 10x |
| 6 | NEAR: 10x futures trend | ₹5,589 | +11.8% | 5.6% | 1 | 53.3% | short 10x |
| 7 | POL: 3x futures trend | ₹5,532 | +10.6% | 5.5% | 0 | 5.4% | short 3x |
| 8 | BONK: coin flip, 3x futures | ₹5,484 | +9.7% | 5.5% | 1 | 3.9% | flat |
| 9 | ZEC: coin flip, 3x futures | ₹5,408 | +8.2% | 5.4% | 2 | 5.9% | short 3x |
| 10 | ICP: coin flip, 3x futures | ₹5,400 | +8.0% | 5.4% | 1 | 7.7% | long 3x |
| 11 | PEPE: coin flip, 3x futures | ₹5,348 | +7.0% | 5.3% | 1 | 3.5% | long 3x |
| 12 | APT: 10x futures trend | ₹5,333 | +6.7% | 5.3% | 0 | 23.1% | short 10x |
| 13 | FIL: 3x futures trend | ₹5,321 | +6.4% | 5.3% | 1 | 7.9% | short 3x |
| 14 | SUI: coin flip, 3x futures | ₹5,309 | +6.2% | 5.3% | 1 | 8.9% | long 3x |
| 15 | ENA: 3x futures trend | ₹5,280 | +5.6% | 5.3% | 1 | 17.7% | short 3x |

**The original bots**

| Bot | Value if sold now | Return | Rank | Closed trades | Now |
|---|---|---|---|---|---|
| Dip buyer (RSI) | ₹5,000 | +0.0% | 96 of 1,045 | 0 | cash |
| Breakout hunter | ₹5,000 | +0.0% | 97 of 1,045 | 0 | cash |
| Self-learning ensemble | ₹5,000 | +0.0% | 98 of 1,045 | 0 | cash, nothing has an edge |
| Grid trader | ₹4,999 | -0.0% | 412 of 1,045 | 1 | cash |
| Buy & hold BTC | ₹4,878 | -2.4% | 568 of 1,045 | 0 | holding BTC |
| Goal chaser (10x futures) | ₹4,872 | -2.6% | 575 of 1,045 | 2 | long 10x |
| Trend follower | ₹4,625 | -7.5% | 797 of 1,045 | 10 | holding BTC |

**Added on 1 Oct, after the [backtests](docs/research.md)**

| Bot | Value if sold now | Return | Rank | Closed trades | Now |
|---|---|---|---|---|---|
| Liquid 5, held | ₹4,827 | -3.5% | 618 of 1,045 | 0 | holding BTC, DOGE, ETH, SOL, XRP |
| Liquid 5, BTC trend filter | ₹4,827 | -3.5% | 619 of 1,045 | 0 | holding BTC, DOGE, ETH, SOL, XRP |

**Strategy report card.** Each strategy runs separately on every coin. "Beat holding" counts the coins where it is ahead of buying that coin and holding it.

| Strategy | Median return | Best coin | Worst coin | In profit | Beat holding | Wiped out | Skill shown? |
|---|---|---|---|---|---|---|---|
| Coin flip, 3x futures | +0.0% | NEAR +22.7% | PHA -27.3% | 23/47 | 34/47 | 0 | luck control |
| RSI dip <30 ±6% | +0.0% | SIREN +2.7% | QNT -7.4% | 5/47 | 46/47 | 0 | too early |
| RSI dip <30 ±3% | +0.0% | SIREN +1.9% | NEAR -8.7% | 6/47 | 46/47 | 0 | too early |
| RSI dip <25 ±3% | +0.0% | PHA +0.5% | NEAR -4.5% | 1/47 | 46/47 | 0 | too early |
| Breakout 20/10h | +0.0% | SAGA +0.0% | ONE -8.1% | 0/47 | 42/47 | 0 | too early |
| Breakout 48/24h | +0.0% | SAGA +0.0% | NEAR -6.7% | 0/47 | 45/47 | 0 | too early |
| Pump rider | +0.0% | SAGA +0.0% | NEAR -8.9% | 0/47 | 46/47 | 0 | too early |
| Grid 3% | -0.4% | SIREN +1.8% | QNT -7.0% | 8/47 | 46/47 | 0 | too early |
| Self-learning | -0.8% | ZEC +2.9% | TRUMP -7.4% | 12/47 | 44/47 | 0 | too early |
| Grid 1.5% | -1.9% | SIREN +3.7% | QNT -18.6% | 1/47 | 41/47 | 0 | too early |
| Long/short 12/48h | -2.1% | SAGA +5.1% | MUBARAK -11.7% | 15/47 | 34/47 | 0 | too early |
| Trend 12/48h | -2.7% | SAGA +0.0% | MUBARAK -17.4% | 0/47 | 31/47 | 0 | too early |
| Coin flip #1 | -3.0% | APT +0.5% | RENDER -10.7% | 3/47 | 30/47 | 0 | luck control |
| Coin flip #2 | -3.5% | AAVE +0.6% | QNT -13.6% | 2/47 | 34/47 | 0 | luck control |
| Trend 24/96h | -3.9% | AAVE +2.0% | SIREN -19.8% | 1/47 | 28/47 | 0 | too early |
| Coin flip #3 | -4.1% | AAVE +1.8% | ENA -10.7% | 1/47 | 32/47 | 0 | luck control |
| Buy & hold | -5.5% | AAVE +1.5% | QNT -17.4% | 1/47 | – | 0 | benchmark |
| Trend 6/24h | -6.6% | AAVE +0.7% | QNT -15.7% | 1/47 | 18/47 | 0 | too early |
| 3x futures trend | -11.5% | POL +10.6% | MUBARAK -40.4% | 8/47 | 15/47 | 0 | too early |
| Fast trend 5/20h | -11.8% | APT +0.0% | SIREN -37.5% | 0/47 | 10/47 | 0 | too early |
| Fast trend 2/8h | -18.0% | SAGA -7.3% | SIREN -54.6% | 0/47 | 3/47 | 0 | too early |
| 10x futures trend | -37.2% | POL +35.3% | PUMP -90.6% | 7/47 | 8/47 | 0 | too early |

**How much of this is luck?** The 188 coin-flip bots trade at random. The luckiest is NEAR: coin flip, 3x futures at +22.7%, and their median is -2.8%. With this many bots, some will look brilliant by chance alone, so a strategy counts as skilled only after 3 days, and only if its median bot is in profit after costs, beats the coin flips, and beats holding on most coins.

**Where the money went.** On average a bot's trades have made -2.7% of its starting money from price moves, before any costs. The spread took 1.1%, fees and GST 1.5%, tax 0.4% and futures funding 0.0%, which leaves -5.7%. 6 of the 22 strategies are ahead before costs, and 0 after them. Tax is charged on every profitable sale and losses can't be set off against it, so a strategy can pay tax while losing money. Average per bot, as a share of its starting money, counting the costs of selling what is still held:

| Strategy | Bots | Price moves | Spread | Fees and GST | Tax | Funding | Result |
|---|---|---|---|---|---|---|---|
| RSI dip <25 ±3% | 47 | +0.0% | -0.0% | -0.0% | -0.0% | – | -0.1% |
| RSI dip <30 ±3% | 47 | +0.4% | -0.2% | -0.3% | -0.1% | – | -0.2% |
| RSI dip <30 ±6% | 47 | +0.3% | -0.2% | -0.2% | -0.1% | – | -0.2% |
| Breakout 48/24h | 47 | -0.2% | -0.0% | -0.1% | -0.0% | – | -0.3% |
| Pump rider | 47 | -0.3% | -0.1% | -0.1% | -0.0% | – | -0.5% |
| Breakout 20/10h | 47 | -0.4% | -0.1% | -0.2% | -0.0% | – | -0.7% |
| Coin flip, 3x futures | 47 | +1.9% | -0.5% | -0.6% | -1.5% | -0.1% | -0.7% |
| Grid 3% | 47 | +0.4% | -0.4% | -0.6% | -0.2% | – | -0.8% |
| Self-learning | 47 | -0.7% | -0.1% | -0.1% | -0.2% | -0.0% | -1.0% |
| Original bots | 7 | +0.5% | -0.8% | -1.3% | -0.2% | -0.1% | -1.8% |
| Long/short 12/48h | 47 | -1.8% | -0.2% | -0.2% | -0.3% | -0.0% | -2.7% |
| Grid 1.5% | 47 | +1.9% | -1.7% | -2.4% | -0.5% | – | -2.8% |
| Added on 1 Oct | 2 | -1.8% | -0.5% | -1.2% | -0.0% | – | -3.5% |
| Coin flip #2 | 47 | -0.5% | -1.1% | -1.7% | -0.2% | – | -3.6% |
| Coin flip #1 | 47 | -0.7% | -1.3% | -1.8% | -0.1% | – | -3.9% |
| Coin flip #3 | 47 | -1.0% | -1.3% | -1.8% | -0.1% | – | -4.2% |
| Trend 12/48h | 47 | -1.7% | -1.0% | -1.5% | -0.0% | – | -4.3% |
| Trend 24/96h | 47 | -2.2% | -1.0% | -1.4% | -0.0% | – | -4.6% |
| Buy & hold | 47 | -3.6% | -0.8% | -1.1% | -0.0% | – | -5.6% |
| Trend 6/24h | 47 | -2.9% | -1.8% | -2.6% | -0.0% | – | -7.3% |
| 3x futures trend | 47 | -9.4% | -1.0% | -1.2% | -1.2% | -0.1% | -12.9% |
| Fast trend 5/20h | 47 | -4.9% | -3.4% | -5.1% | -0.0% | – | -13.5% |
| AI desk | 2 | -12.1% | -1.0% | -1.5% | -0.3% | -0.0% | -14.9% |
| Fast trend 2/8h | 47 | -6.6% | -5.1% | -7.5% | -0.0% | – | -19.3% |
| 10x futures trend | 47 | -27.0% | -2.7% | -3.1% | -3.0% | -0.3% | -36.1% |
| **All bots** | 1,045 | -2.7% | -1.1% | -1.5% | -0.4% | -0.0% | -5.7% |

**Low-cost test.** Since 1 Oct the strategies that had an edge before costs in the backtests also run with CoinDCX's VIP 1 fee (0.17% instead of 0.5%, plus GST). The grids and dip-buyers place limit orders, which pay no spread but fill at exactly their price and only once the price trades through it; stops and the other exits are market orders and still pay it. Tax is unchanged, so the gap to the same strategy at normal costs is what fees and spread took. These 282 bots are judged against a buy & hold and a coin flip at the same low cost, and are left out of the rankings above.

| Strategy | Median, normal costs | Median, low cost | Fees and spread | In profit | Beat holding | Skill shown? |
|---|---|---|---|---|---|---|
| RSI dip <30 ±3% | +0.0% | +0.0% | -0.5% → -0.1% | 5/47 | 44/47 | too early |
| RSI dip <30 ±6% | +0.0% | +0.0% | -0.4% → -0.1% | 4/47 | 44/47 | too early |
| Grid 3% | -0.4% | -0.1% | -1.0% → -0.3% | 17/47 | 46/47 | too early |
| Grid 1.5% | -1.9% | -0.1% | -4.2% → -1.0% | 20/47 | 45/47 | too early |
| Coin flip #1 | -3.0% | -1.9% | -3.1% → -1.9% | 6/47 | 33/47 | luck control |
| Buy & hold | -5.5% | -4.7% | -1.9% → -1.2% | 3/47 | – | benchmark |

VIP 1 needs ₹5,00,000 of trading in 30 days. The busiest of these strategies, grid 1.5%, has traded ₹18,532 per bot in 1.3 days, a pace of ₹4,20,243 a month, so a ₹5,000 account trading this way would not get there on its own.

![Value of the top bots over time](docs/equity.svg)

Costs so far across all bots: ₹72,006 in fees and GST, ₹860 of TDS held back (refundable when you file taxes), and ₹6,216 of estimated tax.

**What the original self-learning bot sees.** Its best strategy variants over the last 3 days, after all costs:

| Variant | Last 3 days | Signal now |
|---|---|---|
| BTC hold long | +0.3% | long |
| BTC 24h breakout | +0.3% | long |
| ETH hold long | +0.0% | long |
| BTC 72h breakout | +0.0% | flat |
| BTC RSI reversion | +0.0% | flat |
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

The strategy report card on the dashboard ranks the 22 strategies by their median return across all 47 coins. A strategy is marked as showing skill only after 3 days, and only when its median bot is in profit after costs, beats the coin-flip bots' median, and is ahead of simply holding the coin on more than half of the coins. The first two conditions were added on 1 Oct: before that, any strategy that sat in cash through a falling first day showed skill. With over a thousand bots, the best few usually owe much of their lead to luck, which is why the coin-flip bots are there.

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

**Added on 1 Oct, after the backtests.** Two bots built from what [the backtests](docs/research.md) found, replayed from the same start as the others:

| Bot | Rules |
|---|---|
| Liquid 5, held | Holds the 5 coins with the most CoinDCX INR volume (the median day of the last 30) in equal parts, passing over any whose smallest order is more than its share (ZEC's is about ₹1,400) for the next one. Every 3 days it sells a coin that has dropped out of the 10 most traded and fills the gap. The yardstick for the next bot. |
| Liquid 5, BTC trend filter | The same 5 coins, held only while BTC's price is above its 30-day average, and in cash otherwise. It checks every 3 days. In 17 past 15-day windows it ended flat (+0.1% a window after costs) while holding the same coins lost 2.2%, and its worst window was -10% instead of -20%. It was the best of 14 timing rules tried, which flatters that result; these 15 days are its real test. |

**Low-cost twins, added on 1 Oct.** On each of the 47 coins, 6 strategies also run a second time with the lowest costs a CoinDCX INR account can realistically reach: buy & hold, the 1.5% and 3% grids, the two RSI dip <30 strategies, and coin flip #1. They pay the VIP 1 spot fee, 0.17% instead of 0.5% plus GST, and the grids and dip-buyers place limit orders instead of trading at the market. A limit order pays no spread, but it fills at exactly its price and only once a later candle trades through it. The dip-buyers bid the signal candle's close for an hour, so they only get in if the price keeps falling. Stops and time exits stay market orders. Tax is unchanged, so the gap between a twin and its original is what fees and spread took. The 282 twins are compared with buy & hold and a coin flip at the same low cost in their own table on the dashboard, and are left out of the rankings, the report card, and what the AI desk sees.

No bot ever changes its rules. The self-learning bots only choose between fixed variants, and the fixed bots are the control group that shows whether those choices actually help.

## The AI trading desk

A team of AI agents runs two more paper books with ₹5,000 each: a **spot portfolio** of up to 5 coins, and a **futures book** with one position at a time, long or short, at up to 3x. The structure follows [TradingAgents](https://github.com/TauricResearch/TradingAgents) (Apache-2.0), an open-source framework that models a trading firm; this is a small rewrite of the idea, not its code.

Every 2 hours the desk meets:

1. Three analysts report at the same time. The **market analyst** reads the price action of all 47 coins over the last hour to the last week: momentum, RSI, trend, volatility, distance from the 7-day high, spread, and volume. The **news analyst** reads the last day's headlines from CoinDesk, Cointelegraph, Decrypt, Bitcoin Magazine, and CryptoSlate, the Fear & Greed index, and CoinGecko's trending coins. The **quant analyst** reads what the rule-based bots have found on each coin, compared with holding it and with the coin-flip bots, and how futures traders are positioned on Hyperliquid (funding rates and open interest).
2. A **bull** and a **bear** researcher debate the reports.
3. The **trader** turns the research and the debate into a plan for both books.
4. A **risk team** of three (aggressive, neutral, conservative) reviews the plan.
5. The **portfolio manager** makes the final decision, and notes a lesson from how the desk's trades have worked out, which later meetings see.

The code, not the AI, enforces the limits. At most 30% of the spot book goes into one coin and 95% in total, and positions under 5% are dropped. Only coins with fresh prices and a real market can be traded: at least ₹5 lakh of CoinDCX INR volume in the last 24 hours, with no trades in at most a quarter of those 15-minute candles, because a quiet book shows stale prices (added on 1 Oct, after the backtests below showed how much stale prices distort results). A coin it holds that stops qualifying is kept as it is, with its stop, until it can be traded again. Futures leverage is 1x to 3x. Every position gets a stop loss (2-15% away on spot, 1-10% on futures) that can be tightened but never loosened, and a book that falls below 70% of its starting money closes out and stops for good. Decisions fill at the next 15-minute close, so the desk never trades at a price it has already seen, and they pay the same fees and tax as every other bot. Changes smaller than 5% of a book are skipped to save fees.

The agents run on Google's free Gemini API tier. The analysts, researchers, and risk team use Gemini 3.5 Flash Lite, with 3.1 Flash Lite and Gemma 4 as fallbacks. The trader and the portfolio manager use the strongest Gemini Flash model that is available (3.8 down to 3.5), falling back to the lighter models. When a model is busy or out of quota, the desk moves on to the next one. If the meeting still can't finish, it is skipped: the books keep their positions and stops, and the desk tries again 30 minutes later. The minutes of every meeting, with what each agent said, are in [`docs/desk.md`](docs/desk.md). On the free tier Google may use the prompts to improve its products; they contain only public prices, headlines, and the bots' simulated results.

AI traders have no proven edge. In [Alpha Arena](https://nof1.ai) Season 1 (October 2025), six leading AI models each traded $10,000 of real money on crypto futures for about two weeks: two finished ahead, and four lost between 42% and 59%. The coin-flip bots and buy & hold are the yardstick for this desk too.

## What the simulation charges

The costs follow what a CoinDCX INR account in India pays. They are set in [`config.json`](config.json).

- **Spot trading fee:** 0.5% of each trade, plus 18% GST on the fee.
- **Futures fee (INR margin):** 0.05% plus GST, and 0.01% funding every 8 hours. Futures are priced off CoinDCX's INR spot candles.
- **Slippage:** spot buys fill above the candle price and sells below it by half of the coin's bid-ask spread, measured on 30 Sep 2026: from 0.1% (the minimum) for the most liquid coins up to 0.73% for the thinnest. Futures fill 0.05% away.
- **TDS:** 1% of each spot sale is held back once a bot's total sales pass ₹50,000. It is refundable when you file your return, so it counts toward the bot's value. Futures have no TDS.
- **Tax:** an estimated 31.2% (30% plus 4% cess) of the gain on every profitable sale. Losses can't be set off against gains, and fees aren't deductible. Because of this, a bot that wins early and then loses everything can end with a negative value: it still owes tax on the early wins.
- **Minimum order:** ₹100, and quantities are rounded down to each coin's lot size.
- **Low-cost twins:** the VIP 1 spot fee of 0.17% plus GST, which CoinDCX charges from ₹5 lakh of trading in 30 days, and no spread on limit orders. Everything else is the same.

"Value if sold now" is what a bot would keep if it sold everything at that moment and paid all of the above. The dashboard's "Where the money went" table splits each strategy's result into what the price moves made and what the spread, fees, tax, and funding took, counting the costs of selling whatever is still held. The AI desk sees the same split for its own books at every meeting.

## What the backtests found

On 1 Oct the strategies were replayed over the six months before the launch: 12 back-to-back 15-day windows from 3 Apr to 30 Sep 2026, on all 47 coins, through the same code. Each was run three times: with no costs (the strategy's skill alone), with fees and spread, and with tax as well. Mean result per bot per window:

| Strategy | No costs | Fees and spread | Tax as well |
|---|---:|---:|---:|
| Buy & hold | +6.0% | +3.9% | +0.8% |
| Grid, 3% steps | +7.9% | 0.0% | -2.7% |
| Grid, 1.5% steps | +21.1% | -5.5% | -10.3% |
| RSI dip-buying | +13.2% | -3.5% | -6.5% |
| Self-learning | -2.6% | -4.0% | -6.2% |
| Trend-following, 6/24h | -16.4% | -45.0% | -47.5% |
| Coin flip | +3.0% | -23.8% | -27.2% |
| Coin flip, 3x futures | +3.1% | -7.4% | -20.9% |
| Trend-following, 3x futures | -32.6% | -41.1% | -55.0% |

- No rule-based strategy made money on average after costs. Buying and holding, which pays the costs once, came closest, and its result is the market's direction rather than skill: it made money in 5 of the 12 windows, and without the rally in the last one (+32%) its average would be -2.0%.
- Trend-following lost even before costs. On CoinDCX's INR prices short moves tended to reverse, partly because the last traded price bounces between the bid and the ask.
- Dip-buying and grids had an edge before costs, but mostly on thinly traded coins, where prices go stale. On the 10 most liquid coins a 1.5% grid made +6.3% before costs, against +25.1% on the other 37, which is too little to pay for its 60-odd trades.
- Picking the best bots of one window to run in the next lost money: -7.1% a window for the top 10 and -5.4% for the top 50.
- Strategies added for the test also failed after costs: holding the recent top gainers (16 versions, on liquid coins only), going long or short the strongest or weakest coin on futures, wider grids, slower breakouts, and following futures funding rates.
- Holding the 5 most liquid coins only while BTC was above its 30-day average ended flat (+0.1% a window) instead of losing 2.2%, and halved the worst window, but made money in only 4 of 17 windows: it avoided losses rather than finding profits.
- Cheaper trading wasn't enough. With CoinDCX's VIP 1 fee (0.17%) and limit orders, the 1.5% grid averaged -1.5% a window instead of -10.3%, the 3% grid -0.3%, and the dip-buyers -1.8% to -2.9%, while holding at the same fee made +1.6%. Filling those limit orders at the candle price, as the normal-cost bots fill, had shown +2% to +6%: profits from fills a real order can't get.

A round trip on CoinDCX spot costs about 2%, and the tax takes 31.2% of every winning trade with no set-off for the losing ones, so a strategy has to trade rarely and win big. Nothing tested here did that reliably. The method, the full results, and the three research mistakes that were caught along the way are in [`docs/research.md`](docs/research.md).

## How it runs

- GitHub is asked to run the [`simulate`](.github/workflows/simulate.yml) workflow every 30 minutes. Each run downloads the latest closed 15-minute and 1-hour candles for all 47 coins from CoinDCX's public API and replays every candle since the last run, in order. GitHub often starts scheduled runs late or skips some, sometimes for hours; that only delays the dashboard, because the next run replays everything it missed.
- As a backup, a small Google Apps Script ([`scheduler/trigger.gs`](scheduler/trigger.gs)) also starts the workflow every 30 minutes through the GitHub API, using a token that can only run this repository's workflows. Once the workflow has switched itself off, or the token expires, the script deletes its own trigger.
- Each run saves its progress to [`state/`](state): `state.json` (balances, positions, and what the self-learning bots have learned), `equity.csv` (every bot's value in rupees, one column per bot, every hour and at the end of each run), and `trades.csv` (every simulated trade, with the reason for it). It also refreshes the dashboard above and the chart in [`docs/equity.svg`](docs/equity.svg).
- After replaying the candles, a run holds an AI desk meeting if one is due, which takes about a minute. It needs a `GEMINI_API_KEY` repository secret; without one, the desk's books wait in cash.
- A daily report is posted as a comment on the "Paper-trading bots: daily reports" issue by the first run after 09:00 IST.
- If the repository has `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` secrets, the reports are also emailed to that address from itself through Gmail, starting with a welcome email showing the current standings. Without them, email is skipped.
- After 15 days the workflow posts the final results, closes the issue, and switches itself off.

## What keeps it running unattended

- BTC's prices are downloaded first. If CoinDCX is down, or more than half of the price downloads fail, the run is skipped without touching the saved state, and the next run catches up. Malformed or impossible candles (missing fields, zero or negative prices) are dropped.
- If only some coins fail to download, the run goes ahead without them, and they replay what they missed once they're back. A coin that sends no prices for 12 hours is treated as delisted: its bots are frozen at their last value and marked as frozen.
- Each bot runs in isolation. If one hits a bug, it is frozen and shown as "stopped by an error" while the others carry on.
- Progress is saved before the dashboard is drawn, so a drawing problem can't lose data, and a bug in reporting or email is logged without stopping the run from saving. Saving to the repo retries up to 5 times.
- The AI desk can't hold up a run. A meeting has a 5-minute budget, every news and data source is optional, and a failed meeting only means no new decision. Models that are out of daily quota are skipped until it resets. Decisions are saved with the time of the candle they were based on and replayed at the next one, so catching up after missed runs gives exactly the same trades.
- The start message, daily reports, emails, final report, closing the issue, and switching off each retry on later runs until they succeed, and none of them is ever posted twice.
- A code change that adds bots replays every bot from the start, so they all share one timeline. CoinDCX only returns about 10 days of 15-minute prices, so after that such a change stops the run with an error instead of replaying from a later start, and the saved state is left as it was.
- Only the newest unsent email of each kind is kept, so a late or broken email setup can't flood the inbox. If Gmail rejects the password, the next attempt waits 6 hours. The workflow switches off once the final report and email are out, or a day after the end at the latest.
- Before launch the code was stress-tested on synthetic 15-day markets: calm, bull, bear, violent chop, a 48% crash, a pump and dump, flash wicks of -45% and +60%, a coin falling 95%, and missing, duplicated, and garbage candles, all with irregular run schedules. It was also run at full size (1,041 bots and the AI desk on 47 coins, about a second per run plus about a minute for a desk meeting), with coins dropping out and coming back. The desk's tests use stand-in agents to cover its limits, stop losses in a crash, failed and skipped meetings, a missing or rejected key, and replaying its decisions. The tests are in [`tests/`](tests).

## Controls

- **Stop early:** Actions tab, then `simulate`, then "Disable workflow".
- **Run another 15 days:** delete the `state` folder, then re-enable the `simulate` workflow.
- **Turn off the AI desk:** remove the `desk` section from [`config.json`](config.json), or delete the `GEMINI_API_KEY` secret. Its books then keep whatever they hold, with their stops.
- **Send a note:** add a Markdown file to [`notes/`](notes) whose first line is `# Title`. The next run posts it on the report issue and emails it, once.
- **Run one step locally:** `python3 -m sim --no-notify`. Tests: `python3 -m unittest discover -s tests`.

## Limits

No bot here, including the self-learning ones, is guaranteed to make money, and no strategy wins on every coin: trend followers lose in choppy markets, dip buyers and grids lose in crashes, and leverage gets wiped out by sharp moves either way. With 1,043 bots, the best few will usually look impressive by chance alone, so check any bot against the coin-flip bots and against holding its coin before reading anything into it. In the synthetic stress tests the original self-learning bot gained about 23% on average when the market trended, lost about 5% on average when it went nowhere, and never lost more than about 16%. The AI desk is an experiment too: language models can misread data or change their minds from one meeting to the next, and its limits only cap how much it can lose, not whether it loses. Fills happen at candle prices, so the simulation can't see order-book depth or outages. The tax figure is an estimate, not tax advice. A strategy that does well for 15 days in a simulation can still lose real money. None of this is financial advice.
