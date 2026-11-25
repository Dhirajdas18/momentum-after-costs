"""Momentum crashes and two ways of stepping aside, applied to a monthly return series.

Both overlays decide at month-end t from data up to t and apply to month t+1. Money not in the
portfolio earns cash at `rf` a year. Moving between the portfolio and cash costs `switch_cost` per
rupee moved (both ways counted: selling the stocks and buying them back later). Tax on the extra
sales is left out.
"""

import numpy as np
import pandas as pd

RF = 0.065
SWITCH_COST = 0.0017  # about one side of delivery charges plus slippage (mo.momentum.FEES_* + 5 bp)


def market_filter(
    r: pd.Series, market: pd.Series, months: int = 10, rf: float = RF, cost: float = SWITCH_COST
) -> tuple[pd.Series, pd.Series]:
    """Hold the portfolio in month t+1 only if the market's month-end level at t is above its
    average of the last `months` month-ends (t included); otherwise hold cash. Returns the new
    monthly returns and the exposure (1 or 0) used in each month."""
    m = market.reindex(r.index.union(market.index)).ffill()
    above = (m > m.rolling(months).mean()).astype(float)
    exposure = above.shift(1).reindex(r.index).fillna(1.0)
    return _apply(r, exposure, rf, cost), exposure


def vol_scale(
    r: pd.Series,
    target: float = 0.20,
    lookback: int = 12,
    rf: float = RF,
    cost: float = SWITCH_COST,
    cap: float = 1.0,
) -> tuple[pd.Series, pd.Series]:
    """Hold target / (the portfolio's annualised volatility over the `lookback` months to t),
    at most `cap` (1: no borrowing), in month t+1; the rest in cash. Full exposure until there is
    enough history."""
    vol = r.rolling(lookback).std() * np.sqrt(12)
    exposure = (target / vol).clip(upper=cap).shift(1).fillna(1.0)
    return _apply(r, exposure, rf, cost), exposure


def _apply(r, exposure, rf, cost):
    cash = rf / 12
    moved = exposure.diff().abs().fillna(0.0)
    return exposure * r + (1 - exposure) * cash - cost * moved


def drawdowns(equity: pd.Series, top: int = 5) -> pd.DataFrame:
    """The `top` deepest peak-to-trough falls: peak date, trough date, depth, recovery date (NaT if
    not recovered)."""
    peak = equity.cummax()
    dd = equity / peak - 1
    out, used = [], pd.Series(False, index=equity.index)
    for _ in range(top):
        d = dd.where(~used)
        if d.min() >= 0 or d.isna().all():
            break
        trough = d.idxmin()
        pk = equity.loc[:trough].idxmax()
        after = equity.loc[trough:]
        rec = after[after >= equity.loc[pk]]
        end = rec.index[0] if len(rec) else equity.index[-1]
        used.loc[pk:end] = True
        out.append(
            {
                "peak": pk,
                "trough": trough,
                "depth": float(dd.loc[trough]),
                "recovered": rec.index[0] if len(rec) else pd.NaT,
            }
        )
    return pd.DataFrame(out)
