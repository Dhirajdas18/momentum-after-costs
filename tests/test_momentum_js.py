import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mo import momentum as mom

JS = Path(__file__).resolve().parents[1] / "src" / "mo" / "momentum.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _node(expr: str):
    # The script goes in on stdin: Linux caps a single command-line argument at 128 KB.
    script = f"const m = require({json.dumps(str(JS))});console.log(JSON.stringify({expr}));"
    out = subprocess.run(["node", "-"], input=script, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _rows(df: pd.DataFrame) -> str:
    return json.dumps([[None if np.isnan(v) else float(v) for v in r] for r in df.to_numpy()])


def _book(seed=0, months=120, stocks=40):
    rng = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rng.normal(0.01, 0.08, (months, stocks)), axis=0))
    px[:30, 0] = np.nan  # a late listing
    px[50:53, 1] = np.nan  # a gap
    px[90:, 2] = np.nan  # delisted
    cols = [f"S{i:02d}" for i in range(stocks)]
    idx = pd.date_range("2010-01-31", periods=months, freq="ME")
    return pd.DataFrame(px, index=idx, columns=cols)


@pytest.mark.parametrize("look,skip", [(12, 1), (6, 0), (3, 1)])
def test_browser_momentum_matches_python(look, skip):
    px = _book()
    js = _node(f"m.momentum({_rows(px)}, {look}, {skip})")
    py = mom.momentum(px, look, skip).to_numpy()
    for jr, pr in zip(js, py, strict=True):
        assert [v is None for v in jr] == list(np.isnan(pr))
        assert [v for v in jr if v is not None] == pytest.approx(pr[~np.isnan(pr)], rel=1e-12)


@pytest.mark.parametrize("n,every,cost", [(10, 1, 0.003), (5, 3, 0.001), (40, 6, 0.0)])
def test_browser_backtest_matches_python(n, every, cost):
    px = _book(seed=n)
    score = mom.momentum(px, 12, 1)
    score.iloc[60, :5] = score.iloc[60, 5]  # ties keep column order in both
    js = _node(f"m.backtest({_rows(px)}, {_rows(score)}, {n}, {every}, {cost})")
    py = mom._backtest_arrays(px.to_numpy(), score.to_numpy(), n, every, cost)
    assert js["start"] == py["start"] and js["rebalances"] == py["rebalances"]
    assert js["holdings"] == py["holdings"]
    for jk, pk in [
        ("gross", "gross"),
        ("net", "net"),
        ("equityGross", "equity_gross"),
        ("equityNet", "equity_net"),
        ("turnover", "turnover"),
        ("cost", "cost"),
    ]:
        assert js[jk] == pytest.approx(py[pk].tolist(), rel=1e-9, abs=1e-12), jk
    res = mom.backtest(px, score, n, every, cost)
    dates = json.dumps(list(res["equity"].index.strftime("%Y-%m-%d")))
    stats = _node(
        f"(() => {{ const r = m.backtest({_rows(px)}, {_rows(score)}, {n}, {every}, {cost});"
        f"return [m.cagr(r.equityNet, {dates}), m.annualVol(r.net), m.maxDrawdown(r.equityNet)];"
        "})()"
    )
    want = [
        mom.cagr(res["equity"]["net"]),
        mom.annual_vol(res["net"]),
        mom.max_drawdown(res["equity"]["net"]),
    ]
    assert stats == pytest.approx(want, rel=1e-9)
