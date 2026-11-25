"""Which momentum signal ranks next month's returns best, on a point-in-time universe.

At each month-end t the universe is the reference model's point-in-time list on that day
(mo.universe.members_on: the `n` most-traded EQ stocks priced at ₹50 or more with a year of
history), or, given a turnover table instead, the `n` most-traded stocks over the 126 trading
days to t (members_at). Every signal uses prices up to t only; the outcome is each stock's return
from t to the next month-end. A stock with no price at the next month-end (delisted or
suspended) counts as 0, as if sold at its last price.
"""

import numpy as np
import pandas as pd

from mo.momentum import TRADING_DAYS, momentum, month_end_prices
from mo.universe import members_at, members_on

SIGNALS = ("12-1", "6-1", "3-0", "12-0", "NSE-style volatility-adjusted")


def _ratio_vol(daily: pd.DataFrame, monthly: pd.DataFrame, min_days: int = 200) -> pd.DataFrame:
    logr = np.log(daily).diff()
    vol = logr.rolling("365D", min_periods=min_days).std() * np.sqrt(TRADING_DAYS)
    return vol.reindex(monthly.index)


def _nse_score(r6: pd.Series, r12: pd.Series) -> pd.Series:
    """Average of the two z-scores (within the given stocks) mapped to NSE's positive score."""
    ok = r6.notna() & r12.notna()
    z = sum(((r - r[ok].mean()) / r[ok].std()).where(ok) for r in (r6, r12)) / 2
    return z.where(z < 0, 1 + z).where(z >= 0, 1 / (1 - z))


def scores_at(monthly, vol, t, members) -> dict[str, pd.Series]:
    """Every signal for `members` at month-end t (only prices to t)."""
    m = monthly.loc[:t, members]
    out = {
        "12-1": momentum(m, 12, 1).iloc[-1],
        "6-1": momentum(m, 6, 1).iloc[-1],
        "3-0": momentum(m, 3, 0).iloc[-1],
        "12-0": momentum(m, 12, 0).iloc[-1],
    }
    v = vol.loc[t, members]
    out["NSE-style volatility-adjusted"] = _nse_score(
        momentum(m, 6, 0).iloc[-1] / v, momentum(m, 12, 0).iloc[-1] / v
    )
    return out


def signal_panel(
    prices: pd.DataFrame,
    turnover: pd.DataFrame | None = None,
    n: int = 200,
    start: str = "2014-01-01",
    universe: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """One row per (month-end t, stock in that month's universe): every signal at t and the next
    month's return."""
    monthly = month_end_prices(prices)
    vol = _ratio_vol(prices, monthly)
    nxt = (monthly.shift(-1) / monthly - 1).fillna(0.0)
    rows = []
    dates = monthly.index[(monthly.index >= start)][:-1]  # the last month has no next month
    for t in dates:
        pool = (
            members_on(universe, t, n)
            if universe is not None
            else members_at(turnover, t + pd.Timedelta(days=1), n)
        )
        members = [s for s in pool if s in monthly.columns and pd.notna(monthly.at[t, s])]
        sc = pd.DataFrame(scores_at(monthly, vol, t, members))
        sc["next"] = nxt.loc[t, members]
        sc["date"] = t
        rows.append(sc.rename_axis("symbol").reset_index())
    return pd.concat(rows, ignore_index=True)


def evaluate(panel: pd.DataFrame, signal: str, top: int = 20) -> dict:
    """Monthly rank IC (Spearman of signal vs next return), top-`top` minus the universe average,
    top-quintile minus bottom-quintile, and how much of the top list changes each month."""
    ics, excess, spread, prev, change, dates = [], [], [], None, [], []
    for t, g in panel.groupby("date"):
        g = g.dropna(subset=[signal])
        if len(g) < 50:
            continue
        ics.append(g[signal].rank().corr(g["next"].rank()))
        best = g.nlargest(top, signal)
        excess.append(best["next"].mean() - g["next"].mean())
        q = pd.qcut(g[signal].rank(method="first"), 5, labels=False)
        spread.append(g.loc[q == 4, "next"].mean() - g.loc[q == 0, "next"].mean())
        names = set(best["symbol"])
        if prev is not None:
            change.append(1 - len(names & prev) / top)
        prev = names
        dates.append(t)
    ics, excess, spread = map(np.array, (ics, excess, spread))
    return {
        "months": len(ics),
        "IC": float(ics.mean()),
        "IC t": float(ics.mean() / ics.std(ddof=1) * np.sqrt(len(ics))),
        "top minus universe, a year": float(excess.mean() * 12),
        "top beat universe, share of months": float((excess > 0).mean()),
        "Q5 minus Q1, a year": float(spread.mean() * 12),
        "top list changed a month": float(np.mean(change)),
        "series": pd.Series(excess, index=pd.DatetimeIndex(dates)),
    }
