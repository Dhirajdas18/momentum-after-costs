"""README findings, one function per topic: `mo report <topic>` writes charts to out/."""

import os
from collections.abc import Callable
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mo import plots


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


REPORTS: dict[str, Callable[[Path], dict]] = {
    "signal": report_signal,
    "universe": report_universe,
}
