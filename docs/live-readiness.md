# CoinDCX live-pilot evidence screen

Paper prices through 03 Oct 2026, 09:30 UTC (2.8 of 15 forward-paper days). **0 spot strategy families pass this screen.** No live trading is wired to this repository.

The historical inputs are 12 non-overlapping 15-day CoinDCX candle replays from 3 Apr to 30 Sep 2026, after the simulation's fees, spread, and estimated tax. They came from the local backtest output identified by SHA-256 `e6d3c6267cd897697f489b99bc1763fe2afa7bb795b6f1cecbdc75cb8b7cf81f`. Candle fills and tax assumptions are imperfect; these results cannot guarantee a future gain.

A family passes only if its historical mean and median are positive, at least 9 of 12 windows are profitable, at least 9 beat holding and the mean advantage is positive; its 15-day forward-paper median is profitable, covers at least 90% of the coins and beats holding on at least two-thirds of them; and its spot orders have no zero-volume, oversize, or unmatched fills and at most 5% use more than 10% of a candle's reported volume. These are conservative pilot criteria, not a statistical proof of skill. All orders still need live order-book and reconciliation tests before any real-money use.

| Spot family | Historical mean | Profitable windows | Beat holding, history | Forward median | Spot fill warnings | Above 10% volume | Pilot screen |
|---|---:|---:|---:|---:|---:|---:|---|
| grid 3% | -2.7% | 2/12 | 5/12 | -0.7% | 40/491 | 28.6% | blocked |
| RSI dip <25 ±3% | -3.9% | 0/12 | 3/12 | +0.0% | 8/36 | 41.7% | blocked |
| pump rider | -6.2% | 0/12 | 4/12 | +0.0% | 5/28 | 64.3% | blocked |
| RSI dip <30 ±6% | -6.5% | 0/12 | 2/12 | +0.0% | 30/98 | 60.2% | blocked |
| breakout 48/24h | -8.2% | 2/12 | 1/12 | +0.0% | 2/27 | 44.4% | blocked |
| RSI dip <30 ±3% | -8.5% | 0/12 | 2/12 | +0.0% | 29/102 | 54.9% | blocked |
| grid 1.5% | -10.3% | 0/12 | 2/12 | -4.2% | 195/2038 | 37.0% | blocked |
| breakout 20/10h | -15.4% | 1/12 | 0/12 | -3.7% | 24/72 | 61.8% | blocked |
| trend 24/96h | -26.1% | 0/12 | 0/12 | -7.3% | 77/208 | 73.2% | blocked |
| trend 12/48h | -36.0% | 0/12 | 0/12 | -6.6% | 84/221 | 72.9% | blocked |
| trend 6/24h | -47.6% | 0/12 | 0/12 | -11.6% | 149/372 | 74.1% | blocked |
| fast trend 5/20h | -71.4% | 0/12 | 0/12 | -22.5% | 276/854 | 74.1% | blocked |
| fast trend 2/8h | -78.1% | 0/12 | 0/12 | -36.1% | 526/1565 | 75.5% | blocked |

Futures are excluded because their simulated P&L uses CoinDCX INR spot candles, and funding is a fixed assumption rather than CoinDCX futures data. The VIP-fee twins are excluded because a ₹5,000 account has not demonstrated the trading volume needed for that fee tier. Coin flips and buy-and-hold are controls, not candidate strategies.

Before any live pilot, set a total capital limit and a daily loss limit, confirm the account's tax jurisdiction and fees, add an authenticated CoinDCX order client with idempotent order IDs and exchange reconciliation, and test it in dry-run mode. Passing this screen would permit review of a capped pilot; it would never authorize unlimited autonomous trading.
