import numpy as np
import pandas as pd
import pytest

from mo.momentum import (
    annual_vol,
    backtest,
    cagr,
    max_drawdown,
    momentum,
    month_end_prices,
    vol_adjusted_score,
)


def _monthly(rows, cols=("A", "B", "C")):
    idx = pd.date_range("2020-01-31", periods=len(rows), freq="ME")
    return pd.DataFrame(rows, index=idx, columns=list(cols), dtype=float)


def test_month_end_prices_takes_the_last_available_price_each_month():
    idx = pd.to_datetime(["2020-01-02", "2020-01-30", "2020-01-31", "2020-02-03", "2020-02-28"])
    px = pd.DataFrame({"A": [1.0, 2, 3, 4, 5], "B": [10.0, 11, np.nan, 12, np.nan]}, index=idx)
    m = month_end_prices(px)
    assert list(m.index) == list(pd.to_datetime(["2020-01-31", "2020-02-28"]))
    assert m["A"].tolist() == [3, 5]
    assert m["B"].tolist() == [11, 12]  # last price it had in the month


def test_momentum_is_return_from_t_minus_lookback_to_t_minus_skip():
    m = _monthly([[100, 50, 10], [110, 50, 10], [121, 55, 10], [133.1, 60, np.nan]])
    r = momentum(m, lookback=3, skip=1)
    assert r.iloc[:3].isna().all().all()
    assert r.iloc[3]["A"] == pytest.approx(121 / 100 - 1)  # months 0 -> 2, month 3 skipped
    assert r.iloc[3]["B"] == pytest.approx(55 / 50 - 1)
    assert r.iloc[3]["C"] == pytest.approx(0.0)  # price at t is not needed
    r0 = momentum(m, lookback=2, skip=0)
    assert r0.iloc[3]["A"] == pytest.approx(133.1 / 110 - 1) and np.isnan(r0.iloc[3]["C"])
    with pytest.raises(ValueError):
        momentum(m, 3, 3)


def test_vol_adjusted_score_matches_a_hand_calculation():
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2019-01-01", "2020-12-31")
    vols = np.array([0.01, 0.02, 0.015, 0.03])
    drift = np.array([0.001, 0.0005, -0.0002, 0.0012])
    logp = np.cumsum(drift + vols * rng.normal(size=(len(idx), 4)), axis=0)
    daily = pd.DataFrame(100 * np.exp(logp), index=idx, columns=list("ABCD"))
    score = vol_adjusted_score(daily)
    d = score.index[-1]
    assert d == pd.Timestamp("2020-12-31")
    last = month_end_prices(daily)
    lr = np.log(daily).diff().loc[d - pd.Timedelta(days=364) : d]
    vol = lr.std() * np.sqrt(252)
    ratios = [(last.iloc[-1] / last.iloc[-1 - m] - 1) / vol for m in (6, 12)]
    z = sum((r - r.mean()) / r.std() for r in ratios) / 2
    want = np.where(z >= 0, 1 + z, 1 / (1 - z))
    assert score.loc[d].to_numpy() == pytest.approx(want, rel=1e-12)
    assert (score.dropna(how="all") > 0).all().all()
    assert score.iloc[:12].isna().all().all()  # needs a 12-month return
    assert list(vol_adjusted_score(daily, score.index[-2:]).index) == list(score.index[-2:])


def test_backtest_toy_example_with_costs():
    # Month 0 ranks C > B > A; month 1 ranks A first.
    px = _monthly([[100, 100, 100], [110, 100, 90], [121, 105, 90], [121, 105, 99]])
    score = _monthly([[1, 2, 3], [3, 2, 1], [3, 2, 1], [np.nan] * 3])
    res = backtest(px, score, top_n=1, rebalance_every=1, cost_per_side=0.01)
    assert res["holdings"] == {px.index[0]: ["C"], px.index[1]: ["A"], px.index[2]: ["A"]}
    assert res["gross"].tolist() == pytest.approx([-0.10, 0.10, 0.0])
    assert res["turnover"].tolist() == pytest.approx([1.0, 2.0, 0.0])
    # Costs are charged to the month after each trade.
    assert res["net"].tolist() == pytest.approx([0.9 * 0.99 - 1, 1.1 * 0.98 - 1, 0.0])
    assert res["equity"]["net"].iloc[-1] == pytest.approx(0.9 * 0.99 * 1.1 * 0.98)
    assert res["cost"].sum() == pytest.approx(0.03)


