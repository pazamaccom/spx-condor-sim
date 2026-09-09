# Strike-distance analysis (reference for acceptance test A3)

Date: 2026-09-09
Data: daily S&P 500 OHLC, 2005-02-28 to 2026-09-08 (~5,400 rolling windows).
Horizon: 21 trading days (~30 calendar days).

## Method

For every day, measure the index 21 trading days later ("finish") and the min low / max high over the window ("touch"). Count how often each threshold is crossed.

## Fixed percentage distances (30-day horizon)

| Move | Finish beyond, all | Finish beyond, 2022 | Touch, all | Touch, 2022 |
|---|---|---|---|---|
| -5% | 8.7% | 30% | 21% | 57% |
| -7% | 4.7% | 20% | 12% | 46% |
| -10% | 2.0% | 6% | 6% | 22% |
| +4% | 19% | 29% | 31% | 47% |
| +5% | 12% | 22% | 20% | 37% |
| +7% | 4.4% | 10% | 8% | 23% |

Finding: a fixed distance is regime-dependent. A 7% put distance is breached ~5% of the time in normal years and ~20% in a hiking year.

## Volatility-scaled distances (30-day horizon)

sigma = trailing 21-day realised daily vol x sqrt(21). Strikes at k x sigma.

| Distance | Median distance | Finish beyond, all | Finish beyond, 2022 | Touch, all | Touch, 2022 |
|---|---|---|---|---|---|
| 1.5s down | 5.6% | 6.6% | 9.6% | 16% | 26% |
| 2.0s down | 7.5% | 3.3% | 3.2% | 8.7% | 11% |
| 2.5s down | 9.4% | 1.6% | 1.2% | 5.0% | 3.6% |
| 1.5s up | 5.6% | 6.6% | 1.6% | 12% | 6% |
| 2.0s up | 7.5% | 1.9% | 0% | 3.3% | 0% |

Finding: at 2.0 sigma the put-side breach rate is ~3% in every regime including 2022; the strike widens automatically when vol rises. Upside is asymmetric: rallies are gradual, so call breaches at 1.5 sigma are ~7% overall and near zero in a hiking year.

## Rules adopted

- Short put at 2.0 sigma below spot; short call at 1.5 sigma above spot.
- sigma input = max(21-day realised, 63-day realised, VIX-implied), scaled to actual days to expiry. Never the 21-day window alone (it under-states vol in quiet periods; on 2026-09-08 it gave a 30-day sigma of 2.4% vs 3.6% on 63-day).
- Expected breach frequencies for A3: put side 2-5%, call side 4-9%.

## Caveats

- 2022 rows are ~230 overlapping windows from one year; directional, not precise.
- Touch frequencies overstate what a 21-DTE exit rule would experience, since the last three weeks of each window are excluded in the strategy.
