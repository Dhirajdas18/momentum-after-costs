"""Interactive dashboard: a live momentum lab for today's NIFTY 200, as one static page."""

import json
import re
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd

from mo import plots
from mo.momentum import month_end_prices

FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
ICON = (
    "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22%3E"
    "%3Cpath d=%22M1 13 5 9 9 10 15 3%22 fill=%22none%22 stroke=%22%232a78d6%22"
    " stroke-width=%222%22/%3E"
    "%3Cpath d=%22M11 3h4v4%22 fill=%22none%22 stroke=%22%232a78d6%22 stroke-width=%222%22/%3E"
    "%3C/svg%3E"
)
HERE = Path(__file__).parent
JS = (HERE / "momentum.js").read_text(encoding="utf-8")
LAB = (HERE / "lab.html").read_text(encoding="utf-8")
PAGE = Template((HERE / "page.html").read_text(encoding="utf-8"))
REPO = "https://github.com/Dhirajdas18/momentum-after-costs"
SCALE = 1e4  # log prices stored as integers in units of 0.0001 (0.01%)
BENCH = ["NIFTYBEES", "NIFTY"]


def encode(px: pd.Series) -> list[int | None]:
    """Log price x 1e4 rounded, as the first value then month-to-month differences (small
    numbers, so the page stays light). None where there is no price; the decoder carries the
    last level across gaps."""
    logs = np.round(np.log(px.to_numpy(float)) * SCALE)
    out, last = [], None
    for v in logs:
        if np.isnan(v):
            out.append(None)
            continue
        out.append(int(v) if last is None else int(v - last))
        last = v
    return out


def lab_data(prices: pd.DataFrame) -> dict:
    """Month-end adjusted closes of the universe and the benchmarks, compactly encoded."""
    from mo.data import SECTORS, SYMBOLS

    monthly = month_end_prices(prices)
    symbols = [s for s in SYMBOLS if s in monthly and monthly[s].notna().any()]
    return {
        "symbols": symbols,
        "industries": {s: SECTORS[s] for s in symbols},
        "dates": list(monthly.index.strftime("%Y-%m-%d")),
        "last": f"{prices.index[-1]:%d %b %Y}",
        "scale": SCALE,
        "px": {s: encode(monthly[s]) for s in symbols},
        "bench": {s: encode(monthly[s]) for s in BENCH},
    }


def lab_section(prices: pd.DataFrame) -> str:
    return LAB.replace("$js", JS).replace(
        "$data", json.dumps(lab_data(prices), separators=(",", ":"))
    )


def method_section(prices: pd.DataFrame) -> str:
    return """<ul class="plain">
<li>Scores: the total return from month t − lookback to month t − 1 (skip on) or to t (skip off),
using month-end adjusted closes known at t. At each rebalance the stocks with a score and a price
are ranked; the top N are bought in equal weight and held, drifting with prices until the next
rebalance.</li>
<li>Costs: the cost per side times the value bought and sold at each rebalance, including the
first purchase from cash. A flat rate per side; real costs vary with stock and order size.</li>
<li>Tax is not modelled. A monthly rebalance realises most gains within a year, so short-term
capital gains tax would take a further share in a taxable account.</li>
<li>Survivorship: the universe is today’s NIFTY 200 applied to every past month. Stocks that fell
out of the index or were delisted are missing, and so are their losses, which flatters
momentum.</li>
<li>A stock without a price at the start or end of a month earns 0 that month. The latest month
is a part month, up to the last close.</li>
<li>Benchmark: NIFTYBEES (the NIFTY 50 ETF, with dividends), from its first month-end in the
data. Momentum and the ETF cover the same months.</li>
</ul>"""


SECTIONS = [
    (
        "Momentum lab",
        "Pick a lookback, how many stocks to hold, how often to rebalance and a cost per side. "
        "The page ranks today’s NIFTY 200 stocks by past return at each rebalance, holds the top "
        "ones in equal weight and charges the cost on every rupee traded. Research only, not "
        "investment advice: the universe is today’s list applied to the past, which is "
        "survivorship-biased and flatters momentum; costs are a flat rate per side and tax is "
        "not modelled.",
        lab_section,
    ),
    (
        "Method and caveats",
        "What the lab computes, and what it leaves out.",
        method_section,
    ),
]


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def build_html(prices: pd.DataFrame) -> str:
    parts, nav = [], []
    for title, blurb, make in SECTIONS:
        body = make(prices)
        sid = _slug(title)
        nav.append(f'<li><a href="#{sid}">{title}</a></li>')
        parts.append(f'<section id="{sid}">\n<h2>{title}</h2>\n<p>{blurb}</p>\n{body}\n</section>')
    d = plots.DARK
    return PAGE.substitute(
        icon=ICON,
        font=FONT,
        repo=REPO,
        updated=f"{prices.index[-1]:%d %b %Y}",
        surface=plots.SURFACE,
        text=plots.TEXT,
        text2=plots.TEXT_2,
        grid=plots.GRID,
        accent=plots.SERIES[0],
        accent2=plots.SERIES[1],
        muted=plots.MUTED,
        d_surface=d[plots.SURFACE],
        d_text=d[plots.TEXT],
        d_text2=d[plots.TEXT_2],
        d_grid=d[plots.GRID],
        d_accent=d[plots.SERIES[0]],
        d_accent2=d[plots.SERIES[1]],
        d_muted="#6b6a64",
        dark=json.dumps({k.lower(): v for k, v in d.items()}),
        dark_lines=json.dumps({k.lower(): v for k, v in plots.DARK_LINES.items()}),
        nav="\n".join(nav),
        sections="\n".join(parts),
    )
