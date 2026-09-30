import math


def floor_step(qty, step):
    return round(math.floor(qty / step + 1e-9) * step, 12)


class _Account:
    def __init__(self, state, costs, markets, log):
        self.s = state
        self.costs = costs
        self.markets = markets
        self.log = log

    @property
    def active(self):
        return self.s["status"] == "active"

    @property
    def cash(self):
        return self.s["cash"]

    @property
    def memo(self):
        return self.s["memo"]

    def mark(self, prices, t):
        value = self.liquidation_value(prices, t)
        self.s["last_value"] = value
        self.s["peak"] = max(self.s["peak"], value)
        if self.s["peak"] > 0:
            self.s["max_dd"] = min(1.0, max(self.s["max_dd"], 1 - value / self.s["peak"]))
        return value


class SpotAccount(_Account):
    """Cost basis excludes fees: Indian VDA rules only allow the purchase price as a deduction."""

    kind = "spot"

    @staticmethod
    def fresh(capital):
        return {
            "kind": "spot", "capital": float(capital), "cash": float(capital), "positions": {}, "fees": 0.0,
            "tds_credit": 0.0, "tax_due": 0.0, "sell_volume": 0.0,
            "trades": 0, "wins": 0, "losses": 0, "last_value": float(capital),
            "peak": float(capital), "max_dd": 0.0, "status": "active", "memo": {},
        }

    def position(self, pair):
        return self.s["positions"].get(pair)

    def equity(self, prices):
        return self.s["cash"] + sum(p["qty"] * prices[pair] for pair, p in self.s["positions"].items())

    def _fee_rate(self):
        return self.costs["spot_fee_rate"] * (1 + self.costs["gst_rate"])

    def buy(self, pair, budget, price, t, reason):
        market = self.markets[pair]
        budget = min(budget, self.s["cash"])
        fill = price * (1 + self.costs["slippage"])
        qty = floor_step(budget / (fill * (1 + self._fee_rate())), market["step"])
        value = qty * fill
        if qty <= 0 or qty < market["min_qty"] or value < market["min_notional"]:
            return 0.0
        fee = value * self._fee_rate()
        self.s["cash"] -= value + fee
        self.s["fees"] += fee
        pos = self.s["positions"].setdefault(pair, {"qty": 0.0, "cost": 0.0, "fee": 0.0, "t": t})
        pos["qty"] += qty
        pos["cost"] += value
        pos["fee"] += fee
        self.log({"t": t, "side": "BUY", "pair": pair, "qty": qty, "price": fill, "value": value,
                  "fee": fee, "tds": 0.0, "pnl": None, "tax": 0.0, "reason": reason})
        return qty

    def sell(self, pair, price, t, reason, qty=None):
        pos = self.s["positions"].get(pair)
        if not pos:
            return 0.0
        qty = pos["qty"] if qty is None else min(qty, pos["qty"])
        share = qty / pos["qty"]
        fill = price * (1 - self.costs["slippage"])
        value = qty * fill
        fee = value * self._fee_rate()
        cost = pos["cost"] * share
        buy_fee = pos["fee"] * share
        gain = value - cost
        tax = gain * self.costs["tax_rate"] if gain > 0 else 0.0
        self.s["sell_volume"] += value
        tds = value * self.costs["tds_rate"] if self.s["sell_volume"] > self.costs["tds_threshold_inr"] else 0.0
        self.s["cash"] += value - fee - tds
        self.s["fees"] += fee
        self.s["tds_credit"] += tds
        self.s["tax_due"] += tax
        pnl = value - cost - buy_fee - fee - tax
        self.s["trades"] += 1
        self.s["wins" if pnl > 0 else "losses"] += 1
        if share > 0.999999:
            del self.s["positions"][pair]
        else:
            pos["qty"] -= qty
            pos["cost"] -= cost
            pos["fee"] -= buy_fee
        self.log({"t": t, "side": "SELL", "pair": pair, "qty": qty, "price": fill, "value": value,
                  "fee": fee, "tds": tds, "pnl": pnl, "tax": tax, "reason": reason})
        return qty

    def liquidation_value(self, prices, t=None):
        value = self.s["cash"] + self.s["tds_credit"] - self.s["tax_due"]
        for pair, pos in self.s["positions"].items():
            proceeds = pos["qty"] * prices[pair] * (1 - self.costs["slippage"])
            gain = proceeds - pos["cost"]
            value += proceeds * (1 - self._fee_rate()) - (gain * self.costs["tax_rate"] if gain > 0 else 0.0)
        return value


