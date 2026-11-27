"""README findings, one function per topic: `mo report <topic>` writes charts to out/."""

import os
from collections.abc import Callable
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mo import plots
from mo.data import ROOT


def prices() -> pd.DataFrame:
    """Adjusted closes of the universe, indices and ETFs with known Yahoo errors repaired."""
    from mo.data import DATA_PATH, clean_prices

    return clean_prices(pd.read_parquet(DATA_PATH)["adj_close"])


def returns() -> pd.DataFrame:
    from mo.data import DATA_PATH, daily_returns

    return daily_returns(pd.read_parquet(DATA_PATH)["adj_close"])


def last_years(df: pd.DataFrame, years: int) -> pd.DataFrame:
    return df.loc[df.index[-1] - pd.DateOffset(years=years) :]


def report_signal(out_dir: Path) -> dict:
    """Which momentum signal ranked next month's returns best, 2014-2026, on the reference model's
    point-in-time universe (the 200 most-traded stocks each day at ₹50 or more with a year of
    history, delisted ones included; needs MO_LAKE_DIR),
    with today's NIFTY 200 from Yahoo alongside."""
    from mo.data import SYMBOLS
    from mo.signals import SIGNALS, evaluate, signal_panel
    from mo.universe import load_lake, load_universe

    res = {}
    lake_px, _ = load_lake()
    panel = signal_panel(lake_px, universe=load_universe())
    res["point-in-time"] = (
        f"{panel['date'].nunique()} month-ends {panel['date'].min():%b %Y}-"
        f"{panel['date'].max():%b %Y}, {len(panel) / panel['date'].nunique():.0f} stocks a month"
    )
    ev = {s: evaluate(panel, s) for s in SIGNALS}
    for s, e in ev.items():
        ser = e["series"]
        res[s] = (
            f"top 20 minus universe {100 * e['top minus universe, a year']:+.1f}% a year "
            f"(2014-19 {1200 * ser[:'2019'].mean():+.1f}, "
            f"2020-26 {1200 * ser['2020':].mean():+.1f}), "
            f"beat it in {e['top beat universe, share of months']:.0%} of months; rank IC "
            f"{e['IC']:.3f} (t {e['IC t']:.1f}); top quintile minus bottom "
            f"{100 * e['Q5 minus Q1, a year']:+.1f}% a year; top 20 changed "
            f"{e['top list changed a month']:.0%} a month"
        )

    # today's NIFTY 200 applied to the past, on the archive's prices: every stock with a price
    yp = lake_px[[c for c in SYMBOLS if c in lake_px.columns]]
    flat = pd.DataFrame(1.0, index=yp.index, columns=yp.columns).where(yp.notna())
    yahoo = signal_panel(yp, flat, n=len(SYMBOLS))
    yahoo = yahoo[yahoo["date"] <= panel["date"].max()]
    for s in ("12-1", "NSE-style volatility-adjusted"):
        e = evaluate(yahoo, s)
        res[f"today's NIFTY 200, {s}"] = (
            f"top 20 minus universe {100 * e['top minus universe, a year']:+.1f}% a year, IC "
            f"{e['IC']:.3f} (t {e['IC t']:.1f})"
        )
    uni_pit = panel.groupby("date")["next"].mean()
    uni_today = yahoo.groupby("date")["next"].mean()
    res["equal-weight universe, a year"] = (
        f"point-in-time {100 * ((1 + uni_pit).prod() ** (12 / len(uni_pit)) - 1):.1f}%, today's "
        f"NIFTY 200 {100 * ((1 + uni_today).prod() ** (12 / len(uni_today)) - 1):.1f}%"
    )

    # quintiles
    quint = {}
    for s in ("12-1", "NSE-style volatility-adjusted", "3-0"):
        q = panel.dropna(subset=[s]).copy()
        q["q"] = q.groupby("date")[s].transform(
            lambda x: pd.qcut(x.rank(method="first"), 5, labels=False)
        )
        quint[s] = q.groupby("q")["next"].mean() * 12
        res[f"quintiles, {s}"] = ", ".join(f"Q{i + 1} {100 * v:.1f}%" for i, v in quint[s].items())

    names = {
        "12-1": "12-1",
        "6-1": "6-1",
        "3-0": "3-month",
        "12-0": "12-0",
        "NSE-style volatility-adjusted": "NSE-style score",
    }
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.1, 1]})
    order = list(SIGNALS)[::-1]
    v = [100 * ev[s]["top minus universe, a year"] for s in order]
    col = [plots.SERIES[0] if s == "NSE-style volatility-adjusted" else plots.MUTED for s in order]
    axes[0].barh([names[s] for s in order], v, color=col, height=0.55)
    for i, x in enumerate(v):
        axes[0].text(
            x + 0.2,
            i,
            f"{x:+.1f}%  (IC t {ev[order[i]]['IC t']:.1f})",
            va="center",
            fontsize=9,
            color=plots.TEXT,
        )
    axes[0].set_xlim(0, 17)
    axes[0].set_xlabel("top 20 minus the universe average, % a year")
    axes[0].set_title("Signal", fontsize=10, fontweight="normal", loc="left")
    w = 0.26
    for j, (s, c) in enumerate(
        (
            (("12-1"), plots.SERIES[1]),
            ("NSE-style volatility-adjusted", plots.SERIES[0]),
            ("3-0", plots.MUTED),
        )
    ):
        axes[1].bar(
            np.arange(5) + (j - 1) * w, 100 * quint[s].to_numpy(), w, color=c, label=names[s]
        )
    axes[1].set_xticks(range(5), ["Q1\nlowest", "Q2", "Q3", "Q4", "Q5\nhighest"])
    axes[1].set_ylabel("next-month return, % a year")
    axes[1].set_title("By quintile of the signal", fontsize=10, fontweight="normal", loc="left")
    axes[1].legend(fontsize=8, loc="upper left")
    fig.suptitle(
        f"200 most-traded NSE stocks each month, {panel['date'].min():%Y}-"
        f"{panel['date'].max():%Y}, before costs",
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    plots.save(fig, out_dir, "signal_compare")

    fig, ax = plt.subplots(figsize=(10, 4.2))
    for s, c in (
        ("NSE-style volatility-adjusted", plots.SERIES[0]),
        ("12-1", plots.SERIES[1]),
        ("12-0", plots.SERIES[2]),
        ("3-0", plots.MUTED),
    ):
        eq = 100 * (1 + ev[s]["series"]).cumprod()
        ax.plot(eq.index, eq, color=c, lw=1.6)
        plots.label_line_end(ax, eq.index[-1], eq.iloc[-1], names[s], c)
    ax.axhline(100, color=plots.TEXT_2, lw=0.8)
    ax.set_ylabel("top 20 against the universe, start = 100")
    ax.set_title(
        "Cumulative edge of the top 20 over an equal-weight universe, monthly, before costs",
        fontsize=10,
        fontweight="normal",
        loc="left",
    )
    ax.margins(x=0.12)
    fig.tight_layout()
    plots.save(fig, out_dir, "signal_edge")
    return res


def _stats(eq: pd.Series) -> dict:
    from mo.momentum import annual_vol, cagr, max_drawdown

    r = eq.pct_change().dropna()
    return {"cagr": cagr(eq), "vol": annual_vol(r), "dd": max_drawdown(eq)}


def report_universe(out_dir: Path) -> dict:
    """Survivorship and liquidity: the top 20 by the NSE-style score on the universe as it was
    each month against today's NIFTY 200 applied to the past (both on the archive's prices, no
    dividends), smaller universes, the reference ₹50 crore turnover rule, delistings and capacity.
    Needs MO_LAKE_DIR. Before costs."""
    from mo.data import SYMBOLS
    from mo.momentum import backtest, month_end_prices
    from mo.signals import score_frame, signal_panel
    from mo.universe import load_lake, load_universe

    sig = "NSE-style volatility-adjusted"
    res = {}
    px, _ = load_lake()
    uni = load_universe()
    monthly = month_end_prices(px)
    lake = os.environ["MO_LAKE_DIR"]
    market = pd.read_parquet(Path(lake) / "market.parquet").set_index("date")

    def run(panel, n=20):
        bt = backtest(monthly, score_frame(panel, sig), top_n=n, cost_per_side=0.0)
        return bt

    def ew(panel):
        r = panel.groupby("date")["next"].mean()
        first = r.index[0]
        r.index = monthly.index[monthly.index.get_indexer(r.index) + 1]
        return pd.concat([pd.Series([1.0], index=[first]), (1 + r).cumprod()])

    pit = signal_panel(px, universe=uni)
    today_syms = [s for s in SYMBOLS if s in px.columns]
    flat = pd.DataFrame(1.0, index=px.index, columns=today_syms).where(px[today_syms].notna())
    today = signal_panel(px[today_syms], flat, n=len(today_syms))
    curves = {}
    for name, panel in (("point-in-time 200", pit), ("today's NIFTY 200", today)):
        bt = run(panel)
        curves[f"top 20, {name}"] = bt["equity"]["gross"]
        curves[f"all stocks, {name}"] = ew(panel)
    start, end = curves["top 20, point-in-time 200"].index[[0, -1]]
    for k in ("nifty", "nifty200"):
        m = month_end_prices(market[[k]].dropna())[k].loc[start:end]
        curves[{"nifty": "NIFTY 50", "nifty200": "NIFTY 200"}[k]] = m / m.iloc[0]
    stats = {}
    for k, eq in curves.items():
        eq = eq.loc[start:end]
        stats[k] = _stats(eq / eq.iloc[0])
        res[k] = (
            f"{100 * stats[k]['cagr']:.1f}% a year, volatility {100 * stats[k]['vol']:.1f}%, "
            f"worst drawdown {100 * stats[k]['dd']:.1f}%"
        )
    res["period"] = f"{start:%b %Y} to {end:%b %Y}, price indices and archive prices, no dividends"
    res["today's list: stocks in the archive"] = f"{len(today_syms)} of {len(SYMBOLS)}"

    # against the real Nifty200 Momentum 30 (price index, in the archive from Aug 2020)
    mom = month_end_prices(market[["mom30_index"]].dropna())["mom30_index"]
    for n, reb in ((20, 1), (30, 6)):
        eq = backtest(
            monthly, score_frame(pit, sig), top_n=n, rebalance_every=reb, cost_per_side=0.0
        )["equity"]["gross"]
        a, b = eq.loc[mom.index[0] :], mom.loc[: eq.index[-1]]
        res[f"top {n}, rebalanced every {reb} months, vs Nifty200 Momentum 30"] = (
            f"{b.index[0]:%b %Y}-{b.index[-1]:%b %Y}: "
            f"ours {100 * _stats(a / a.iloc[0])['cagr']:.1f}% "
            f"a year, index {100 * _stats(b / b.iloc[0])['cagr']:.1f}%, monthly correlation "
            f"{a.pct_change().corr(b.pct_change()):.2f}"
        )

    # delistings among the point-in-time picks
    bt = run(pit)
    last_px = px.apply(lambda c: c.last_valid_index())
    picked = {s for h in bt["holdings"].values() for s in h}
    gone = sorted(s for s in picked if last_px[s] < px.index[-1] - pd.Timedelta(days=30))
    in_today = sum(s in SYMBOLS for s in picked)
    res["point-in-time picks"] = (
        f"{len(picked)} different stocks held at some point; {in_today} are in today's NIFTY 200; "
        f"{len(gone)} stopped trading before the archive's end"
    )

    # universe size and the turnover rule
    sizes = {}
    for n in (50, 100, 200):
        panel = signal_panel(px, universe=uni, n=n) if n != 200 else pit
        b = run(panel)
        e = ew(panel)
        top, allst = b["equity"]["gross"], e.loc[start:end]
        sizes[n] = (_stats(top / top.iloc[0])["cagr"], _stats(allst / allst.iloc[0])["cagr"])
        res[f"most-traded {n}"] = (
            f"top 20 {100 * sizes[n][0]:.1f}% a year, all {n} {100 * sizes[n][1]:.1f}%, "
            f"edge {100 * (sizes[n][0] - sizes[n][1]):+.1f} points"
        )
    liquid = uni[uni["med_turnover_cr"] >= 50]
    count = liquid.groupby("date").size()
    res["stocks with ₹50 crore median turnover"] = ", ".join(
        f"{y}: {int(count[count.index.year == y].median())}" for y in (2014, 2017, 2020, 2023, 2026)
    )
    lp = signal_panel(px, universe=liquid.assign(rank=liquid.groupby("date").cumcount() + 1))
    b = run(lp)
    e = ew(lp)
    res["₹50 crore rule"] = (
        f"top 20 {100 * _stats(b['equity']['gross'])['cagr']:.1f}% a year, all qualifying "
        f"{100 * _stats(e / e.iloc[0])['cagr']:.1f}%, {lp.groupby('date').size().median():.0f} "
        f"stocks a month (median)"
    )

    # capacity: a ₹10 crore book, 20 stocks, each ₹50 lakh, against the stock's median turnover
    picks_turn = []
    for d, h in bt["holdings"].items():
        u = uni[uni["date"] == uni["date"][uni["date"] <= d].max()].set_index("symbol")
        picks_turn += [u.at[s, "med_turnover_cr"] for s in h if s in u.index]
    med = float(np.median(picks_turn))
    res["capacity"] = (
        f"median daily turnover of a held stock ₹{med:.0f} crore; ₹50 lakh a stock (a ₹10 crore "
        f"book) is {100 * 0.5 / med:.2f}% of a day; at 5% of a day's turnover the book could be "
        f"about ₹{0.05 * med * 20:.0f} crore"
    )

    fig, ax = plt.subplots(figsize=(10, 4.6))
    show = {
        "top 20, today's NIFTY 200": (plots.MUTED, "--"),
        "top 20, point-in-time 200": (plots.SERIES[0], "-"),
        "all stocks, today's NIFTY 200": (plots.MUTED, ":"),
        "all stocks, point-in-time 200": (plots.SERIES[2], "-"),
        "NIFTY 50": (plots.SERIES[1], "-"),
    }
    for k, (c, ls) in show.items():
        eq = curves[k].loc[start:end]
        eq = 100 * eq / eq.iloc[0]
        ax.plot(eq.index, eq, color=c, lw=1.6, ls=ls)
        plots.label_line_end(ax, eq.index[-1], eq.iloc[-1], f"{k} {100 * stats[k]['cagr']:.1f}%", c)
    ax.set_yscale("log")
    ticks = [100, 200, 400, 800, 1600, 3200, 6400]
    ax.set_yticks(ticks, [str(t) for t in ticks])
    ax.minorticks_off()
    ax.set_ylabel("growth of 100, log scale")
    ax.set_title(
        "Same rule, two universes: the list as it was each month against today's list "
        "(before costs, no dividends)",
        fontsize=10,
        fontweight="normal",
        loc="left",
    )
    ax.margins(x=0.3)
    fig.tight_layout()
    plots.save(fig, out_dir, "universe_survivorship")

    fig, ax = plt.subplots(figsize=(8, 4))
    xs = np.arange(3)
    ax.bar(
        xs - 0.2,
        [100 * sizes[n][0] for n in (50, 100, 200)],
        0.38,
        color=plots.SERIES[0],
        label="top 20 by the score",
    )
    ax.bar(
        xs + 0.2,
        [100 * sizes[n][1] for n in (50, 100, 200)],
        0.38,
        color=plots.MUTED,
        label="all stocks in the universe",
    )
    for i, n in enumerate((50, 100, 200)):
        for dx, v in ((-0.2, sizes[n][0]), (0.2, sizes[n][1])):
            ax.text(
                i + dx, 100 * v + 0.3, f"{100 * v:.1f}%", ha="center", fontsize=9, color=plots.TEXT
            )
    ax.set_xticks(xs, ["50 most traded", "100 most traded", "200 most traded"])
    ax.set_ylabel("% a year, before costs")
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title(
        "Momentum's edge grew with a wider universe", fontsize=10, fontweight="normal", loc="left"
    )
    fig.tight_layout()
    plots.save(fig, out_dir, "universe_size")
    return res


def report_portfolio(out_dir: Path) -> dict:
    """Building the portfolio from the NSE-style score on the point-in-time universe (needs
    MO_LAKE_DIR): how many stocks, how to weight them, industry caps, and how much of the gap to
    the Nifty200 Momentum 30 index weighting explains. Before costs, no dividends."""
    from mo.momentum import annual_vol, backtest, cagr, max_drawdown, month_end_prices
    from mo.signals import _ratio_vol, score_frame, signal_panel
    from mo.universe import load_lake, load_universe

    res = {}
    px, _ = load_lake()
    uni = load_universe()
    monthly = month_end_prices(px)
    sc = score_frame(signal_panel(px, universe=uni), "NSE-style volatility-adjusted")
    vol = _ratio_vol(px, monthly)
    u = uni.assign(m=uni["date"].dt.to_period("M"))
    size = u.groupby(["m", "symbol"])["med_turnover_cr"].last().unstack()
    month_of = pd.Series(monthly.index, index=monthly.index.to_period("M"))
    size = size[size.index.isin(month_of.index)]
    size.index = month_of.loc[size.index].to_numpy()
    industry = pd.read_csv(ROOT / "docs" / "data" / "nifty500_industry.csv")
    industry = dict(zip(industry["symbol"], industry["industry"], strict=True))
    market = pd.read_parquet(Path(os.environ["MO_LAKE_DIR"]) / "market.parquet").set_index("date")
    mom = month_end_prices(market[["mom30_index"]].dropna())["mom30_index"]

    def run(name, **kw):
        b = backtest(monthly, sc, cost_per_side=0.0, **kw)
        e = b["equity"]["gross"]
        yrs = (e.index[-1] - e.index[0]).days / 365.25
        a, ix = e.loc[mom.index[0] :], mom.loc[: e.index[-1]]
        out = {
            "cagr": cagr(e),
            "vol": annual_vol(e.pct_change().dropna()),
            "dd": max_drawdown(e),
            "turnover": float(b["turnover"].iloc[1:].sum() / yrs),
            "recent": cagr(a / a.iloc[0]),
            "index": cagr(ix / ix.iloc[0]),
            "holdings": b["holdings"],
        }
        res[name] = (
            f"{100 * out['cagr']:.1f}% a year, volatility {100 * out['vol']:.1f}%, worst drawdown "
            f"{100 * out['dd']:.1f}%, traded {out['turnover']:.1f}x the portfolio a year; "
            f"{a.index[0]:%b %Y}-{a.index[-1]:%b %Y} {100 * out['recent']:.1f}% against the "
            f"index's {100 * out['index']:.1f}%"
        )
        return out

    sizes = {n: run(f"{n} stocks, equal weight", top_n=n) for n in (10, 20, 30, 50)}
    w = {
        "equal": sizes[30],
        "inverse volatility": run("30 stocks, inverse volatility", top_n=30, tilt=1 / vol),
        "score": run("30 stocks, by score", top_n=30, tilt=sc),
        "size": run("30 stocks, by size (turnover)", top_n=30, tilt=size),
        "score x size": run("30 stocks, score x size", top_n=30, tilt=sc * size),
        "score x size, 5% cap": run(
            "30 stocks, score x size, 5% cap", top_n=30, tilt=sc * size, max_weight=0.05
        ),
        "score x size, 5% cap, every 6 months": run(
            "30 stocks, score x size, 5% cap, every 6 months",
            top_n=30,
            tilt=sc * size,
            max_weight=0.05,
            rebalance_every=6,
        ),
    }
    {
        k: run(f"20 stocks, at most {k} per industry", top_n=20, group=industry, max_per_group=k)
        for k in (3, 2)
    }
    picks = [s for h in sizes[20]["holdings"].values() for s in h]
    res["industry known (today's NIFTY 500 list)"] = (
        f"{np.mean([s in industry for s in picks]):.0%} of 20-stock picks; "
        "unknown ones are not capped"
    )

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharex=True)
    ns = [10, 20, 30, 50]
    for ax, key, lab, c in (
        (axes[0], "cagr", "return, % a year", plots.SERIES[0]),
        (axes[1], "dd", "worst drawdown, %", plots.SERIES[1]),
    ):
        v = [100 * sizes[n][key] for n in ns]
        ax.bar([str(n) for n in ns], v, color=c, width=0.55)
        for i, x in enumerate(v):
            ax.text(
                i,
                x + (0.4 if x >= 0 else -0.4),
                f"{x:.1f}%",
                ha="center",
                va="bottom" if x >= 0 else "top",
                fontsize=9,
                color=plots.TEXT,
            )
        ax.set_xlabel("stocks held")
        ax.set_ylabel(lab)
    axes[1].set_ylim(-52, 0)
    fig.suptitle(
        "Fewer stocks, more return and deeper falls (equal weight, monthly, before costs)",
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    plots.save(fig, out_dir, "portfolio_size")

    fig, ax = plt.subplots(figsize=(10, 4.4))
    names = list(w)
    xs = np.arange(len(names))
    ax.bar(
        xs - 0.2,
        [100 * w[k]["cagr"] for k in names],
        0.38,
        color=plots.SERIES[0],
        label="Jan 2014 to Nov 2026",
    )
    ax.bar(
        xs + 0.2,
        [100 * w[k]["recent"] for k in names],
        0.38,
        color=plots.SERIES[2],
        label=f"{mom.index[0]:%b %Y} to Nov 2026",
    )
    ax.axhline(
        100 * w["equal"]["index"],
        color=plots.SERIES[1],
        lw=1.2,
        ls="--",
        label=f"Nifty200 Momentum 30, {mom.index[0]:%b %Y} to Nov 2026",
    )
    ax.set_xticks(
        xs,
        [
            "equal",
            "inverse\nvolatility",
            "score",
            "size",
            "score\n× size",
            "score × size\n5% cap",
            "score × size\n5% cap, 6-monthly",
        ],
    )
    ax.set_ylabel("% a year, before costs")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title(
        "30 stocks: weighting by size took away most of the edge",
        fontsize=10,
        fontweight="normal",
        loc="left",
    )
    fig.tight_layout()
    plots.save(fig, out_dir, "portfolio_weights")
    return res


def report_costs(out_dir: Path) -> dict:
    """Delivery costs and turnover for the top-20 NSE-style score portfolio on the point-in-time
    universe (needs MO_LAKE_DIR): Zerodha charges, rebalance frequency with every possible start
    month, hold bands, portfolio size (the per-sale DP charge) and slippage. No dividends."""
    from mo.momentum import backtest, cagr, delivery_costs, month_end_prices
    from mo.signals import score_frame, signal_panel
    from mo.universe import load_lake, load_universe

    res = {}
    px, _ = load_lake()
    monthly = month_end_prices(px)
    sc = score_frame(signal_panel(px, universe=load_universe()), "NSE-style volatility-adjusted")

    def run(**kw):
        b = backtest(monthly, sc, top_n=20, **kw)
        e = b["equity"]
        yrs = (e.index[-1] - e.index[0]).days / 365.25
        return {
            "gross": cagr(e["gross"]),
            "net": cagr(e["net"]),
            "cost": float(b["cost"].sum() / yrs),
            "turnover": float(b["turnover"].iloc[1:].sum() / yrs),
        }

    base = run(costs=delivery_costs())
    res["charges"] = (
        "Zerodha delivery, Nov 2026: STT 0.1% each side, stamp 0.015% on buys, NSE 0.00322% "
        "and SEBI 0.0001% each side with 18% GST, ₹16 DP charge per stock sold, 5 bp slippage "
        "a side; ₹10 lakh"
    )
    res["monthly, full rebalance"] = (
        f"gross {100 * base['gross']:.1f}%, net {100 * base['net']:.1f}% a year; costs "
        f"{100 * base['cost']:.2f}% a year; traded {base['turnover']:.1f}x the portfolio a year"
    )
    bands = {}
    for kr in (30, 40, 60):
        bands[kr] = run(keep_rank=kr, costs=delivery_costs())
        b = bands[kr]
        res[f"monthly, hold band {kr}"] = (
            f"gross {100 * b['gross']:.1f}%, net {100 * b['net']:.1f}%; costs "
            f"{100 * b['cost']:.2f}% a year; traded {b['turnover']:.1f}x"
        )

    # every rebalance frequency from every start month, scored on 2016 onward
    timing = {}
    for every in (1, 3, 6, 12):
        for kr in (None, 40):
            vals = []
            for off in range(every):
                s2 = sc.copy()
                first = s2.index[s2.index >= pd.Timestamp("2015-01-01")][off]
                s2.loc[: first - pd.Timedelta(days=1)] = np.nan
                e = backtest(
                    monthly,
                    s2,
                    top_n=20,
                    rebalance_every=every,
                    keep_rank=kr,
                    costs=delivery_costs(),
                )["equity"]["net"]
                e = e.loc["2016-01-01":]
                vals.append(cagr(e / e.iloc[0]))
            timing[(every, kr)] = vals
            res[f"every {every} months, {'band 40' if kr else 'full rebalance'}, net 2016-26"] = (
                f"median {100 * np.median(vals):.1f}%, range {100 * min(vals):.1f}% to "
                f"{100 * max(vals):.1f}% over {every} start months"
            )
    for cap in (2e5, 1e7):
        a, b = (
            run(costs=delivery_costs(capital=cap)),
            run(keep_rank=40, costs=delivery_costs(capital=cap)),
        )
        res[f"₹{cap / 1e5:,.0f} lakh"] = (
            f"costs {100 * a['cost']:.2f}% a year full rebalance, "
            f"{100 * b['cost']:.2f}% with band 40"
        )
    slips = {}
    for sl in (0.0002, 0.001, 0.002):
        slips[sl] = (
            run(costs=delivery_costs(slippage=sl)),
            run(keep_rank=40, costs=delivery_costs(slippage=sl)),
        )
        res[f"slippage {sl * 1e4:.0f} bp"] = (
            f"net {100 * slips[sl][0]['net']:.1f}% full rebalance, "
            f"{100 * slips[sl][1]['net']:.1f}% band 40"
        )

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.15, 1]})
    names = ["full rebalance", "band 30", "band 40", "band 60"]
    rows = [base, bands[30], bands[40], bands[60]]
    xs = np.arange(len(names))
    axes[0].bar(
        xs - 0.2, [100 * r["gross"] for r in rows], 0.38, color=plots.MUTED, label="before costs"
    )
    axes[0].bar(
        xs + 0.2, [100 * r["net"] for r in rows], 0.38, color=plots.SERIES[0], label="after costs"
    )
    for i, r in enumerate(rows):
        axes[0].text(
            i,
            100 * r["gross"] + 0.6,
            f"costs {100 * r['cost']:.1f}%/yr\n{r['turnover']:.1f}x traded",
            ha="center",
            fontsize=8,
            color=plots.TEXT,
        )
    axes[0].set_xticks(xs, names)
    axes[0].set_ylim(0, 42)
    axes[0].set_ylabel("% a year, 2014-2026")
    axes[0].legend(fontsize=8, loc="upper right", ncol=2)
    axes[0].set_title("Monthly, 20 stocks, ₹10 lakh", fontsize=10, fontweight="normal", loc="left")
    for j, (kr, c, lab) in enumerate(
        ((None, plots.MUTED, "full rebalance"), (40, plots.SERIES[0], "band 40"))
    ):
        for i, every in enumerate((1, 3, 6, 12)):
            v = 100 * np.array(timing[(every, kr)])
            x = i + (j - 0.5) * 0.3
            axes[1].plot([x, x], [v.min(), v.max()], color=c, lw=2)
            axes[1].plot([x], [np.median(v)], "o", color=c, ms=6, label=lab if i == 0 else None)
    axes[1].set_xticks(range(4), ["monthly", "3 months", "6 months", "12 months"])
    axes[1].set_ylabel("% a year after costs, 2016-2026")
    axes[1].legend(fontsize=8, loc="lower left")
    axes[1].set_title(
        "Rebalance every… (dot: median start month; line: range)",
        fontsize=10,
        fontweight="normal",
        loc="left",
    )
    fig.suptitle(
        "Costs took 1.5 points a year; a hold band halved them; slower rebalancing cost "
        "more than it saved",
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    plots.save(fig, out_dir, "costs_turnover")
    return res


def report_tax(out_dir: Path) -> dict:
    """After-tax returns of the top-20 NSE-style score portfolio on the point-in-time universe
    (needs MO_LAKE_DIR) with delivery costs: short- and long-term gains tax paid every March,
    rebalance schedules (slow ones from every start month), ₹10 lakh and ₹1 crore, against NIFTY
    bought and held. Today's tax rates for every year; no dividends."""
    from mo.momentum import delivery_costs, month_end_prices
    from mo.signals import score_frame, signal_panel
    from mo.tax import buy_and_hold_after_tax, simulate
    from mo.universe import load_lake, load_universe

    res = {}
    px, _ = load_lake()
    monthly = month_end_prices(px)
    sc = score_frame(signal_panel(px, universe=load_universe()), "NSE-style volatility-adjusted")
    market = pd.read_parquet(Path(os.environ["MO_LAKE_DIR"]) / "market.parquet").set_index("date")
    nifty = month_end_prices(market[["nifty"]].dropna())["nifty"]

    def run(capital, score=sc, **kw):
        c = delivery_costs(capital=capital)
        pre = simulate(monthly, score, capital=capital, costs=c, tax=False, **kw)["value"]
        post = simulate(monthly, score, capital=capital, costs=c, **kw)
        yrs = (pre.index[-1] - pre.index[0]).days / 365.25
        gains = post["short-term gains"] + post["long-term gains"]
        return {
            "pre": (pre.iloc[-1] / capital) ** (1 / yrs) - 1,
            "yearly": (post["value"].iloc[-1] / capital) ** (1 / yrs) - 1,
            "sold": (post["after selling"] / capital) ** (1 / yrs) - 1,
            "short share": post["short-term gains"] / gains if gains else np.nan,
            "start": pre.index[0],
            "end": pre.index[-1],
        }

    rules = {
        "monthly, full rebalance": {},
        "monthly, hold band 40": {"keep_rank": 40},
    }
    out = {}
    for cap, label in ((1e6, "₹10 lakh"), (1e7, "₹1 crore")):
        for name, kw in rules.items():
            r = run(cap, **kw)
            out[(label, name)] = r
            res[f"{label}, {name}"] = (
                f"{100 * r['pre']:.1f}% a year before tax, {100 * r['yearly']:.1f}% after tax paid "
                f"each March, {100 * r['sold']:.1f}% after selling everything at the end; "
                f"{100 * r['short share']:.0f}% of realised gains short-term"
            )
        r0 = out[(label, "monthly, full rebalance")]
        n = nifty.loc[r0["start"] : r0["end"]]
        yrs = (n.index[-1] - n.index[0]).days / 365.25
        b = buy_and_hold_after_tax(n, cap)
        out[(label, "NIFTY")] = {
            "pre": (b["before tax"] / cap) ** (1 / yrs) - 1,
            "sold": (b["after selling"] / cap) ** (1 / yrs) - 1,
        }
        res[f"{label}, NIFTY 50 bought and held"] = (
            f"{100 * out[(label, 'NIFTY')]['pre']:.1f}% a year before tax, "
            f"{100 * out[(label, 'NIFTY')]['sold']:.1f}% after selling at the end"
        )

    slow = {}
    for every in (6, 12, 13):
        vals = []
        for off in range(every):
            s2 = sc.copy()
            first = s2.index[s2.index >= pd.Timestamp("2015-01-01")][off]
            s2.loc[: first - pd.Timedelta(days=1)] = np.nan
            r = run(1e6, score=s2, rebalance_every=every, keep_rank=40)
            vals.append(r)
        slow[every] = vals
        pre = np.array([v["pre"] for v in vals])
        sold = np.array([v["sold"] for v in vals])
        short = np.array([v["short share"] for v in vals])
        res[f"every {every} months, band 40, ₹10 lakh, by start month"] = (
            f"before tax median {100 * np.median(pre):.1f}% ({100 * pre.min():.1f} to "
            f"{100 * pre.max():.1f}), after selling median {100 * np.median(sold):.1f}% "
            f"({100 * sold.min():.1f} to {100 * sold.max():.1f}); short-term share of gains "
            f"median {100 * np.median(short):.0f}%"
        )
    s1 = sc.copy()
    s1.loc[: pd.Timestamp("2014-12-31")] = np.nan
    m1 = [run(1e6, score=s1, keep_rank=40)]
    slow[1] = m1
    res["monthly, band 40, from Jan 2015 (same span as the slow schedules)"] = (
        f"before tax {100 * m1[0]['pre']:.1f}%, after selling {100 * m1[0]['sold']:.1f}%"
    )

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), gridspec_kw={"width_ratios": [1.2, 1]})
    names = ["monthly, full rebalance", "monthly, hold band 40", "NIFTY"]
    labels = ["monthly,\nfull rebalance", "monthly,\nhold band 40", "NIFTY 50,\nbought and held"]
    xs = np.arange(3)
    for j, (key, c, lab) in enumerate(
        (
            ("pre", plots.MUTED, "before tax"),
            ("sold", plots.SERIES[0], "after tax, all sold at the end"),
        )
    ):
        v = [100 * out[("₹10 lakh", k)][key] for k in names]
        axes[0].bar(xs + (j - 0.5) * 0.38, v, 0.38, color=c, label=lab)
        for i, x in enumerate(v):
            axes[0].text(
                i + (j - 0.5) * 0.38,
                x + 0.4,
                f"{x:.1f}%",
                ha="center",
                fontsize=8,
                color=plots.TEXT,
            )
    axes[0].set_xticks(xs, labels)
    axes[0].set_ylim(0, 32)
    axes[0].set_ylabel("% a year, ₹10 lakh, 2014-2026")
    axes[0].legend(fontsize=8, loc="upper right")
    for i, every in enumerate((1, 6, 12, 13)):
        pre = 100 * np.array([v["pre"] for v in slow[every]])
        sold = 100 * np.array([v["sold"] for v in slow[every]])
        for dx, v, c in ((-0.15, pre, plots.MUTED), (0.15, sold, plots.SERIES[0])):
            axes[1].plot([i + dx] * 2, [v.min(), v.max()], color=c, lw=2)
            axes[1].plot([i + dx], [np.median(v)], "o", color=c, ms=6)
    axes[1].set_xticks(range(4), ["monthly", "6 months", "12 months", "13 months"])
    axes[1].set_ylabel("% a year from a 2015 start, by start month")
    axes[1].set_title(
        "Band 40, ₹10 lakh (grey before tax, blue after)",
        fontsize=10,
        fontweight="normal",
        loc="left",
    )
    fig.suptitle(
        "Tax took 2.8 points a year with the band, 4.4 without; holding past a year didn't pay",
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    plots.save(fig, out_dir, "tax")
    return res


def report_crash(out_dir: Path) -> dict:
    """Momentum crashes on the point-in-time universe (needs MO_LAKE_DIR): the monthly band-40
    portfolio after delivery costs, its worst months and drawdowns against NIFTY and the average
    stock, and two ways of stepping aside (a NIFTY trend filter, volatility scaling). Before tax,
    no dividends; cash earns 6.5%."""
    from mo.crash import RF, drawdowns, market_filter, vol_scale
    from mo.momentum import (
        annual_vol,
        backtest,
        cagr,
        delivery_costs,
        max_drawdown,
        month_end_prices,
    )
    from mo.signals import score_frame, signal_panel
    from mo.universe import load_lake, load_universe

    res = {}
    px, _ = load_lake()
    monthly = month_end_prices(px)
    panel = signal_panel(px, universe=load_universe())
    sc = score_frame(panel, "NSE-style volatility-adjusted")
    market = pd.read_parquet(Path(os.environ["MO_LAKE_DIR"]) / "market.parquet").set_index("date")
    nifty = month_end_prices(market[["nifty"]].dropna())["nifty"]
    r = backtest(monthly, sc, top_n=20, keep_rank=40, costs=delivery_costs())["net"]
    nr = nifty.pct_change().reindex(r.index).fillna(0.0)
    ew = panel.groupby("date")["next"].mean()
    ew.index = monthly.index[monthly.index.get_indexer(ew.index) + 1]
    ew = ew.reindex(r.index)

    start = monthly.index[monthly.index.get_loc(r.index[0]) - 1]

    def curve(x):
        return pd.concat([pd.Series([1.0], index=[start]), (1 + x).cumprod()])

    def stats(x):
        e = curve(x)
        v = annual_vol(x)
        return {
            "cagr": cagr(e),
            "vol": v,
            "dd": max_drawdown(e),
            "sharpe": float((x - RF / 12).mean() * 12 / v),
        }

    series = {"momentum (band 40, after costs)": r, "NIFTY 50": nr, "average stock": ew}
    exposure = {}
    for m in (6, 10, 12):
        series[f"trend filter, {m} months"], exposure[m] = market_filter(r, nifty, m)
    for tv in (0.15, 0.20, 0.25):
        series[f"volatility target {tv:.0%}"], exposure[tv] = vol_scale(r, tv)
    st = {k: stats(v) for k, v in series.items()}
    invested = {f"trend filter, {m} months": exposure[m] for m in (6, 10, 12)}
    invested |= {f"volatility target {tv:.0%}": exposure[tv] for tv in (0.15, 0.20, 0.25)}
    for k, v in st.items():
        extra = f", invested {invested[k].mean():.0%} on average" if k in invested else ""
        res[k] = (
            f"{100 * v['cagr']:.1f}% a year, volatility {100 * v['vol']:.1f}%, worst drawdown "
            f"{100 * v['dd']:.1f}%, Sharpe {v['sharpe']:.2f}{extra}"
        )
    res["period"] = f"{start:%b %Y} to {r.index[-1]:%b %Y}"
    for name, x in (("momentum", r), ("NIFTY 50", nr)):
        d = drawdowns(curve(x), 4)
        res[f"deepest drawdowns, {name}"] = "; ".join(
            f"{row.peak:%b %Y}-{row.trough:%b %Y} {100 * row.depth:.1f}%" for row in d.itertuples()
        )
    worst = pd.DataFrame({"mom": r, "nifty": nr, "ew": ew}).nsmallest(5, "mom")
    res["momentum's worst months (momentum, NIFTY, average stock)"] = "; ".join(
        f"{d:%b %Y} {100 * w.mom:+.1f}, {100 * w.nifty:+.1f}, {100 * w.ew:+.1f}"
        for d, w in worst.iterrows()
    )
    ex = r - ew
    below = (nifty < nifty.rolling(10).mean()).shift(1).reindex(r.index).fillna(False).astype(bool)
    res["edge over the average stock"] = (
        f"{100 * ex[~below].mean() * 12:+.1f}% a year when NIFTY was above its 10-month average, "
        f"{100 * ex[below].mean() * 12:+.1f}% when below ({int(below.sum())} months); in months "
        f"NIFTY rose more than 5% {100 * ex[nr > 0.05].mean():+.2f}% a month "
        f"({int((nr > 0.05).sum())} months), fell more than 5% {100 * ex[nr < -0.05].mean():+.2f}% "
        f"({int((nr < -0.05).sum())})"
    )

    fig, ax = plt.subplots(figsize=(10, 4.4))
    for k, c, ls in (
        ("momentum (band 40, after costs)", plots.SERIES[0], "-"),
        ("trend filter, 10 months", plots.SERIES[2], "-"),
        ("NIFTY 50", plots.SERIES[1], "-"),
    ):
        e = 100 * curve(series[k])
        ax.plot(e.index, e, color=c, lw=1.6, ls=ls)
        plots.label_line_end(ax, e.index[-1], e.iloc[-1], f"{k} {100 * st[k]['cagr']:.1f}%", c)
    out_months = exposure[10][exposure[10] == 0].index
    for d in out_months:
        ax.axvspan(d - pd.Timedelta(days=30), d, color=plots.GRID, alpha=0.6, lw=0)
    ax.set_yscale("log")
    ticks = [100, 200, 400, 800, 1600]
    ax.set_yticks(ticks, [str(t) for t in ticks])
    ax.minorticks_off()
    ax.set_ylabel("growth of 100, log scale")
    ax.set_title(
        "Shaded: months the 10-month NIFTY filter held cash",
        fontsize=10,
        fontweight="normal",
        loc="left",
    )
    ax.margins(x=0.32)
    fig.tight_layout()
    plots.save(fig, out_dir, "crash_paths")

    names = [
        "momentum (band 40, after costs)",
        "trend filter, 6 months",
        "trend filter, 10 months",
        "trend filter, 12 months",
        "volatility target 15%",
        "volatility target 20%",
        "volatility target 25%",
        "NIFTY 50",
    ][::-1]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), sharey=True)
    col = [
        plots.SERIES[0]
        if k.startswith("momentum")
        else plots.SERIES[1]
        if k == "NIFTY 50"
        else plots.MUTED
        for k in names
    ]
    for ax, key, lab in (
        (axes[0], "sharpe", "Sharpe (above 6.5% cash)"),
        (axes[1], "dd", "worst drawdown, %"),
    ):
        v = [st[k][key] * (100 if key == "dd" else 1) for k in names]
        ax.barh(names, v, color=col, height=0.55)
        for i, x in enumerate(v):
            if key == "dd":
                ax.text(
                    x - 0.4, i, f"{x:.0f}%", va="center", ha="right", fontsize=9, color=plots.TEXT
                )
            else:
                ax.text(x + 0.01, i, f"{x:.2f}", va="center", fontsize=9, color=plots.TEXT)
        ax.set_xlabel(lab)
    axes[0].set_xlim(0, 1.05)
    axes[1].set_xlim(-38, 0)
    fig.suptitle(
        "Stepping aside cut drawdowns a little; only one setting raised the Sharpe",
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    plots.save(fig, out_dir, "crash_overlays")
    return res


def report_verdict(out_dir: Path) -> dict:
    """The verdict on ₹10 lakh (needs MO_LAKE_DIR): DIY momentum (20 stocks, monthly, hold band 40,
    delivery costs, tax) against a Nifty200 Momentum 30 fund (the index less a 0.3% fee) and NIFTY
    bought and held, from August 2020 when the archive has the index; DIY against NIFTY from 2014;
    a luck test; next-day execution; the fund's tracking. No dividends anywhere."""
    from mo.data import DATA_PATH
    from mo.luck import luck_probability
    from mo.momentum import backtest, cagr, delivery_costs, month_end_prices
    from mo.signals import score_frame, signal_panel
    from mo.tax import buy_and_hold_after_tax, simulate
    from mo.universe import load_lake, load_universe

    res = {}
    cap, fee = 1e6, 0.003
    px, _ = load_lake()
    monthly = month_end_prices(px)
    sc = score_frame(signal_panel(px, universe=load_universe()), "NSE-style volatility-adjusted")
    market = pd.read_parquet(Path(os.environ["MO_LAKE_DIR"]) / "market.parquet").set_index("date")
    nifty = month_end_prices(market[["nifty"]].dropna())["nifty"]
    mom = month_end_prices(market[["mom30_index"]].dropna())["mom30_index"]
    costs = delivery_costs(capital=cap)

    def diy(score):
        pre = simulate(monthly, score, capital=cap, keep_rank=40, costs=costs, tax=False)["value"]
        post = simulate(monthly, score, capital=cap, keep_rank=40, costs=costs)
        return pre, post

    def ann(end_value, start, end):
        return (end_value / cap) ** (365.25 / (end - start).days) - 1

    windows = {}
    s2 = sc.copy()
    s2.loc[: mom.index[0] - pd.Timedelta(days=1)] = np.nan
    for label, score in (("2014-2026", sc), ("since Aug 2020", s2)):
        pre, post = diy(score)
        a, b = pre.index[0], pre.index[-1]
        row = {"DIY momentum": (ann(pre.iloc[-1], a, b), ann(post["after selling"], a, b))}
        n = buy_and_hold_after_tax(nifty.loc[a:b], cap)
        row["NIFTY 50"] = (ann(n["before tax"], a, b), ann(n["after selling"], a, b))
        if label == "since Aug 2020":
            idx = mom.loc[a:b]
            fund = idx * np.exp(-fee * np.arange(len(idx)) / 12)
            f = buy_and_hold_after_tax(fund, cap)
            row["Momentum 30 fund"] = (ann(f["before tax"], a, b), ann(f["after selling"], a, b))
            paths = {
                "DIY momentum": post["value"] / cap * 100,
                "Momentum 30 fund": fund / fund.iloc[0] * 100,
                "NIFTY 50": nifty.loc[a:b] / nifty.loc[a:b].iloc[0] * 100,
            }
        windows[label] = row
        for k, (p0, p1) in row.items():
            res[f"{label}, {k}"] = (
                f"{100 * p0:.1f}% a year before tax, {100 * p1:.1f}% after tax with everything "
                f"sold at the end ({a:%b %Y}-{b:%b %Y}, ₹10 lakh)"
            )

    net = backtest(monthly, sc, top_n=20, keep_rank=40, costs=delivery_costs())["net"]
    ex_n = net - nifty.pct_change().reindex(net.index)
    fund_m = (mom * np.exp(-fee * np.arange(len(mom)) / 12)).pct_change()
    ex_f = (net - fund_m.reindex(net.index)).dropna()
    res["luck, against NIFTY 50 (2014-2026, before tax)"] = (
        f"average edge {100 * 12 * ex_n.mean():+.1f}% a year; chance of this with no real edge "
        f"{luck_probability(ex_n):.3f} (12-month blocks, 20,000 resamples)"
    )
    res["luck, against the Momentum 30 fund (Aug 2020-2026, before tax)"] = (
        f"average edge {100 * 12 * ex_f.mean():+.1f}% a year over {len(ex_f)} months; chance "
        f"{luck_probability(ex_f):.3f}"
    )
    nxt = px.shift(-1).reindex(monthly.index).fillna(monthly)
    a = backtest(monthly, sc, top_n=20, keep_rank=40, costs=delivery_costs())["equity"]["net"]
    b = backtest(nxt, sc, top_n=20, keep_rank=40, costs=delivery_costs())["equity"]["net"]
    res["trading the day after the signal"] = (
        f"{100 * cagr(b):.1f}% a year against {100 * cagr(a):.1f}% at the signal's own close"
    )
    etf = month_end_prices(pd.read_parquet(DATA_PATH)["adj_close"][["MOMENTUM"]].dropna())
    etf = etf["MOMENTUM"].loc[mom.index[0] :]
    ix = mom.loc[etf.index[0] : etf.index[-1]]
    res["Motilal Oswal Momentum 30 ETF against the index"] = (
        f"{etf.index[0]:%b %Y}-{etf.index[-1]:%b %Y}: ETF {100 * cagr(etf / etf.iloc[0]):.2f}% a "
        f"year, index {100 * cagr(ix / ix.iloc[0]):.2f}% (Yahoo prices against the archive's index)"
    )

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), gridspec_kw={"width_ratios": [1.35, 1]})
    for k, c in (
        ("DIY momentum", plots.SERIES[0]),
        ("Momentum 30 fund", plots.SERIES[2]),
        ("NIFTY 50", plots.SERIES[1]),
    ):
        e = paths[k]
        axes[0].plot(e.index, e, color=c, lw=1.7)
        plots.label_line_end(axes[0], e.index[-1], e.iloc[-1], k, c)
    axes[0].set_ylabel("growth of 100 (DIY after costs and yearly tax)")
    axes[0].set_title("Since August 2020, ₹10 lakh", fontsize=10, fontweight="normal", loc="left")
    axes[0].margins(x=0.28)
    row = windows["since Aug 2020"]
    names = ["DIY momentum", "Momentum 30 fund", "NIFTY 50"]
    xs = np.arange(3)
    for j, (idx_, c, lab) in enumerate(
        ((0, plots.MUTED, "before tax"), (1, plots.SERIES[0], "after tax, sold at the end"))
    ):
        v = [100 * row[k][idx_] for k in names]
        axes[1].bar(xs + (j - 0.5) * 0.38, v, 0.38, color=c, label=lab)
        for i, x in enumerate(v):
            axes[1].text(
                i + (j - 0.5) * 0.38,
                x + 0.4,
                f"{x:.1f}%",
                ha="center",
                fontsize=8,
                color=plots.TEXT,
            )
    axes[1].set_xticks(xs, ["DIY\nmomentum", "Momentum 30\nfund", "NIFTY 50"])
    axes[1].set_ylim(0, 36)
    axes[1].set_ylabel("% a year")
    axes[1].legend(fontsize=8, loc="upper right")
    fig.suptitle(
        "After costs and tax, DIY momentum beat the fund by about 12 points a year (no dividends)",
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    plots.save(fig, out_dir, "verdict")
    return res


REPORTS: dict[str, Callable[[Path], dict]] = {
    "signal": report_signal,
    "universe": report_universe,
    "portfolio": report_portfolio,
    "costs": report_costs,
    "tax": report_tax,
    "crash": report_crash,
    "verdict": report_verdict,
}
