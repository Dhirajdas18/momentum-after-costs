"""README findings, one function per topic: `mo report <topic>` writes charts to out/."""

from collections.abc import Callable
from pathlib import Path

import pandas as pd


def prices() -> pd.DataFrame:
    """Adjusted closes of the universe, indices and ETFs with known Yahoo errors repaired."""
    from mo.data import DATA_PATH, clean_prices

    return clean_prices(pd.read_parquet(DATA_PATH)["adj_close"])


def returns() -> pd.DataFrame:
    from mo.data import DATA_PATH, daily_returns

    return daily_returns(pd.read_parquet(DATA_PATH)["adj_close"])


def last_years(df: pd.DataFrame, years: int) -> pd.DataFrame:
    return df.loc[df.index[-1] - pd.DateOffset(years=years) :]


REPORTS: dict[str, Callable[[Path], dict]] = {}
