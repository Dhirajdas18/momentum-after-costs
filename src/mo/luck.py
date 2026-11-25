"""How likely a monthly excess return this good is by luck: a circular block bootstrap.

The excess series is centred at zero (no true edge), then resampled in blocks of `block` consecutive
months (keeping the streaks and calm/stormy spells together) to the same length, many times. The
share of resamples whose average beats the real average is the chance of doing this well with no
edge at all (as in monte-carlo-stock-sim's luck test).
"""

import numpy as np
import pandas as pd


def luck_probability(excess: pd.Series, block: int = 12, n: int = 20_000, seed: int = 0) -> float:
    x = excess.dropna().to_numpy(float)
    centred = x - x.mean()
    t = len(x)
    rng = np.random.default_rng(seed)
    blocks = int(np.ceil(t / block))
    starts = rng.integers(0, t, size=(n, blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % t
    sims = centred[idx.reshape(n, -1)[:, :t]].mean(axis=1)
    return float((sims >= x.mean()).mean())
