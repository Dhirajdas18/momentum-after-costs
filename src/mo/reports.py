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

    # today's NIFTY 200 applied to the past (Yahoo): every stock with a price, no turnover rule
    yp = prices()[SYMBOLS].loc["2013-01-01":]
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
    dividends), smaller universes, the reference model's ₹50 crore turnover rule, delistings and capacity.
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
        r.index = monthly.index[monthly.index.get_indexer(r.index) + 1]
        return (1 + r).cumprod()

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


REPORTS: dict[str, Callable[[Path], dict]] = {
    "signal": report_signal,
    "universe": report_universe,
    "portfolio": report_portfolio,
    "costs": report_costs,
}
