import numpy as np
import pandas as pd

from mo.momentum import backtest
from mo.tax import Ledger, buy_and_hold_after_tax, simulate


def _toy(seed=0, months=40, n=8):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-31", periods=months, freq="ME")
    px = pd.DataFrame(
        np.exp(np.cumsum(rng.normal(0.01, 0.08, (months, n)), axis=0)),
        index=idx,
        columns=[f"S{i}" for i in range(n)],
    )
    return px, px.pct_change(3)


def test_pretax_path_matches_backtest():
    px, sc = _toy()
    bt = backtest(px, sc, top_n=3, cost_per_side=0.0)
    sim = simulate(px, sc, capital=1.0, top_n=3, tax=False)
    assert np.allclose(sim["value"].to_numpy(), bt["equity"]["gross"].to_numpy())


def test_ledger_short_and_long_term_and_exemption():
    led = Ledger()
    d0 = pd.Timestamp("2020-01-31")
    led.buy("A", d0, 100, 100.0)
    led.sell("A", pd.Timestamp("2020-06-30"), 50, 120.0)  # short-term gain 1,000
    led.sell("A", pd.Timestamp("2021-03-31"), 50, 4000.0)  # long-term gain 195,000
    tax = led.year_end_tax()
    assert np.isclose(tax, (0.20 * 1000 + 0.125 * (195_000 - 125_000)) * 1.04)


def test_losses_carry_forward():
    led = Ledger()
    led.buy("A", pd.Timestamp("2020-01-31"), 10, 100.0)
    led.sell("A", pd.Timestamp("2020-02-29"), 10, 50.0)  # short-term loss 500
    assert led.year_end_tax() == 0 and led.carry_st == 500
    led.buy("B", pd.Timestamp("2020-04-30"), 10, 100.0)
    led.sell("B", pd.Timestamp("2020-05-31"), 10, 200.0)  # gain 1,000
    assert np.isclose(led.year_end_tax(), 0.20 * 500 * 1.04)


def test_buy_and_hold_pays_once_at_the_end():
    p = pd.Series(
        [100.0, 150.0, 200.0], index=pd.to_datetime(["2020-01-31", "2021-01-31", "2022-01-31"])
    )
    r = buy_and_hold_after_tax(p, 1_000_000)
    assert np.isclose(r["after selling"], 2_000_000 - 0.125 * 875_000 * 1.04)