def test_equal_weights_sum_to_one():
    px = _monthly([[100, 50, 20], [110, 55, 22], [110, 55, 22]])
    score = _monthly([[1, 2, 3], [1, 2, 3], [1, 2, 3]])
    res = backtest(px, score, top_n=2, cost_per_side=0.0)
    assert res["turnover"].iloc[0] == pytest.approx(1.0)  # bought from cash
    assert res["gross"].iloc[0] == pytest.approx(0.10)  # every stock +10% -> portfolio +10%
    assert res["holdings"][px.index[0]] == ["C", "B"]
    few = backtest(px, score.where(score > 2), top_n=5, cost_per_side=0.0)
    assert few["holdings"][px.index[0]] == ["C"]  # fewer qualify than top_n: hold them all


def test_weights_drift_between_rebalances():
    px = _monthly([[100, 100], [200, 100], [200, 100], [200, 100]], cols="AB")
    score = _monthly([[1, 1]] * 4, cols="AB")
    res = backtest(px, score, top_n=2, rebalance_every=2, cost_per_side=0.0)
    # After A doubles the book is 2/3 A, 1/3 B; month 2 earns nothing; rebalance back to 50/50.
    assert list(res["turnover"].index) == [px.index[0], px.index[2]]
    assert res["turnover"].iloc[1] == pytest.approx(2 * (2 / 3 - 1 / 2))


def test_turnover_is_zero_when_holdings_do_not_change():
    rng = np.random.default_rng(3)
    common = np.cumprod(1 + rng.normal(0.01, 0.05, 24))
    px = _monthly(np.outer(common, [100, 50, 10]).tolist())  # same returns: weights stay equal
    score = _monthly([[3, 2, 1]] * 24)
    res = backtest(px, score, top_n=2, cost_per_side=0.003)
    assert res["turnover"].iloc[0] == pytest.approx(1.0)
    assert res["turnover"].iloc[1:].to_numpy() == pytest.approx(0.0, abs=1e-12)
    assert res["net"].iloc[1:].to_numpy() == pytest.approx(res["gross"].iloc[1:].to_numpy())


def test_a_stock_with_no_next_price_counts_as_cash():
    px = _monthly([[100, 100], [np.nan, 120], [np.nan, 120]], cols="AB")
    score = _monthly([[2, 1], [np.nan, 1], [np.nan, 1]], cols="AB")
    res = backtest(px, score, top_n=1, cost_per_side=0.0)
    assert res["holdings"][px.index[0]] == ["A"]
    assert res["gross"].iloc[0] == 0.0
    assert res["holdings"][px.index[1]] == ["B"]  # A has no price, so it can't be picked


def _random_book(seed=0, months=60, stocks=15):
    rng = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rng.normal(0.01, 0.08, (months, stocks)), axis=0))
    px[:20, 0] = np.nan  # a late listing
    px[40:43, 1] = np.nan  # a gap
    cols = [f"S{i:02d}" for i in range(stocks)]
    return pd.DataFrame(
        px, index=pd.date_range("2015-01-31", periods=months, freq="ME"), columns=cols
    )


def test_no_look_ahead_future_prices_do_not_change_holdings():
    px = _random_book()
    t = 30
    base = backtest(px, momentum(px, 12, 1), top_n=5)
    changed = px.copy()
    changed.iloc[t + 1 :] *= np.random.default_rng(9).uniform(0.2, 5.0, changed.iloc[t + 1 :].shape)
    alt = backtest(changed, momentum(changed, 12, 1), top_n=5)
    for d in px.index[: t + 1]:
        if d in base["holdings"]:
            assert alt["holdings"][d] == base["holdings"][d]
    assert any(alt["holdings"][d] != base["holdings"][d] for d in px.index[t + 1 : -1])
    assert alt["gross"].loc[: px.index[t]].tolist() == base["gross"].loc[: px.index[t]].tolist()


