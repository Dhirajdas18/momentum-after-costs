import numpy as np
import pandas as pd

from mo.signals import _nse_score, evaluate, signal_panel


def _toy(seed=0, n=60, days=900):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-02", periods=days)
    drift = np.linspace(-0.001, 0.001, n)
    px = pd.DataFrame(np.exp(np.cumsum(rng.normal(drift, 0.01, (days, n)), axis=0)), index=idx,
                      columns=[f"S{i}" for i in range(n)])
    to = pd.DataFrame(rng.uniform(1, 2, (days, n)), index=idx, columns=px.columns)
    return px, to


def test_nse_score_is_positive_and_keeps_order():
    r6 = pd.Series([0.1, 0.2, -0.3, 0.0])
    r12 = pd.Series([0.2, 0.4, -0.5, 0.1])
    s = _nse_score(r6, r12)
    assert (s > 0).all() and list(s.rank()) == [3.0, 4.0, 1.0, 2.0]


def test_signals_at_t_ignore_later_prices():
    px, to = _toy()
    p1 = signal_panel(px, to, n=50, start="2013-06-01")
    t = p1["date"].iloc[0]
    px2 = px.copy()
    px2.loc[px2.index > t] *= 3.0
    p2 = signal_panel(px2, to, n=50, start="2013-06-01")
    a = p1[p1["date"] == t].set_index("symbol")
    b = p2[p2["date"] == t].set_index("symbol")
    cols = ["12-1", "6-1", "3-0", "12-0", "NSE-style volatility-adjusted"]
    assert np.allclose(a[cols].to_numpy(), b[cols].to_numpy(), equal_nan=True)


def test_evaluate_finds_a_planted_signal():
    px, to = _toy()
    p = signal_panel(px, to, n=60, start="2013-06-01")
    p["perfect"] = p["next"]
    e = evaluate(p, "perfect", top=10)
    assert e["IC"] > 0.99 and e["top minus universe, a year"] > 0
