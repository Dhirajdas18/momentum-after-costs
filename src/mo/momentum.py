"""Core momentum maths: month-end prices, momentum scores, NSE-style volatility-adjusted score,
and a long-only top-N backtest with costs. numpy and pandas only.

Conventions:
- Monthly frames are month x symbol, indexed by the last trading date of each month in the data
  (the latest row may be a part month, up to the last close).
- A score at month-end t uses prices up to and including t only; trades happen at t's close and
  earn returns from t to t+1.
"""

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def month_end_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """The last available price of each calendar month, per stock, indexed by the month's last
    trading date in `prices`. A stock with no price at all in a month gets NaN for it."""
    months = prices.index.to_period("M")
    out = prices.groupby(months).last()
    out.index = prices.index.to_series().groupby(months).max().to_numpy()
    out.index.name = prices.index.name
    return out


def momentum(monthly: pd.DataFrame, lookback: int = 12, skip: int = 1) -> pd.DataFrame:
    """Total return from month t - lookback to month t - skip, known at month-end t.

    12-1 (the default) is the return from t-12 to t-1: the latest month is skipped because
    one-month returns tend to reverse. skip=0 includes it. NaN where either price is missing.
    """
    if not 0 <= skip < lookback:
        raise ValueError("need 0 <= skip < lookback")
    return monthly.shift(skip) / monthly.shift(lookback) - 1


def vol_adjusted_score(
    daily: pd.DataFrame, monthly_dates: pd.Index | None = None, min_days: int = 200
) -> pd.DataFrame:
    """A Nifty200 Momentum 30 style score at each month-end (an approximation of NSE's published
    methodology, not a replica of the index):

    1. 6-month and 12-month price returns to month-end t (no month skipped).
    2. Each divided by the annualised standard deviation of daily log returns over the 365
       calendar days to t (at least `min_days` returns, else NaN).
    3. Each ratio turned into a z-score across the stocks that have both ratios that month
       (sample standard deviation), and the two z-scores averaged.
    4. The average z mapped to a positive normalised score: 1 + z if z >= 0, 1 / (1 - z) if not.

    NSE also weights constituents by score x free-float market cap, caps weights, and reviews
    twice a year with buffers; none of that is here. `monthly_dates` defaults to every month-end
    of `daily` and must be a subset of them.
    """
    monthly = month_end_prices(daily)
    dates = monthly.index if monthly_dates is None else pd.Index(monthly_dates)
    logr = np.log(daily).diff()
    vol = logr.rolling("365D", min_periods=min_days).std() * np.sqrt(TRADING_DAYS)
    vol = vol.reindex(monthly.index)
    ratios = [momentum(monthly, m, 0) / vol for m in (6, 12)]
    both = ratios[0].notna() & ratios[1].notna()
    zs = []
    for r in ratios:
        r = r.where(both)
        zs.append(r.sub(r.mean(axis=1), axis=0).div(r.std(axis=1), axis=0))
    z = (zs[0] + zs[1]) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        score = np.where(z >= 0, 1 + z, 1 / (1 - z))  # NaN stays NaN
    return pd.DataFrame(score, index=z.index, columns=z.columns).reindex(dates)


def _cap_weights(w: np.ndarray, cap: float) -> np.ndarray:
    """Scale weights (summing to 1) so none exceeds `cap`, handing the excess to the rest in
    proportion (repeated until it fits; needs cap * count >= 1)."""
    w = w.copy()
    for _ in range(50):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        free = ~over & (w > 0)
        w[free] += excess * w[free] / w[free].sum()
    return w


