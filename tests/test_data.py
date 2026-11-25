import numpy as np
import pandas as pd
import pytest

from mo.data import (
    ETFS,
    INDICES,
    SECTORS,
    SYMBOLS,
    clean_prices,
    daily_returns,
    missing_symbols,
    tickers,
)


def test_universe_snapshot_is_nifty200_with_industries():
    assert len(SYMBOLS) >= 190 and len(set(SYMBOLS)) == len(SYMBOLS)
    assert set(SECTORS) == set(SYMBOLS) and all(SECTORS.values())
    assert not (set(INDICES) | set(ETFS)) & set(SYMBOLS)


def test_yahoo_tickers():
    t = tickers(["NIFTY", "NIFTY200", "MOMENTUM", "M&M"])
    assert t == {"^NSEI": "NIFTY", "^CNX200": "NIFTY200", "MOMENTUM.NS": "MOMENTUM",
                 "M&M.NS": "M&M"}


def test_short_history_is_not_missing():
    idx = pd.bdate_range("2020-01-01", periods=4)
    adj = pd.DataFrame({"A": [1.0, 2, 3, 4], "B": [np.nan, np.nan, 5, 6], "C": np.nan}, index=idx)
    table = pd.concat({"adj_close": adj}, axis=1)
    assert missing_symbols(table, ["A", "B", "C", "D"]) == ["C", "D"]


def _fixes(tmp_path, rows):
    p = tmp_path / "fixes.csv"
    pd.DataFrame(rows, columns=["symbol", "date", "action", "reason"]).to_csv(p, index=False)
    return p


def test_zero_blank_and_start_fixes(tmp_path):
    idx = pd.bdate_range("2020-01-01", periods=5)
    px = pd.DataFrame({"A": [100.0, 50.0, 51.0, 52.0, 53.0],  # day 1: unadjusted split -> zero
                       "B": [10.0, 1.0, 10.5, 10.6, 10.7],    # day 1: bad print -> blank
                       "C": [99.0, 98.0, 5.0, 5.1, 5.2]},     # real history starts on day 2
                      index=idx)
    fixes = _fixes(tmp_path, [["A", idx[1].date(), "zero", ""], ["B", idx[1].date(), "blank", ""],
                              ["C", idx[2].date(), "start", ""]])
    r = daily_returns(px, fixes)
    assert r.loc[idx[1], "A"] == 0.0
    assert r.loc[idx[1], "B"] == 0.0 and r.loc[idx[2], "B"] == pytest.approx(0.05)
    assert r.loc[: idx[2], "C"].isna().all() and r.loc[idx[3], "C"] == pytest.approx(0.02)
    assert np.isfinite(r.loc[idx[3]]).all()
    p = clean_prices(px, fixes)
    assert p["A"].tolist() == pytest.approx([100, 100, 102, 104, 106])  # split undone in levels
    assert p.loc[: idx[1], "C"].isna().all() and p.loc[idx[2], "C"] == 5.0
    assert p["B"].tolist() == pytest.approx([10, 10, 10.5, 10.6, 10.7])
