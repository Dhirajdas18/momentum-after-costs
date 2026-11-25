"""README findings, one function per topic: `mo report <topic>` writes charts to out/."""

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
    """Which momentum signal ranked next month's returns best, 2014-2026, on a point-in-time
    universe (the 200 most-traded stocks each month, delisted ones included; needs MO_LAKE_DIR),
    with today's NIFTY 200 from Yahoo alongside."""
    from mo.data import SYMBOLS
    from mo.signals import SIGNALS, evaluate, signal_panel
    from mo.universe import load_lake

    res = {}
    lake_px, lake_to = load_lake()
    panel = signal_panel(lake_px, lake_to)
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


REPORTS: dict[str, Callable[[Path], dict]] = {"signal": report_signal}
