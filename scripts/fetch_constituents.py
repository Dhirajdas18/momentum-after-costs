"""Refresh docs/data/nifty200.csv (symbol, industry) from NSE's NIFTY 200 list.

Pass a local copy of the file as an argument to skip the download:
fetch_constituents.py [ind_nifty200list.csv].
"""

import csv
import io
import sys
import urllib.request

from mo.data import CONSTITUENTS

URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv"
MIN_STOCKS = 190


def read(source: str) -> list[list[str]]:
    """CSV rows from a URL or a local path, every cell stripped of padding."""
    if source.startswith("https://"):
        req = urllib.request.Request(
            source, headers={"User-Agent": "momentum-after-costs/0.1 (research)"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8-sig")
    else:
        with open(source, encoding="utf-8-sig") as f:
            text = f.read()
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text)) if row]


def universe(rows: list[list[str]]) -> list[tuple[str, str]]:
    """(symbol, industry) for each stock in the list, sorted by symbol."""
    head = rows[0]
    sym, ind = head.index("Symbol"), head.index("Industry")
    return sorted({(r[sym], r[ind]) for r in rows[1:] if r[sym]})


def main() -> None:
    rows = universe(read(sys.argv[1] if len(sys.argv) > 1 else URL))
    if len(rows) < MIN_STOCKS:
        raise SystemExit(f"expected at least {MIN_STOCKS} stocks, got {len(rows)}; not overwriting")
    with open(CONSTITUENTS, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "industry"])
        w.writerows(rows)
    print(f"{len(rows)} NIFTY 200 stocks -> {CONSTITUENTS}")


if __name__ == "__main__":
    main()
