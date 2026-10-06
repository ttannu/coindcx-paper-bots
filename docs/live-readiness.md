# CoinDCX live-pilot evidence screen

Paper prices through 06 Oct 2026, 15:00 UTC (6.1 of 15 forward-paper days). **0 spot strategy families pass this screen.** No live trading is wired to this repository.

The historical inputs are 12 non-overlapping 15-day CoinDCX candle replays from 3 Apr to 30 Sep 2026, after the simulation's fees, spread, and estimated tax. They came from the local backtest output identified by SHA-256 `e6d3c6267cd897697f489b99bc1763fe2afa7bb795b6f1cecbdc75cb8b7cf81f`. Candle fills and tax assumptions are imperfect; these results cannot guarantee a future gain.

A family passes only if its historical mean and median are positive, at least 9 of 12 windows are profitable, at least 9 beat holding and the mean advantage is positive; its 15-day forward-paper median is profitable, covers at least 90% of the coins and beats holding on at least two-thirds of them; and its spot orders have no zero-volume, oversize, or unmatched fills and at most 5% use more than 10% of a candle's reported volume. These are conservative pilot criteria, not a statistical proof of skill. All orders still need live order-book and reconciliation tests before any real-money use.

| Spot family | Historical mean | Profitable windows | Beat holding, history | Forward median | Spot fill warnings | Above 10% volume | Pilot screen |
|---|---:|---:|---:|---:|---:|---:|---|
| grid 3% | -2.7% | 2/12 | 5/12 | -0.1% | 60/819 | 26.8% | blocked |
| RSI dip <25 ±3% | -3.9% | 0/12 | 3/12 | +0.0% | 10/46 | 47.8% | blocked |
| pump rider | -6.2% | 0/12 | 4/12 | +0.0% | 20/68 | 63.1% | blocked |
| RSI dip <30 ±6% | -6.5% | 0/12 | 2/12 | +0.0% | 52/151 | 66.7% | blocked |
| breakout 48/24h | -8.2% | 2/12 | 1/12 | -4.3% | 35/101 | 64.2% | blocked |
| RSI dip <30 ±3% | -8.5% | 0/12 | 2/12 | -0.1% | 52/157 | 62.8% | blocked |
| grid 1.5% | -10.3% | 0/12 | 2/12 | -4.5% | 338/3369 | 36.5% | blocked |
| breakout 20/10h | -15.4% | 1/12 | 0/12 | -7.3% | 91/214 | 71.2% | blocked |
| trend 24/96h | -26.1% | 0/12 | 0/12 | -14.8% | 192/476 | 71.0% | blocked |
| trend 12/48h | -36.0% | 0/12 | 0/12 | -18.8% | 304/653 | 75.5% | blocked |
| trend 6/24h | -47.6% | 0/12 | 0/12 | -26.6% | 446/959 | 75.9% | blocked |
| fast trend 5/20h | -71.4% | 0/12 | 0/12 | -47.6% | 843/2393 | 73.8% | blocked |
| fast trend 2/8h | -78.1% | 0/12 | 0/12 | -61.6% | 1200/3811 | 68.9% | blocked |

Futures are excluded because their simulated P&L uses CoinDCX INR spot candles, and funding is a fixed assumption rather than CoinDCX futures data. The VIP-fee twins are excluded because a ₹5,000 account has not demonstrated the trading volume needed for that fee tier. Coin flips and buy-and-hold are controls, not candidate strategies. The four later-start spot portfolios are evaluated separately in [the slow-strategy screen](strategy-lab.md); none had a positive historical mean after costs.

Before any live pilot, set a total capital limit and a daily loss limit, confirm the account's tax jurisdiction and fees, add an authenticated CoinDCX order client with idempotent order IDs and exchange reconciliation, and test it in dry-run mode. Passing this screen would permit review of a capped pilot; it would never authorize unlimited autonomous trading.
