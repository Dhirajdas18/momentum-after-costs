# Momentum After Costs

[![CI](https://github.com/Dhirajdas18/momentum-after-costs/actions/workflows/ci.yml/badge.svg)](https://github.com/Dhirajdas18/momentum-after-costs/actions/workflows/ci.yml)
[![Dashboard](https://github.com/Dhirajdas18/momentum-after-costs/actions/workflows/pages.yml/badge.svg)](https://dhirajdas18.github.io/momentum-after-costs/)

Long-only momentum stock selection on NSE: buy the NIFTY 200 stocks that rose most, pay real
delivery charges every time the list changes, and compare what is left with NIFTY and with the
Nifty200 Momentum 30 index and its funds. Daily data from 2007; every score uses only prices known
at the time it is used.

**Live momentum lab: [dhirajdas18.github.io/momentum-after-costs](https://dhirajdas18.github.io/momentum-after-costs/)**,
pick a lookback, number of stocks, rebalance frequency and cost per side and see growth of ₹1 lakh
against the NIFTY ETF and today's ranking, computed in your browser; rebuilt every week from fresh
data by GitHub Actions.

## Features

- [x] The signal out of sample: 12-1, 6-1, 12-0 and 3-month returns and NSE's volatility-adjusted score
- [x] Survivorship and liquidity: a point-in-time universe against today's list, universe size, turnover rule
- [ ] Portfolio construction: number of stocks, weights and sector caps
- [ ] Costs and turnover: delivery charges, rebalance frequency and hold bands
- [ ] Tax: short- and long-term gains and holding periods
- [ ] Momentum crashes: a market filter and volatility scaling
- [ ] Against the Nifty200 Momentum 30 fund and NIFTY after costs and tax

## Findings

### 1. Twelve-month momentum works best volatility-adjusted; three months doesn't

<a href="docs/img/signal_compare.png"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/img/signal_compare.png"><img src="docs/img/signal_compare.gif" alt="Top 20 minus universe return by signal, and next-month return by quintile for three signals" width="720"></picture></a>

<a href="docs/img/signal_edge.png"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/img/signal_edge.png"><img src="docs/img/signal_edge.gif" alt="Cumulative edge of each signal's top 20 over an equal-weight universe, 2014-2026" width="720"></picture></a>

Each month-end from January 2014 to October 2026 (154 months) the universe is the day's 200 most-traded
NSE stocks priced at ₹50 or more with a year of history, by median turnover over 126 days, delisted
ones included (built from NSE's daily bhavcopy in a local archive; only these results are committed).
Every signal uses prices to that month-end; the outcome is the next month's return, before costs and
without dividends, with a stock that stops trading counted as sold at its last price. 12-1 is the return
from 12 months ago to 1 month ago; 12-0 includes the latest month; the NSE-style score averages 6- and
12-month returns each divided by a year's volatility (an approximation of the Nifty200 Momentum 30
method, without its weighting and buffers).

- **The top 20 beat the average stock with every 6-12 month signal.** By +10.6% a year with the
  NSE-style score, +9.2% with 12-0, +7.5% with 12-1 and +7.3% with 6-1. The rank correlation with next
  month's return was small but steady: 0.031 for the score and 0.033 for 12-1 (t 2.3 each).
- **Three months was noise.** Rank correlation 0.002 (t 0.2), −0.2% a year over 2014–19, and its top
  20 changed 54% a month against 29–34% for the 12-month signals.
- **Skipping the latest month didn't help here.** 12-0 kept +9.2% a year against 12-1's +7.5%, with
  about the same rank correlation; the textbook one-month reversal didn't show in these stocks.
- **Stronger lately.** The score's edge was +7.8% a year in 2014–19 and +13.1% in 2020–26; 12-1's was
  +4.7% and +9.9%.
- **Today's list flatters everything.** Applying today's NIFTY 200 to the same months, the average stock
  made 25.5% a year against 15.4% for the stocks that were actually most traded at the time, and 12-1's
  top-20 edge rose to +13.2% (finding 2 looks at this).
### 2. Today's list adds 9 points a year; the honest momentum edge is 12 points, but only in a wide universe

<a href="docs/img/universe_survivorship.png"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/img/universe_survivorship.png"><img src="docs/img/universe_survivorship.gif" alt="Growth of 100 for the top 20 and all stocks, on the point-in-time universe and on today's NIFTY 200, with NIFTY 50, 2014-2026" width="720"></picture></a>

<a href="docs/img/universe_size.png"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/img/universe_size.png"><img src="docs/img/universe_size.gif" alt="Top 20 against all stocks for universes of the 50, 100 and 200 most-traded stocks" width="560"></picture></a>

The rule: each month-end, hold the 20 stocks with the highest NSE-style score in equal weight; before
costs. Both universes use the archive's prices (no dividends, so the NIFTY lines are price indices
too), January 2014 to November 2026: the point-in-time universe of finding 1, or today's NIFTY 200
(194 of its 200 are in the archive) applied to every month.

- **Today's list adds 9 points a year.** The top 20 made 36.4% a year on today's NIFTY 200 against
  27.1% on the stocks that were actually most traded at the time; the average stock 23.2% against
  15.2%. NIFTY 50 made 11.8%, NIFTY 200 12.9%.
- **The honest edge is large.** On the point-in-time universe the top 20 beat the average stock by
  11.9 points a year, with a worst drawdown of −33.9% against −43.4%. Over those 13 years it held 403
  different stocks, only 166 of them in today's NIFTY 200; 39 stopped trading before the end.
- **Only in a wide universe.** Among the 50 most-traded stocks the top 20 beat the rest by 1.5 points
  a year, among 100 by 4.0, among 200 by 11.9: momentum's winners were mostly outside the largest names.
- **More than the index.** Over August 2020 to November 2026, when the archive has the Nifty200
  Momentum 30 price index, our top 30 rebalanced every 6 months made 25.9% a year against the index's
  16.2% (monthly correlation 0.89). Our version holds stocks in equal weight from the most-traded list;
  the index weights by score × market value within NIFTY 200. Finding 3 tests weighting.
- **Liquidity grew.** The number of the top 200 with a median daily turnover of ₹50 crore (the reference model's
  rule) rose from 64 in 2014 to 200 in 2026; keeping only those, the top 20 made 21.5% a year. A held
  stock traded a median ₹82 crore a day, so ₹50 lakh a stock (a ₹10 crore book) is 0.6% of a day.

## Quick start

```bash
uv sync
uv run python scripts/fetch_data.py         # Yahoo Finance -> data/prices.parquet
MO_LAKE_DIR=... uv run mo report signal     # also: universe; needs a local NSE bhavcopy archive
uv run python scripts/build_site.py         # momentum lab -> site/index.html
uv run pytest
```

`scripts/fetch_constituents.py` refreshes the stock list (`docs/data/nifty200.csv`) from NSE's
NIFTY 200 file. Event studies on delisted stocks can read a local NSE bhavcopy archive
(`MO_LAKE_DIR`, with `panel.parquet`); it is optional and not committed.

## Design

- `src/mo/universe.py`: the point-in-time universe (each day's 200 most-traded stocks at ₹50 or more
  with a year of history) from a local NSE bhavcopy archive set by `MO_LAKE_DIR`; findings that need it say so, and only their results are
  committed.
- `src/mo/signals.py`: the momentum signals and their monthly evaluation (rank IC, top 20 against the
  universe, quintiles).

- `src/mo/data.py`: Yahoo adjusted closes for today's NIFTY 200, NIFTY, NIFTY 200, the NIFTY ETF
  and two Nifty200 Momentum 30 funds (MOMENTUM, MOM30IETF) in one (field, symbol) table; known
  Yahoo errors (unadjusted corporate actions, bad prints, stale history) repaired from
  `docs/data/yahoo_fixes.csv`, each with its source; flags suspicious adjusted-price drops.
- `src/mo/momentum.py`: month-end prices, lookback/skip momentum, a Nifty200 Momentum 30 style
  volatility-adjusted score (an approximation of NSE's methodology), and a long-only top-N
  backtest with equal weights, drifting weights between rebalances and costs on traded value.
- `src/mo/momentum.js`: a line-for-line browser copy of `momentum.py` (without the
  volatility-adjusted score, which needs daily prices), tested against Python through Node.
- `src/mo/site.py`: the momentum lab, one static Plotly page; no server, no committed price data.
- `src/mo/reports.py`: README findings, reproducible with `mo report <topic>`.
- Conventions: decisions at month-end t use prices up to t only and trade at t's close; a held
  stock without a price for a month earns 0 that month; costs are a rate per side on the value
  bought and sold; CAGR is by calendar time.
- Survivorship: the universe is today's NIFTY 200, so stocks that left the index or were delisted
  are missing, which flatters momentum.
- Charts: one validated palette; README charts are animated GIFs with a static fallback for
  reduced-motion users.

Research only, not investment advice. MIT licence.
