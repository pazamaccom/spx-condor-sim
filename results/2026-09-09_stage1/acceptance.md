# Acceptance tests — run `2026-09-09_stage1`

Data: 2004-01-02 to 2026-09-09; simulation 2005-01-03 to 2026-09-09.

| Test | Verdict |
|---|---|
| A1 | FAIL |
| A2 | PASS |
| A3 | FAIL |
| A4 | FAIL |
| A5 | PASS |
| Overall | FAIL |

## A1 — losing cycles in stress windows (filter OFF, variant A)

Losing cycle = realised P&L < 0. 'Exiting' attributes a cycle to the window of its exit date; 'active' counts cycles open on any day of the window. Verdict uses the exiting count.

| Window | Losers required | Cycles exiting | Losers exiting | Cycles active | Losers active | Worst cycle ($) | Worst MAE active ($) | Verdict |
|---|---|---|---|---|---|---|---|---|
| Oct 2008 | 1 | 1 | 1 | 1 | 1 | -102 | -309 | PASS |
| Feb 2018 | 1 | 1 | 0 | 1 | 0 | 250 | -1,939 | FAIL |
| Mar 2020 | 1 | 1 | 1 | 1 | 1 | -1,339 | -2,920 | PASS |
| 2022 | 3 | 16 | 3 | 16 | 3 | -1,607 | -2,187 | PASS |

## A2 — full-period Sharpe, premium P&L only, ex-cash

| Variant | Sharpe | Min | Max | Verdict |
|---|---|---|---|---|
| A | 1.00 | 0.40 | 1.20 | PASS |
| B | 0.77 | 0.40 | 1.20 | PASS |

Status: **PASS**.

## A3 — short-strike breach frequency across all cycles

finish = index close beyond the short strike on the exit day (the basis of the ranges in docs/strike-analysis.md); touch = intraday low/high beyond the strike on any day of the cycle after entry.

| Variant | Cycles | Put finish (%) | Put touch (%) | Put range | Put verdict | Call finish (%) | Call touch (%) | Call range | Call verdict |
|---|---|---|---|---|---|---|---|---|---|
| A | 282 | 0.35 | 1.42 | 2-5 | FAIL | 0.35 | 0.35 | 4-9 | FAIL |
| B | 282 | 0.35 | 1.42 | 2-5 | FAIL | 0.35 | 0.35 | 4-9 | FAIL |

Replication of docs/strike-analysis.md from this run's data (21-trading-day horizon, all days from 2005-02-28), first with the document's sigma (rv21 only) and then with the strategy's sigma definition:

| sigma definition | side | k | median distance (%) | finish beyond, all (%) | finish beyond, 2022 (%) | touch, all (%) | touch, 2022 (%) | windows |
|---|---|---|---|---|---|---|---|---|
| doc: rv21 only | put | 2.00 | 7.52 | 3.26 | 3.19 | 8.71 | 10.76 | 5,375 |
| doc: rv21 only | call | 1.50 | 5.64 | 6.60 | 1.59 | 11.78 | 5.98 | 5,375 |
| strategy: max(rv21, rv63, VIX) | put | 2.00 | 10.02 | 1.02 | 0.40 | 4.04 | 2.79 | 5,396 |
| strategy: max(rv21, rv63, VIX) | call | 1.50 | 7.51 | 0.67 | 0.80 | 1.26 | 0.80 | 5,396 |

## A4 — 1-day lag on all inputs (OHLC, VIX, VIX3M, VIX9D, DTB3)

| Variant | Metric | Base | Lag 1 | Change (%) | Verdict |
|---|---|---|---|---|---|
| A | Total premium P&L ($) | 48,264 | 50,434 | 4.50 | PASS |
| A | Final equity ($) | 646,670 | 649,079 | 0.37 | PASS |
| A | Net gain on book ($) | 246,670 | 249,079 | 0.98 | PASS |
| A | Sharpe, premium-only | 1.00 | 1.16 | 15.86 | FAIL |
| A | Premium-only max drawdown ($) | -6,588 | -5,123 | 22.24 | FAIL |
| A | Win rate (%) | 75.53 | 76.60 | 1.41 | PASS |
| A | Cycles | 282 | 282 | 0.00 | PASS |
| B | Total premium P&L ($) | 71,742 | 79,557 | 10.89 | FAIL |
| B | Final equity ($) | 675,058 | 683,985 | 1.32 | PASS |
| B | Net gain on book ($) | 275,058 | 283,985 | 3.25 | PASS |
| B | Sharpe, premium-only | 0.77 | 0.95 | 23.55 | FAIL |
| B | Premium-only max drawdown ($) | -14,627 | -12,854 | 12.12 | FAIL |
| B | Win rate (%) | 75.53 | 76.60 | 1.41 | PASS |
| B | Cycles | 282 | 282 | 0.00 | PASS |

Threshold: 10% on every metric listed.

## A5 — summary.md reproducible from trades.csv (scripts/verify_summary.py)

| Variant | Output | Verdict |
|---|---|---|
| A | A5 verify_summary [results/2026-09-09_stage1/variant_a]: PASS — 310/310 numbers reproduced | PASS |
| B | A5 verify_summary [results/2026-09-09_stage1/variant_b]: PASS — 310/310 numbers reproduced | PASS |
