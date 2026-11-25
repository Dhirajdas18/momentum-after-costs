import numpy as np
import pandas as pd

from mo.crash import drawdowns, market_filter, vol_scale


def test_market_filter_uses_last_month_and_pays_cash():
    idx = pd.date_range("2020-01-31", periods=14, freq="ME")
    market = pd.Series([100] * 10 + [50, 50, 200, 200], index=idx, dtype=float)
    r = pd.Series(0.05, index=idx)
    out, exp = market_filter(r, market, months=10, rf=0.12, cost=0.0)
    assert exp.iloc[11] == 0.0 and np.isclose(out.iloc[11], 0.01)  # decided at month 10 (below)
    assert exp.iloc[13] == 1.0  # month 12 back above


def test_vol_scale_never_borrows_and_ignores_the_future():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2015-01-31", periods=60, freq="ME")
    r = pd.Series(rng.normal(0.01, 0.08, 60), index=idx)
    _, e1 = vol_scale(r)
    r2 = r.copy()
    r2.iloc[40:] *= 5
    _, e2 = vol_scale(r2)
    assert (e1 <= 1).all() and np.allclose(e1.iloc[:41], e2.iloc[:41])


def test_drawdowns_finds_the_deepest():
    eq = pd.Series(
        [1, 2, 1, 3, 2.4, 3.5], index=pd.date_range("2020-01-31", periods=6, freq="ME"), dtype=float
    )
    d = drawdowns(eq, top=2)
    assert np.isclose(d["depth"].iloc[0], -0.5) and np.isclose(d["depth"].iloc[1], -0.2)