def test_rejects_other_weightings():
    px = _random_book()
    with pytest.raises(ValueError):
        backtest(px, momentum(px), weights="score")


def test_summary_stats():
    eq = pd.Series(
        [1.0, 1.2, 0.9, 1.21],
        index=pd.to_datetime(["2020-01-01", "2020-07-01", "2021-01-01", "2022-01-01"]),
    )
    assert cagr(eq) == pytest.approx(1.21 ** (365.25 / 731) - 1)
    assert max_drawdown(eq) == pytest.approx(0.9 / 1.2 - 1)
    r = pd.Series([0.01, -0.02, 0.03])
    assert annual_vol(r) == pytest.approx(np.std(r, ddof=1) * np.sqrt(12))


def test_tilt_group_cap_and_weight_cap():
    import numpy as np
    import pandas as pd

    from mo.momentum import _cap_weights, backtest

    idx = pd.date_range("2020-01-31", periods=4, freq="ME")
    px = pd.DataFrame(
        {"A": [1, 1.1, 1.2, 1.3], "B": [1, 1, 1, 1], "C": [1, 0.9, 0.8, 0.7]}, index=idx
    )
    sc = pd.DataFrame(
        {"A": [3, 3, 3, 3], "B": [2, 2, 2, 2], "C": [1, 1, 1, 1]}, index=idx, dtype=float
    )
    tilt = pd.DataFrame({"A": [3.0] * 4, "B": [1.0] * 4, "C": [1.0] * 4}, index=idx)
    bt = backtest(px, sc, top_n=2, cost_per_side=0.0, tilt=tilt)
    assert np.isclose(bt["gross"].iloc[0], 0.75 * 0.1 + 0.25 * 0.0)
    g = backtest(
        px, sc, top_n=2, cost_per_side=0.0, group={"A": "x", "B": "x", "C": "y"}, max_per_group=1
    )
    assert g["holdings"][idx[0]] == ["A", "C"]
    w = _cap_weights(np.array([0.7, 0.2, 0.1]), 0.5)
    assert np.isclose(w.sum(), 1) and w.max() <= 0.5 + 1e-12


def test_hold_band_keeps_a_slipping_winner_without_trimming():
    import numpy as np
    import pandas as pd

    from mo.momentum import backtest

    idx = pd.date_range("2020-01-31", periods=4, freq="ME")
    px = pd.DataFrame(
        {"A": [1, 2, 2, 2], "B": [1, 1, 1, 1], "C": [1, 1, 1, 1]}, index=idx, dtype=float
    )
    sc = pd.DataFrame(
        {"A": [3, 1, 1, 1], "B": [2, 3, 3, 3], "C": [1, 2, 2, 2]}, index=idx, dtype=float
    )
    plain = backtest(px, sc, top_n=2, cost_per_side=0.0)
    band = backtest(px, sc, top_n=2, cost_per_side=0.0, keep_rank=3)
    assert plain["holdings"][idx[1]] == ["B", "C"]
    assert set(band["holdings"][idx[1]]) == {"A", "B"}  # A ranks 3rd: kept
    assert band["turnover"].iloc[1] == 0  # nothing traded, A not trimmed back to half
    assert np.isclose(band["turnover"].iloc[0], 1.0)


def test_delivery_costs_charge_sells_and_a_fixed_fee_per_stock_sold():
    import numpy as np
    import pandas as pd

    from mo.momentum import backtest

    idx = pd.date_range("2020-01-31", periods=3, freq="ME")
    px = pd.DataFrame({"A": [1, 1, 1], "B": [1, 1, 1]}, index=idx, dtype=float)
    sc = pd.DataFrame({"A": [2, 1, 1], "B": [1, 2, 2]}, index=idx, dtype=float)
    bt = backtest(px, sc, top_n=1, costs=(0.01, 0.02, 100.0, 10_000.0))
    assert np.isclose(bt["cost"].iloc[0], 0.01)  # buy A from cash
    assert np.isclose(bt["cost"].iloc[1], 0.01 + 0.02 + 100 / (10_000 * (1 - 0.01)))
