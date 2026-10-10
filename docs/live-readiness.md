# CoinDCX live-pilot evidence screen

Paper prices through 10 Oct 2026, 02:00 UTC (9.5 of 15 forward-paper days). **0 spot strategy families pass this screen.** No live trading is wired to this repository.

The historical inputs are 12 non-overlapping 15-day CoinDCX candle replays from 3 Apr to 30 Sep 2026, after the simulation's fees, spread, and estimated tax. They came from the local backtest output identified by SHA-256 `e6d3c6267cd897697f489b99bc1763fe2afa7bb795b6f1cecbdc75cb8b7cf81f`. Candle fills and tax assumptions are imperfect; these results cannot guarantee a future gain.

A family passes only if its historical mean and median are positive, at least 9 of 12 windows are profitable, at least 9 beat holding and the mean advantage is positive; its 15-day forward-paper median is profitable, covers at least 90% of the coins and beats holding on at least two-thirds of them; and its spot orders have no zero-volume, oversize, or unmatched fills and at most 5% use more than 10% of a candle's reported volume. These are conservative pilot criteria, not a statistical proof of skill. All orders still need live order-book and reconciliation tests before any real-money use.

| Spot family | Historical mean | Profitable windows | Beat holding, history | Forward median | Spot fill warnings | Above 10% volume | Pilot screen |
|---|---:|---:|---:|---:|---:|---:|---|
| grid 3% | -2.7% | 2/12 | 5/12 | -3.2% | 84/1251 | 24.9% | blocked |
| RSI dip <25 ±3% | -3.9% | 0/12 | 3/12 | -2.8% | 29/186 | 38.8% | blocked |
| pump rider | -6.2% | 0/12 | 4/12 | +0.0% | 29/89 | 66.3% | blocked |
| RSI dip <30 ±6% | -6.5% | 0/12 | 2/12 | -5.5% | 119/390 | 60.6% | blocked |
| breakout 48/24h | -8.2% | 2/12 | 1/12 | -5.2% | 43/125 | 66.9% | blocked |
| RSI dip <30 ±3% | -8.5% | 0/12 | 2/12 | -8.0% | 120/478 | 54.1% | blocked |
| grid 1.5% | -10.3% | 0/12 | 2/12 | -12.7% | 449/4242 | 37.4% | blocked |
| breakout 20/10h | -15.4% | 1/12 | 0/12 | -10.2% | 119/279 | 71.4% | blocked |
| trend 24/96h | -26.1% | 0/12 | 0/12 | -15.8% | 229/553 | 72.4% | blocked |
| trend 12/48h | -36.0% | 0/12 | 0/12 | -20.2% | 351/762 | 75.9% | blocked |
| trend 6/24h | -47.6% | 0/12 | 0/12 | -34.7% | 571/1241 | 75.4% | blocked |
| fast trend 5/20h | -71.4% | 0/12 | 0/12 | -57.0% | 1030/3063 | 71.5% | blocked |
| fast trend 2/8h | -78.1% | 0/12 | 0/12 | -69.8% | 1482/5149 | 65.9% | blocked |

Futures are excluded because their simulated P&L uses CoinDCX INR spot candles, and funding is a fixed assumption rather than CoinDCX futures data. The VIP-fee twins are excluded because a ₹5,000 account has not demonstrated the trading volume needed for that fee tier. Coin flips and buy-and-hold are controls, not candidate strategies. The four later-start spot portfolios are evaluated separately in [the slow-strategy screen](strategy-lab.md); none had a positive historical mean after costs.

Before any live pilot, set a total capital limit and a daily loss limit, confirm the account's tax jurisdiction and fees, add an authenticated CoinDCX order client with idempotent order IDs and exchange reconciliation, and test it in dry-run mode. Passing this screen would permit review of a capped pilot; it would never authorize unlimited autonomous trading.