class FuturesAccount(_Account):
    kind = "futures"

    @staticmethod
    def fresh(capital):
        return {
            "kind": "futures", "capital": float(capital), "cash": float(capital), "position": None,
            "fees": 0.0, "funding": 0.0, "tax_due": 0.0, "trades": 0, "wins": 0, "losses": 0,
            "liquidations": 0, "last_value": float(capital),
            "peak": float(capital), "max_dd": 0.0, "status": "active", "memo": {},
        }

    @property
    def open_position(self):
        return self.s["position"]

    def _fee_rate(self):
        return self.costs["futures_fee_rate"] * (1 + self.costs["gst_rate"])

    @staticmethod
    def _pnl(pos, price):
        direction = 1 if pos["side"] == "long" else -1
        return (price - pos["entry"]) * pos["qty"] * direction

    def _funding(self, pos, t):
        hours = max(0.0, (t - pos["t"]) / 3600000.0)
        return pos["qty"] * pos["entry"] * self.costs["funding_rate_per_8h"] * hours / 8

    def open(self, pair, side, leverage, price, t, reason):
        direction = 1 if side == "long" else -1
        fill = price * (1 + direction * self.costs["futures_slippage"])
        margin = self.s["cash"] / (1 + leverage * self._fee_rate())
        notional = margin * leverage
        if notional < self.markets[pair]["min_notional"]:
            return False
        fee = notional * self._fee_rate()
        mmr = self.costs["maintenance_margin"]
        if side == "long":
            liq = fill * (1 - 1.0 / leverage + mmr)
        else:
            liq = fill * (1 + 1.0 / leverage - mmr)
        self.s["cash"] = max(0.0, self.s["cash"] - margin - fee)
        self.s["fees"] += fee
        self.s["position"] = {"pair": pair, "side": side, "qty": notional / fill, "entry": fill,
                              "margin": margin, "fee": fee, "liq": liq, "t": t, "leverage": leverage}
        self.log({"t": t, "side": "OPEN " + side.upper(), "pair": pair, "qty": notional / fill, "price": fill,
                  "value": notional, "fee": fee, "tds": 0.0, "pnl": None, "tax": 0.0,
                  "reason": "%s, %gx, liquidation at %.0f" % (reason, leverage, liq)})
        return True

    def check_liquidation(self, candle, t):
        pos = self.s["position"]
        if not pos:
            return False
        hit = candle["l"] <= pos["liq"] if pos["side"] == "long" else candle["h"] >= pos["liq"]
        if not hit:
            return False
        self.s["position"] = None
        self.s["trades"] += 1
        self.s["losses"] += 1
        self.s["liquidations"] += 1
        self.log({"t": t, "side": "LIQUIDATED", "pair": pos["pair"], "qty": pos["qty"], "price": pos["liq"],
                  "value": pos["qty"] * pos["liq"], "fee": 0.0, "tds": 0.0, "pnl": -(pos["margin"] + pos["fee"]),
                  "tax": 0.0, "reason": "%s position lost its whole margin" % pos["side"]})
        return True

    def close(self, price, t, reason):
        pos = self.s["position"]
        direction = 1 if pos["side"] == "long" else -1
        fill = price * (1 - direction * self.costs["futures_slippage"])
        funding = self._funding(pos, t)
        gain = self._pnl(pos, fill) - funding
        fee = pos["qty"] * fill * self._fee_rate()
        tax = gain * self.costs["tax_rate"] if gain > 0 else 0.0
        self.s["cash"] += max(0.0, pos["margin"] + gain - fee)
        self.s["fees"] += fee
        self.s["funding"] += funding
        self.s["tax_due"] += tax
        net = gain - fee - pos["fee"] - tax
        self.s["trades"] += 1
        self.s["wins" if net > 0 else "losses"] += 1
        self.s["position"] = None
        self.log({"t": t, "side": "CLOSE " + pos["side"].upper(), "pair": pos["pair"], "qty": pos["qty"],
                  "price": fill, "value": pos["qty"] * fill, "fee": fee, "tds": 0.0, "pnl": net, "tax": tax,
                  "reason": reason})

    def liquidation_value(self, prices, t):
        value = self.s["cash"] - self.s["tax_due"]
        pos = self.s["position"]
        if pos:
            direction = 1 if pos["side"] == "long" else -1
            fill = prices[pos["pair"]] * (1 - direction * self.costs["futures_slippage"])
            gain = self._pnl(pos, fill) - self._funding(pos, t)
            fee = pos["qty"] * fill * self._fee_rate()
            value += max(0.0, pos["margin"] + gain - fee) - (gain * self.costs["tax_rate"] if gain > 0 else 0.0)
        return value

    def mark(self, prices, t):
        value = _Account.mark(self, prices, t)
        if self.s["position"] is None and self.s["cash"] < self.costs["min_trade_inr"]:
            self.s["status"] = "busted"
        return value
