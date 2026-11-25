"""After-tax returns of the momentum portfolio for an Indian resident individual.

Rates (FY 2026-27, unchanged by Budget 2026): listed equity sold after more than 12 months is
long-term, taxed at 12.5% on gains above ₹1.25 lakh a financial year; sold within 12 months,
short-term at 20%. 4% health and education cess on the tax; surcharge left out. Today's rates are
applied to every year (they were lower before July 2024), so the past is taxed as it would be now.

Set-off (simplified): within a financial year (April to March) short-term losses reduce short-term
gains, then long-term gains; long-term losses reduce only long-term gains; what is left carries
forward (without the 8-year limit). Tax for a year is paid out of the portfolio at the end of
March by shrinking every holding in proportion, without realising gains on that sale (which
slightly understates tax). Lots are sold first-in, first-out.

The simulator holds shares and rupees, so its pre-tax path must match mo.momentum.backtest with the
same rule (tested).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from mo.momentum import _backtest_arrays

STCG, LTCG, LTCG_EXEMPT, CESS = 0.20, 0.125, 125_000.0, 0.04


@dataclass
class Ledger:
    lots: dict = field(default_factory=dict)  # stock -> list of [buy date, shares, cost per share]
    st: float = 0.0  # realised this FY
    lt: float = 0.0
    carry_st: float = 0.0  # losses carried forward (positive numbers)
    carry_lt: float = 0.0
    paid: float = 0.0
    st_total: float = 0.0  # all realised short- and long-term gains, net, before set-off
    lt_total: float = 0.0

    def buy(self, stock, date, shares, price):
        self.lots.setdefault(stock, []).append([date, shares, price])

    def sell(self, stock, date, shares, price):
        lots = self.lots.get(stock, [])
        while shares > 1e-12 and lots:
            d, q, c = lots[0]
            take = min(q, shares)
            gain = take * (price - c)
            if (date - d).days > 365:
                self.lt += gain
                self.lt_total += gain
            else:
                self.st += gain
                self.st_total += gain
            lots[0][1] -= take
            shares -= take
            if lots[0][1] <= 1e-12:
                lots.pop(0)

    def year_end_tax(self) -> float:
        """Tax due for the financial year just ended; updates carried losses."""
        st, lt = self.st, self.lt
        st -= self.carry_st
        lt -= self.carry_lt
        self.carry_st = self.carry_lt = 0.0
        if st < 0:  # short-term loss can reduce long-term gains
            lt += st
            st = 0.0
            if lt < 0:
                self.carry_st, lt = -lt, 0.0
        if lt < 0:
            self.carry_lt, lt = -lt, 0.0
        tax = (STCG * st + LTCG * max(lt - LTCG_EXEMPT, 0.0)) * (1 + CESS)
        self.st = self.lt = 0.0
        self.paid += tax
        return tax

    def liquidation_tax(self, date, prices: dict) -> float:
        """Tax if everything were sold at `date` (the year's gains so far included)."""
        for s in list(self.lots):
            q = sum(lot[1] for lot in self.lots[s])
            if q > 0 and np.isfinite(prices.get(s, np.nan)):
                self.sell(s, date, q, prices[s])
        return self.year_end_tax()


def simulate(
    monthly: pd.DataFrame,
    score: pd.DataFrame,
    capital: float = 1_000_000.0,
    top_n: int = 20,
    rebalance_every: int = 1,
    keep_rank: int | None = None,
    costs: tuple | None = None,
    tax: bool = True,
) -> dict:
    """Rupee path of the top-N rule (same choices as `backtest`), with costs taken from the
    portfolio at each rebalance and tax paid every 31 March. Returns monthly values before and
    after tax, tax paid, and the value after selling everything at the end."""
    score = score.reindex(index=monthly.index, columns=monthly.columns)
    px = monthly.to_numpy(float)
    ref = _backtest_arrays(
        px,
        score.to_numpy(float),
        top_n,
        rebalance_every,
        0.0,
        keep_rank=keep_rank,
        costs=costs,
        return_targets=True,
    )
    dates = monthly.index
    cols = list(monthly.columns)
    i0 = ref["start"]
    targets = dict(zip(ref["rebalances"], ref["targets"], strict=True))
    ledger = Ledger()
    shares = np.zeros(len(cols))
    cash = capital
    last_px = np.full(len(cols), np.nan)
    values = []
    for i in range(i0, len(dates)):
        p = px[i]
        live = np.isfinite(p)
        last_px[live] = p[live]
        value = cash + float(np.nansum(shares * last_px))
        if i in targets:
            if costs is not None:
                fee = ref["cost"][ref["rebalances"].index(i)] * value
            else:
                fee = 0.0
            w_target = targets[i]
            new_value = value - fee
            target_shares = np.where(
                w_target > 0, w_target * new_value / np.where(live, p, np.nan), 0.0
            )
            target_shares = np.nan_to_num(target_shares)
            for j in np.flatnonzero(np.abs(target_shares - shares) > 1e-12):
                d = target_shares[j] - shares[j]
                price = last_px[j]
                if d < 0:
                    ledger.sell(cols[j], dates[i], -d, price)
                else:
                    ledger.buy(cols[j], dates[i], d, price)
            cash = new_value - float(np.nansum(target_shares * np.where(live, p, last_px)))
            shares = target_shares
            value = new_value
        if tax and dates[i].month == 3:
            due = ledger.year_end_tax()
            if due > 0:
                scale = (value - due) / value
                shares *= scale
                cash *= scale
                for lots in ledger.lots.values():
                    for lot in lots:
                        lot[1] *= scale
                value -= due
        values.append(value)
    out = pd.Series(values, index=dates[i0:], name="after tax" if tax else "before tax")
    final_prices = dict(zip(cols, last_px, strict=True))
    liq = ledger.liquidation_tax(dates[-1], final_prices) if tax else 0.0
    return {
        "value": out,
        "tax paid": ledger.paid,
        "after selling": out.iloc[-1] - liq,
        "short-term gains": ledger.st_total,
        "long-term gains": ledger.lt_total,
    }


def buy_and_hold_after_tax(prices: pd.Series, capital: float = 1_000_000.0) -> dict:
    """A fund or index bought once and sold at the end: no tax until the sale, then long-term
    gains tax on the whole gain above one year's exemption."""
    p = prices.dropna()
    end = capital * p.iloc[-1] / p.iloc[0]
    gain = end - capital
    held_long = (p.index[-1] - p.index[0]).days > 365
    rate = LTCG if held_long else STCG
    exempt = LTCG_EXEMPT if held_long else 0.0
    tax = rate * max(gain - exempt, 0.0) * (1 + CESS)
    return {"before tax": end, "after selling": end - tax}