def _backtest_arrays(
    px: np.ndarray,
    sc: np.ndarray,
    top_n: int,
    every: int,
    cost: float,
    tilt: np.ndarray | None = None,
    group: np.ndarray | None = None,
    max_per_group: int | None = None,
    max_weight: float | None = None,
    keep_rank: int | None = None,
    costs: tuple[float, float, float, float] | None = None,
    return_targets: bool = False,
) -> dict:
    """Array core of `backtest` (rows are months, columns stocks; NaN for missing). Optional:
    `tilt` (same shape) sets target weights in proportion to its value for the picked stocks
    (missing or non-positive -> equal weight for that month); `group` (one label per column) with
    `max_per_group` skips a stock once its group already has that many picks; `max_weight` caps
    any one weight. `keep_rank` (hold band): a held stock stays, untouched, while its rank is within
    `keep_rank`; only the stocks that fall out are sold and the freed money is split equally among
    the best-ranked stocks not held, so winners are not trimmed. `costs` = (buy rate, sell rate, ₹
    per stock sold, starting capital in ₹): replaces `cost` with buys and sells charged separately
    and a fixed charge for every stock sold (against the capital grown at the net return)."""
    t_len, n = px.shape
    valid = ~np.isnan(sc) & ~np.isnan(px)
    starts = [i for i in range(t_len - 1) if valid[i].any()]
    if not starts:
        raise ValueError("no month with a valid score and price before the last month")
    i0 = starts[0]
    rebal = set(range(i0, t_len - 1, every))
    w = np.zeros(n)
    gross, net, turn, cost_log, picks, rebal_rows, targets = [], [], [], [], [], [], []
    eq_g, eq_n = [1.0], [1.0]
    pending = 0.0  # cost of the last rebalance, charged to the month that follows it
    for i in range(i0, t_len):
        if i > i0:
            with np.errstate(invalid="ignore", divide="ignore"):
                r = px[i] / px[i - 1] - 1
            r[np.isnan(r)] = 0.0  # missing start or end price: cash at 0 for the month
            g = float(w @ r)
            gross.append(g)
            net.append((1 + g) * (1 - pending) - 1)
            eq_g.append(eq_g[-1] * (1 + g))
            eq_n.append(eq_n[-1] * (1 + net[-1]))
            pending = 0.0
            if 1 + g != 0:
                w = w * (1 + r) / (1 + g)  # buy and hold: weights drift with prices
        if i in rebal:
            cand = np.flatnonzero(valid[i])
            order = cand[np.argsort(-sc[i, cand], kind="stable")]  # ties: column order
            if group is None or max_per_group is None:
                pick = order[:top_n]
            else:
                taken, chosen = {}, []
                for j in order:
                    k = group[j]
                    if k is not None and taken.get(k, 0) >= max_per_group:
                        continue
                    taken[k] = taken.get(k, 0) + 1
                    chosen.append(j)
                    if len(chosen) == top_n:
                        break
                pick = np.array(chosen, dtype=int)
            target = np.zeros(n)
            held = np.flatnonzero(w > 0)
            if keep_rank is not None and (
                tilt is not None or group is not None or max_weight is not None
            ):
                raise ValueError("keep_rank can't be combined with tilt, group or max_weight")
            if keep_rank is not None and len(held):
                rank = {j: r for r, j in enumerate(order)}
                keep = [j for j in held if rank.get(j, 10**9) < keep_rank]
                keep = sorted(keep, key=lambda j: rank[j])[:top_n]
                new = [j for j in order if j not in set(keep)][: top_n - len(keep)]
                target[keep] = w[keep]
                free = 1.0 - float(w[keep].sum())
                if new:
                    target[new] = free / len(new)
                elif keep:
                    target[keep] = w[keep] / w[keep].sum()
                pick = np.array(keep + new, dtype=int)
            elif len(pick):
                target[pick] = 1.0 / len(pick)
                if tilt is not None:
                    t = tilt[i, pick]
                    if np.all(np.isfinite(t)) and np.all(t > 0):
                        target[pick] = t / t.sum()
                if max_weight is not None:
                    target[pick] = _cap_weights(target[pick], max_weight)
            tv = float(np.abs(target - w).sum())
            turn.append(tv)
            if costs is None:
                c = cost * tv
            else:
                buy_rate, sell_rate, per_sell, capital = costs
                d = target - w
                sold = int(np.sum(d < -1e-9))
                c = (
                    buy_rate * float(d[d > 0].sum())
                    + sell_rate * float(-d[d < 0].sum())
                    + sold * per_sell / (capital * eq_n[-1])
                )
            cost_log.append(c)
            pending = c
            picks.append(pick.tolist())
            targets.append(target.copy())
            rebal_rows.append(i)
            w = target
    return {
        "start": i0,
        "gross": np.array(gross),
        "net": np.array(net),
        "equity_gross": np.array(eq_g),
        "equity_net": np.array(eq_n),
        "turnover": np.array(turn),
        "cost": np.array(cost_log),
        "holdings": picks,
        "rebalances": rebal_rows,
        **({"targets": targets} if return_targets else {}),
    }


