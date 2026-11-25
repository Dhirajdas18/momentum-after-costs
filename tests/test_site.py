import json
import re
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from mo.data import SYMBOLS
from mo.site import BENCH, SCALE, build_html, encode, lab_data


def _prices():
    idx = pd.bdate_range("2008-01-01", "2026-11-25")
    cols = SYMBOLS + BENCH
    rng = np.random.default_rng(0)
    steps = rng.normal(0.0003, 0.015, (len(idx), len(cols)))
    px = pd.DataFrame(100 * np.exp(np.cumsum(steps, axis=0)), index=idx, columns=cols)
    px.iloc[:400, 0] = np.nan  # a recent listing
    px.iloc[:250, cols.index("NIFTYBEES")] = np.nan  # the ETF starts later
    return px


def test_encoding_round_trips_to_a_hundredth_of_a_percent():
    px = pd.Series([np.nan, np.nan, 101.3, 99.8, 102.45, 2500.0])
    enc = encode(px)
    assert enc[:2] == [None, None] and all(isinstance(v, int) for v in enc[2:])
    dec = np.cumsum(enc[2:]) / SCALE
    assert dec == pytest.approx(np.log(px[2:].to_numpy()), abs=0.5 / SCALE + 1e-12)


def test_lab_data_is_month_end_compact_and_keeps_gaps():
    d = lab_data(_prices())
    assert d["dates"][0] == "2008-01-31" and d["dates"][-1] == "2026-11-25"
    assert set(d["symbols"]) == set(SYMBOLS) and set(d["industries"]) == set(SYMBOLS)
    assert set(d["bench"]) == {"NIFTYBEES", "NIFTY"}
    first = SYMBOLS[0]
    assert d["px"][first][0] is None and isinstance(d["px"][first][-1], int)
    assert all(len(v) == len(d["dates"]) for v in d["px"].values())
    assert json.loads(json.dumps(d)) == d


def test_page_builds_without_placeholders_and_states_the_caveats():
    html = build_html(_prices())
    assert "function backtest" in html and 'id="momentum-lab"' in html
    assert "$" + "js" not in html and "$" + "data" not in html
    for words in ("not investment advice", "survivorship", "flat rate per side", "tax"):
        assert words in html
    assert len(html.encode()) < 1_500_000


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_page_scripts_parse():
    html = build_html(_prices())
    for i, src in enumerate(re.findall(r"<script>(.*?)</script>", html, re.S)):
        out = subprocess.run(["node", "--check", "-"], input=src, capture_output=True, text=True)
        assert out.returncode == 0, (i, out.stderr[:500])
