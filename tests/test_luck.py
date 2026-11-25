import numpy as np
import pandas as pd

from mo.luck import luck_probability


def test_luck_probability_small_for_a_real_edge_and_middling_for_none():
    rng = np.random.default_rng(1)
    edge = pd.Series(rng.normal(0.02, 0.03, 150))
    noise = rng.normal(0.0, 0.03, 150)
    none = pd.Series(noise - noise.mean())  # exactly no edge
    assert luck_probability(edge, n=4000) < 0.01
    assert 0.3 < luck_probability(none, n=4000) < 0.7