def backtest(
    monthly_prices: pd.DataFrame,
    score: pd.DataFrame,
    top_n: int = 20,
    rebalance_every: int = 1,
    cost_per_side: float = 0.003,
    weights: str = "equal",
    tilt: pd.DataFrame | None = None,
    group: dict | None = None,
    max_per_group: int | None = None,
    max_weight: float | None = None,
    keep_rank: int | None = None,
    costs: tuple[float, float, float, float] | None = None,
) -> dict:
    """Long-only top-N momentum portfolio, rebalanced every `rebalance_every` months.

    At each rebalance month-end t (the first month with any valid score, then every
    `rebalance_every` months, never the last month), rank the stocks with both a score and a
    price at t, buy the top `top_n` in equal weight (all of them if fewer qualify), and hold.
    Between rebalances weights drift with prices. Trading costs are `cost_per_side` times the
    value traded (sum of |target weight - drifted weight|, buys and sells), charged to the
    month after the trade; the first rebalance buys from cash (turnover 1).

    A held stock with no price at the start or end of a month (delisted, suspended, or a data
    gap) earns 0 that month, as if held in cash at its last price; at the next rebalance it is
    sold at that carried value if it no longer qualifies.

    No look-ahead: holdings chosen at t depend only on `score` and prices at rows <= t, so
    the caller must pass a score built from data up to each row (as `momentum` does).

    Returns a dict of pandas objects: gross and net monthly returns, equity (gross, net; 1 at
    the first rebalance), turnover and cost per rebalance, and holdings per rebalance.
    """
    if weights != "equal":
        raise ValueError("weights is 'equal'; pass `tilt` for other weightings")
    score = score.reindex(index=monthly_prices.index, columns=monthly_prices.columns)
    t_arr = None
    if tilt is not None:
        t_arr = tilt.reindex(index=monthly_prices.index, columns=monthly_prices.columns).to_numpy(
            float
        )
    g_arr = None
    if group is not None:
        g_arr = np.array([group.get(c) for c in monthly_prices.columns], dtype=object)
    res = _backtest_arrays(
        monthly_prices.to_numpy(float),
        score.to_numpy(float),
        top_n,
        rebalance_every,
        cost_per_side,
        tilt=t_arr,
        group=g_arr,
        max_per_group=max_per_group,
        max_weight=max_weight,
        keep_rank=keep_rank,
        costs=costs,
    )
    dates = monthly_prices.index
    cols = monthly_prices.columns
    i0 = res["start"]
    rdates = dates[res["rebalances"]]
    return {
        "gross": pd.Series(res["gross"], index=dates[i0 + 1 :], name="gross"),
        "net": pd.Series(res["net"], index=dates[i0 + 1 :], name="net"),
        "equity": pd.DataFrame(
            {"gross": res["equity_gross"], "net": res["equity_net"]}, index=dates[i0:]
        ),
        "turnover": pd.Series(res["turnover"], index=rdates, name="turnover"),
        "cost": pd.Series(res["cost"], index=rdates, name="cost"),
        "holdings": {d: [cols[j] for j in p] for d, p in zip(rdates, res["holdings"], strict=True)},
    }


def cagr(equity: pd.Series) -> float:
    """Compound annual growth by calendar time between the first and last dates."""
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def annual_vol(returns: pd.Series, periods: int = 12) -> float:
    """Standard deviation of period returns (sample), annualised by sqrt(periods)."""
    return float(returns.std() * np.sqrt(periods))


def max_drawdown(equity: pd.Series) -> float:
    """Worst fall from a running peak, as a negative fraction."""
    return float((equity / equity.cummax() - 1).min())


# Zerodha delivery charges as in the reference spec §6 (slightly conservative: Zerodha's page in
# Nov 2026 lists NSE 0.00307% and DP ₹15.34 including GST): no brokerage; STT 0.1% each
# side; stamp duty 0.015% on buys; NSE transaction 0.00322% and SEBI 0.0001% each side with 18% GST;
# about ₹16 depository (DP) charge per stock per day it is sold.
FEES_BUY = 0.001 + 0.00015 + (0.0000322 + 0.000001) * 1.18
FEES_SELL = 0.001 + (0.0000322 + 0.000001) * 1.18
DP_PER_SELL = 16.0


def delivery_costs(slippage: float = 0.0005, capital: float = 1_000_000.0) -> tuple:
    """The `costs` tuple for `backtest`: fees plus `slippage` per side, ₹16 per stock sold."""
    return (FEES_BUY + slippage, FEES_SELL + slippage, DP_PER_SELL, capital)
