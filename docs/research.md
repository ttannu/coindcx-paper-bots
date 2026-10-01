# What six months of CoinDCX prices say about these strategies

Before trusting 15 days of live paper trading, every strategy in this repository was replayed over the six months before the launch. The short answer: none of them made money on CoinDCX's INR spot market after fees and tax, not even at CoinDCX's VIP fee with limit orders, and the few that looked promising either lost in the next window or came from prices that could not really be traded. This page explains how that was tested, where the money went, and the three mistakes in the research that were caught along the way.

Written on 1 Oct 2026. The market in this period mostly fell and then rallied hard in the second half of September, so these results describe one stretch of one market, not a law.

## How it was tested

- **Prices.** 15-minute and 1-hour candles for the same 47 coins as the live run, from CoinDCX's public API (`I-<COIN>_INR` pairs), from 20 Dec 2025 to 30 Sep 2026. For the checks against global prices, the CoinDCX `B-<COIN>_USDT` pairs (routed to Binance) were converted to rupees with CoinDCX's USDT/INR price. Futures funding rates came from Hyperliquid's public API.
- **Windows.** 12 back-to-back 15-day windows from 3 Apr to 30 Sep 2026. Each window starts every bot fresh with ₹5,000, like the live run. The earlier months (20 Dec to 3 Apr) were kept aside and used only by the signal studies below.
- **Same code.** The windows were replayed through the live engine in [`sim/`](../sim), with the same bots, costs, and order of events, so a backtest trade is exactly what the live run would have done.
- **Three cost settings.** Every window was run with the real costs, with no tax, and with no costs at all (no fees, spread, funding, TDS, or tax). The first difference is the fees and spread; the second is the tax.

## Results after all costs

Every (coin, window) pair counts once: 47 coins in 12 windows, about 560 results per strategy. "Mean" is what an equal-weight portfolio of the strategy across all coins would have made in a window. "Beat holding" is how often the strategy did better than buying and holding the same coin in the same window.

| Strategy | Median | Mean | Bots in profit | Beat holding | Windows the portfolio made money | Trades per window |
|---|---:|---:|---:|---:|---:|---:|
| Buy & hold | -1.7% | +0.8% | 42% | - | 5 of 12 | 0 |
| Grid, 3% steps | -0.9% | -2.7% | 33% | 53% | 2 of 12 | 17 |
| RSI dip-buying, <25, ±3% | -1.5% | -3.9% | 11% | 45% | 0 of 12 | 4 |
| Pump rider | -2.7% | -6.2% | 6% | 45% | 0 of 12 | 2 |
| RSI dip-buying, <30, ±6% | -4.9% | -6.5% | 10% | 34% | 0 of 12 | 7 |
| Self-learning (per coin) | -7.7% | -6.2% | 18% | 31% | 1 of 12 | 9 |
| Breakout 48/24h | -9.7% | -8.2% | 14% | 26% | 2 of 12 | 3 |
| Grid, 1.5% steps | -9.0% | -10.3% | 7% | 29% | 0 of 12 | 62 |
| Long/short 12/48h, 1x futures | -14.7% | -14.5% | 16% | 19% | 1 of 12 | 12 |
| Coin flip, 3x futures | -21.9% | -20.9% | 14% | 20% | 0 of 12 | 15 |
| Trend 24/96h | -24.5% | -26.1% | 2% | 10% | 0 of 12 | 10 |
| Coin flip | -27.8% | -27.2% | 1% | 1% | 0 of 12 | 15 |
| Trend 6/24h | -47.5% | -47.5% | 0% | 0% | 0 of 12 | 23 |
| 3x futures trend | -60.5% | -55.0% | 6% | 5% | 0 of 12 | 21 |
| Fast trend 2/8h | -79.0% | -78.1% | 0% | 0% | 0 of 12 | 83 |
| 10x futures trend | -100.0% | -103.9% | 1% | 1% | 0 of 12 | 19 |

The rules of each strategy are in the [README](../README.md#the-bots). Results below -100% are possible because the tax on early wins is still owed after later losses.

Buy & hold's +0.8% average owes everything to the last window: from 15 Sep to 30 Sep the average coin rose 32%, led by QNT (+318%) and ONE (+241%). Without that window, its average is -2.0%. The market's median coin ranged from -12.5% to +19.4% per window, so which window a bot ran in mattered far more than its strategy.

The original seven bots did the same: holding BTC -1.1% (median per window), the BTC grid -0.7%, RSI dip-buying -5.2%, the self-learning bot -5.9%, breakout -10.2%, trend -25.6%, and the 10x goal chaser -79.1%.

## Where the money went

Mean result per bot per window, with each cost added in turn:

| Strategy | No costs | Fees and spread | Tax as well | Trades per window | Winning trades |
|---|---:|---:|---:|---:|---:|
| Buy & hold | +6.0% | +3.9% | +0.8% | 0 | - |
| Grid, 1.5% steps | +21.1% | -5.5% | -10.3% | 62 | 92% |
| RSI dip-buying, <30, ±6% | +13.2% | -3.5% | -6.5% | 7 | 80% |
| Grid, 3% steps | +7.9% | 0.0% | -2.7% | 17 | 90% |
| Coin flip | +3.0% | -23.8% | -27.2% | 15 | 49% |
| Coin flip, 3x futures | +3.1% | -7.4% | -20.9% | 15 | 51% |
| Self-learning | -2.6% | -4.0% | -6.2% | 9 | 29% |
| Trend 6/24h | -16.4% | -45.0% | -47.5% | 23 | 12% |
| 3x futures trend | -32.6% | -41.1% | -55.0% | 21 | 16% |
| 10x futures trend | -67.1% | -77.5% | -103.9% | 19 | 17% |

Three things decide these results:

1. **A round trip on CoinDCX spot costs about 2%.** That is the 0.5% fee plus 18% GST on each side, and half the bid-ask spread on each side, 0.1% to 0.73% depending on the coin. A coin flip that trades 15 times in 15 days, with no skill at all, ends 27% down, and 30 points of that are costs. The 1.5% grid had the most skill of anything tested, +21% before costs, and paid 27 points of it in fees and spread.
2. **Tax is charged on every winning trade, and losses don't offset it.** At 31.2%, a strategy that wins often pays tax often, and a strategy with many losing trades pays tax on its few wins while its losses cost it in full. Leveraged futures suffer most: the 3x trend strategy lost 14 points of every window to tax, and the 10x one lost 26.
3. **Trend-following had no skill here even before costs.** On CoinDCX's INR prices, short moves tended to reverse over the next few hours, so buying strength meant buying near a top. The signal studies below show that much of this reversal is the last traded price bouncing between the bid and the ask on thin books, which no strategy can profit from.

## Picking winners doesn't work

If past results carried over, the best bots of one window should do well in the next. They didn't. Each rule below chose using one window and was scored on the next, which it had not seen:

| Rule | Mean per window | Median |
|---|---:|---:|
| Run the best strategy of the last window on every coin | -1.4% | -3.2% |
| Run each coin's best strategy of the last window | -3.8% | -4.7% |
| Run the top 50 bots of the last window | -5.4% | -5.3% |
| Run the top 10 bots of the last window | -7.1% | -9.7% |
| Run every strategy bot (no choosing) | -27.5% | -28.7% |
| Coin flips | -25.6% | -25.8% |

Choosing helped only in the sense that it mostly avoided the high-turnover strategies. None of the rules beat buying and holding everything, and the top 10 did worse than the top 50: the very best bots of a window were mostly lucky.

## Thin coins flatter the backtests

CoinDCX's INR books for many of these coins are quiet. Over the 90 days to 30 Sep the median day traded ₹3.07 crore of BTC, but only about ₹1 lakh of QNT, ONE, or SAGA, and QNT went without a single trade in 51% of hours. A candle with no trades repeats the last price, and a candle with a few small trades can print far from where a real order would fill.

That shows in the results. Before costs, the 1.5% grid made +6.3% a window on the 10 most liquid coins and +25.1% on the other 37; RSI dip-buying (<30) made +2.5% and +15.5%. Most of the mean-reversion "skill" came from the thin coins, where a trade at those prices was least likely to happen, and on the liquid coins the skill was too small to pay for the trades.

The big moves were real, though. In the rally of 15 to 30 Sep, QNT rose 318% in rupees and 317% on global markets, and ONE 241% and 235%.

Since 1 Oct the AI desk may only trade coins with at least ₹5 lakh of INR volume in the last 24 hours and trades in at least three quarters of those 15-minute candles.

## Strategies added for this test

Before giving up on rules, several strategies built around the failures above were added and run through the same 12 windows, with real costs:

| Strategy | Mean | Median | Windows in profit | Worst window |
|---|---:|---:|---:|---:|
| Hold the top 3 coins by 7-day return, rebalance every 3 days | +1.1% | -3.8% | 4 of 12 | -23.1% |
| Hold the top 3 coins by 3-day return, rebalance every 3 days | +0.9% | -9.7% | 5 of 12 | -21.1% |
| Grid, 8% steps | -0.3% | -0.1% | 5 of 12 | -2.5% |
| Grid, 5% steps | -0.8% | -1.0% | 4 of 12 | -4.3% |
| Breakout 168/72h | -2.4% | -3.4% | 2 of 12 | -8.6% |
| Long/short 48/192h, 1x futures | -2.4% | -3.1% | 3 of 12 | -8.8% |
| Trend 48/192h | -18.0% | -17.6% | 0 of 12 | -27.0% |
| Long the strongest coin or short the weakest, 1x futures | -22.2% to -26.5% | | 0 to 2 of 12 | |
| The same at 2x | -40.1% to -48.5% | | 0 to 1 of 12 | |
| Hold the single top coin, rebalance daily or every 3 days | -14.0% to -33.6% | | 1 to 3 of 12 | |

The two rotations with a positive mean made all of it in the last window (+72% and +74%, in the September rally) and lost in most others. Slower strategies lost less because they traded less, and the wide grids came close to break-even for the same reason, but nothing made a reliable profit.

## Signals studied directly

Some ideas are cheaper to test as a signal than as a bot: does a coin's past behaviour predict its next move? These studies used all three periods (20 Dec to 3 Apr, 3 Apr to 2 Jul, 2 Jul to 30 Sep), including the one no backtest had touched.

- **Short-term reversal.** Among the 20 most liquid coins, the fifth that fell most in the last 4 hours beat the average of the 20 by 0.3 to 0.4 points over the next 4 hours on INR prices, at 69% to 78% of the times checked, in all three periods. On global prices for the same coins the effect vanished in every period (51% to 56%). It is the last traded price bouncing between the bid and the ask on INR books, which no order can capture. On all 47 coins, where the books are thinner, the INR effect was bigger: 0.4 to 0.6 points, at 77% to 86% of checks.
- **Momentum over days.** Over longer horizons the pattern turned around. Among the same 20 coins, the fifth that rose most over the last 3 days beat the average over the next 3 days in every period: by 0.55 to 0.76 points on INR prices, and 0.5 to 1.0 on global prices (DOT, which had no global price before April, was left out where it was missing). Ranking by the last 7 days gave 0.4 to 1.2 points. This was the only effect that held in all three periods and on both kinds of price.
- **Big dips.** Coins down more than 10% in a day did +8.9%, -4.2%, and -0.3% the next day in the three periods: no consistent effect.
- **The INR premium.** Buying a coin when its INR price was 3% or more below the global price looked excellent: +2.6% to +3.5% over the next 12 hours. But the gain fell to +0.7% to +1.1% when entering one candle later, and to about zero when paying that candle's high. The signal candles had traded a median of only ₹849 to ₹2,024 in their hour, and requiring ₹1 lakh of volume removed the signal completely. The "discount" was a stale price.
- **Futures funding.** Coins whose futures traders were most crowded long (the highest funding fifth on Hyperliquid) beat the average coin by only 0.1% to 0.25% a day. A strategy holding the top 5 lost 14.1% a window on INR prices after costs, against -1.9% for holding every coin, and made money in 1 of the 18 15-day windows since early January. On global prices with no costs, holding the top 8 made +5.1% a window against +2.2% for holding everything: a real but small effect that costs erase.

## Trading the momentum signal

Momentum over 3 to 7 days was the one effect that held everywhere, so it was traded directly. The 16 variants were fixed before running: ranking on INR or global prices, over the last 3 or 7 days, rebalancing every 3 or 7 days, and holding the top 3 or 5. Only coins that had traded a median of at least ₹10 lakh a day over the previous 30 days could be held, so the list only used what was known at the time. They ran in 17 windows from 18 Jan to 30 Sep.

| | Mean per window | Windows in profit |
|---|---:|---:|
| The 16 variants, before costs | -1.6% to +1.7% | 5 to 8 of 17 |
| Holding every eligible coin, before costs | +0.6% | 8 of 17 |
| The 16 variants, after costs | -8.4% to -5.5% | 2 to 4 of 17 |
| Holding every eligible coin, after costs | -2.8% | 4 of 17 |

Before costs the rotations did no better than holding everything, and after costs every one of them did worse. Half a point every 3 days on average is small next to the swings of single coins, and each swap cost about 2%.

## Timing the market

The last idea was to stay out of falling markets: hold the most liquid coins (BTC alone, or the 5 with the most INR volume) only while BTC's price is above its 10-, 20-, or 30-day average, checked every day or every 3 days, and hold cash otherwise. With real costs, in the same 17 windows:

| Strategy | Mean | Median | Windows in profit | Worst window |
|---|---:|---:|---:|---:|
| BTC, always held | -2.4% | -2.4% | 5 of 17 | -17.9% |
| BTC, only above its 30-day average, checked every 3 days | -0.4% | -0.6% | 4 of 17 | -7.7% |
| The 5 most liquid coins, always held | -2.2% | -2.9% | 4 of 17 | -19.6% |
| The 5 most liquid, while BTC is above its 30-day average, checked every 3 days | +0.1% | -0.1% | 4 of 17 | -10.0% |
| The 5 most liquid, while BTC is above its 20-day average, checked every 3 days | -0.5% | -0.1% | 3 of 17 | -10.4% |
| The 5 most liquid, while BTC is above its 10-day average, checked daily | -3.7% | -5.3% | 4 of 17 | -15.2% |

Every filter checked every 3 days did better than holding, and the slow ones halved the worst window, but none made real money: the best ended flat, with a profit in 4 of 17 windows. The gain came from sitting in cash through the fall from February to June, after one or two switches a window, so it rests on a handful of decisions in one falling market. A filter like this limits losses; it doesn't create profits.

## Cheaper trading

Added on 1 Oct. Fees and spread took most of what the grids and dip-buyers made before costs, so they were replayed over the same 12 windows with the lowest costs a CoinDCX INR account can realistically reach: the VIP 1 spot fee of 0.17% instead of 0.5% (plus GST), which needs ₹5 lakh of trading in 30 days, and limit orders instead of market orders. A limit order pays no spread, but it fills at exactly its price and only once a later candle trades through it. The dip-buyers bid the signal candle's close for an hour; stops and time exits stay market orders. Tax is unchanged. Mean result per bot per window, after all costs:

| Strategy | Normal costs | VIP 1 fee and limit orders | Windows in profit | On the 10 most liquid coins |
|---|---:|---:|---:|---:|
| Buy & hold | +0.8% | +1.6% | 5 of 12 | +1.1% |
| Grid, 3% steps | -2.7% | -0.3% | 5 of 12 | -0.1% |
| Grid, 1.5% steps | -10.3% | -1.5% | 3 of 12 | -0.8% |
| RSI dip <30, ±6% | -6.5% | -1.8% | 0 of 12 | -1.0% |
| RSI dip <30, ±3% | -8.5% | -2.9% | 0 of 12 | -1.4% |
| Coin flip | -27.2% | -17.9% | 0 of 12 | -13.3% |

The last two columns are for the low-cost runs. Cheaper trading cut the losses by two-thirds or more, but nothing made money, and every strategy did worse on average than holding the coin at the same fee. The volume is out of reach as well: the busiest strategy, the 1.5% grid, traded about ₹1.6 lakh a month per ₹5,000 bot, a third of what VIP 1 requires.

The first version of this test filled limit orders the way the normal-cost bots fill: at the candle price, and at the open when the price gapped past the order. That showed the grids and dip-buyers making +2.4% to +5.8% a window, and making money in 9 to 12 of the 12 windows. All of it came from fills a real order can't get. An order resting in the book fills at its own price even when the market gaps through it, and a bid at the last traded price only fills if sellers keep coming, which is when the price is still falling. Filling at the order's own price was enough to wipe out the grids' profit. Requiring the price to trade through an order instead of touching it made no difference to the grids, and took the dip-buyers from between -1.2% and +0.3% a window to a loss in all 12. The normal-cost grids get the same flattering gap fills, so their real results would be somewhat worse than the table at the top shows.

## Three mistakes that were caught

All three made a strategy look far better than it was, and all are easy to make:

- **The stale-price discount** (above). The profit only existed at prices nobody could trade at. The check that caught it was entering one candle later, at a price the strategy could really have got, and filtering on volume.
- **A tie that leaked the future.** The first funding study ranked coins by funding rate with a sort that broke ties by the next day's return. Many coins sit at exactly the base funding rate, so the ties were common, and the sort quietly put the next day's winners on top. That produced an "edge" of +1.1% to +2.4% a day. Ranking by funding alone brought it down to the 0.1% to 0.25% above. A day-by-day check against a direct simulation of the strategy showed the mismatch.
- **Fills a resting order can't get** ([above](#cheaper-trading)). The first low-cost test filled limit orders at the candle's open when the price gapped past them, and as soon as the price touched them. That alone made the grids and dip-buyers look profitable at the VIP fee. The check that caught it was filling each order at its own price, and only after the price traded through it.

## Limits of this research

- **One market.** Six months that were mostly falling, then a sharp rally. A strategy that failed here might work in a long bull or bear market.
- **Today's coins.** The 47 coins were chosen on 30 Sep 2026 for their volatility and trading on CoinDCX, so coins delisted during the period are missing, and coins that had just rallied are over-represented. That flatters buy & hold in the last window.
- **Candle fills.** Trades fill at candle prices plus half the spread measured on 30 Sep, so order-book depth and outages are not modelled. For thin coins that is optimistic.
- **Futures prices.** The simulation prices futures off CoinDCX's INR spot candles. Real INR-margined futures follow global perpetual prices, which are smoother on thin coins.
- **Tax.** Futures gains are taxed like spot sales, the strictest reading of the rules. If they were taxed as business income with losses set off, the futures results would be better, but the rule-based futures strategies lost before tax too.

## What would have to change

For a rule-based bot to make money here, at least one of these would have to be true:

- **Much cheaper trading, though that alone wasn't enough.** CoinDCX's INR spot fee falls from 0.5% to 0.42% above ₹2 lakh of trading a month, and to 0.17% or less at its VIP levels, which start at ₹5 lakh. At 0.17% and with limit orders the strategies here still lost ([above](#cheaper-trading)). Futures cost 0.05% a side, but the rule-based futures strategies lost before costs.
- **Losses that offset gains.** Under the current rules every winning trade is taxed on its own, which punishes strategies that win and lose often.
- **Liquid coins only.** On the thin coins the backtests promise profits the market would not have given.
- **An edge from outside the price chart.** Every rule here reads the same 15-minute and hourly prices that thousands of other bots read. That information is already in the price.

Until then, the approaches that did least badly were the ones that paid costs rarely: holding a few liquid coins, at most stepping aside while BTC is below its 30-day average. They make or lose roughly what the market does, which is exposure, not an edge.
