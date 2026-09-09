# Stage 1 summary — variant A (fixed 2 contracts)

Run: `2026-09-09_stage1`. Simulation window: 2005-01-03 to 2026-09-09 (21.68 years). Book: $400,000. Config: `config.yaml` (frozen 2026-09-09, copied into this run folder).

All numbers below are recomputed from `trades.csv` (and `monthly.csv` for cash / book-equity figures) by `scripts/verify_summary.py`.

## Headline — premium P&L only (from trades.csv)

| Metric | Value |
|---|---|
| Cycles | 282 |
| Total premium P&L ($) | 48,264 |
| Premium-only CAGR (%) | 0.53 |
| Premium-only ann. vol (%) | 0.53 |
| Sharpe, premium-only ex-cash | 1.00 |
| Premium-only max drawdown ($) | -6,588 |
| Premium-only max drawdown (%) | -1.61 |
| Win rate (%) | 75.53 |
| Avg win ($) | 354 |
| Avg loss ($) | -392 |
| Profit factor | 2.78 |
| Profit-target exits | 153 |
| DTE exits | 129 |
| Expiry settlements | 0 |
| Avg days held | 13.98 |
| Avg contracts | 2.00 |
| Max contracts | 2 |
| Avg net credit (index pts) | 3.15 |
| Avg credit / width (%) | 7.59 |
| Put-side breach, finish (%) | 0.35 |
| Call-side breach, finish (%) | 0.35 |
| Put-side breach, touch (%) | 1.42 |
| Call-side breach, touch (%) | 0.35 |
| Same-expiry re-entries | 31 |

Premium-only max drawdown: peak 2017-12, trough 2020-02 (month-end basis).

## Book equity incl. cash (from monthly.csv)

| Metric | Value |
|---|---|
| Final equity ($) | 646,670 |
| Total cash interest ($) | 197,845 |
| Total premium P&L incl. open mark ($) | 48,825 |
| CAGR (%) | 2.24 |
| Ann. vol (%) | 0.73 |
| Max drawdown ($) | -3,569 |
| Max drawdown (%) | -0.75 |

Book max drawdown: peak 2017-12, trough 2018-01 (month-end basis).

## Worst 5 cycles

| Entry | Exit | Reason | Contracts | Short put | Short call | Exit spot | P&L ($) | MAE ($) |
|---|---|---|---|---|---|---|---|---|
| 2018-01-02 | 2018-01-26 | dte_exit | 2 | 2,510 | 2,835 | 2,873 | -4,175 | -4,155 |
| 2020-02-04 | 2020-02-28 | dte_exit | 2 | 2,925 | 3,575 | 2,954 | -3,007 | -2,987 |
| 2018-10-02 | 2018-10-26 | dte_exit | 2 | 2,675 | 3,110 | 2,659 | -2,847 | -2,898 |
| 2023-10-31 | 2023-11-24 | dte_exit | 2 | 3,660 | 4,595 | 4,559 | -2,767 | -2,956 |
| 2026-03-31 | 2026-04-24 | dte_exit | 2 | 5,370 | 7,395 | 7,165 | -1,804 | -1,960 |

## By calendar year (cycles attributed to exit year)

| Year | Cycles | Win rate (%) | Premium P&L ($) | Worst cycle ($) | Cash P&L ($) | Total P&L ($) | Year-end equity ($) |
|---|---|---|---|---|---|---|---|
| 2,005 | 12 | 33.33 | -603 | -322 | 12,873 | 12,270 | 412,270 |
| 2,006 | 12 | 58.33 | 245 | -109 | 20,283 | 20,528 | 432,798 |
| 2,007 | 11 | 72.73 | 150 | -346 | 19,767 | 19,917 | 452,715 |
| 2,008 | 9 | 44.44 | -407 | -260 | 6,384 | 5,977 | 458,692 |
| 2,009 | 11 | 36.36 | -562 | -437 | 687 | 125 | 458,817 |
| 2,010 | 12 | 50.00 | -100 | -324 | 636 | 535 | 459,352 |
| 2,011 | 11 | 54.55 | -71.24 | -228 | 244 | 172 | 459,525 |
| 2,012 | 12 | 83.33 | 954 | -148 | 403 | 1,357 | 460,882 |
| 2,013 | 12 | 83.33 | 970 | -108 | 266 | 1,236 | 462,118 |
| 2,014 | 12 | 83.33 | 1,734 | -139 | 151 | 1,885 | 464,003 |
| 2,015 | 13 | 84.62 | 1,346 | -697 | 237 | 1,583 | 465,586 |
| 2,016 | 13 | 92.31 | 1,988 | -402 | 1,484 | 3,472 | 469,057 |
| 2,017 | 13 | 100 | 3,833 | 70.13 | 4,438 | 8,271 | 477,328 |
| 2,018 | 14 | 57.14 | -5,781 | -4,175 | 9,439 | 3,658 | 480,986 |
| 2,019 | 15 | 73.33 | 2,039 | -213 | 10,198 | 12,236 | 493,222 |
| 2,020 | 10 | 90.00 | 340 | -3,007 | 1,831 | 2,171 | 495,394 |
| 2,021 | 18 | 100 | 10,807 | 367 | 231 | 11,038 | 506,432 |
| 2,022 | 16 | 81.25 | 1,785 | -1,607 | 10,395 | 12,180 | 518,612 |
| 2,023 | 15 | 80.00 | 2,734 | -2,767 | 27,607 | 30,341 | 548,953 |
| 2,024 | 15 | 93.33 | 9,093 | -4.68 | 29,012 | 38,106 | 587,058 |
| 2,025 | 15 | 93.33 | 10,900 | -235 | 25,031 | 35,931 | 622,989 |
| 2,026 | 11 | 81.82 | 6,870 | -1,804 | 16,250 | 23,681 | 646,670 |

## Event windows (cycles attributed to exit date; MAE over cycles active in the window)

| Window | Cycles exiting | Losing cycles | Premium P&L, exits ($) | Worst cycle ($) | Worst MAE, active cycles ($) | Premium P&L, monthly ($) | Total P&L, monthly ($) |
|---|---|---|---|---|---|---|---|
| 2008 | 9 | 5 | -407 | -260 | -525 | -407 | 5,977 |
| Feb 2018 | 1 | 0 | 250 | 250 | -1,939 | 260 | 836 |
| Mar 2020 | 0 | 0 | 0.00 | 0.00 | 0.00 | -0.00 | 158 |
| 2022 | 16 | 3 | 1,785 | -1,607 | -2,187 | 1,785 | 12,180 |
| Aug 2024 | 2 | 0 | 942 | 211 | -369 | 942 | 3,367 |
| Apr 2025 | 1 | 0 | 782 | 782 | -4,088 | 782 | 2,891 |
| Mar 2026 | 1 | 1 | -810 | -810 | -1,960 | -980 | 1,055 |

## Diagnostics

| Item | Value |
|---|---|
| entries_blocked_by_filter_days | 150 |
| expiries_skipped_filter | 31 |
| entries_skipped_nonpositive_credit | 30 |
| entries_skipped_zero_contracts | 0 |
| expiry_settlements | 0 |
| vol_floor_hits | 0 |
| same_expiry_reentries | 31 |
| first_vix3m_date | 2006-07-17 |
| open_position_at_end | {'entry_date': '2026-09-01', 'expiry': '2026-10-16', 'contracts': 2, 'credit_net': np.float64(10.065893669310901)} |
| n_trades | 282 |
| sim_start | 2005-01-03 |
| sim_end | 2026-09-09 |

## Assumptions affecting the numbers

1. **Pricing is synthetic.** Black-Scholes on the index, r = DTB3 converted from bank-discount basis to a continuously-compounded actual/365 rate (91-day bill), q = 1.5% continuous, T = calendar days / 365. Stage 2 replaces this with real option prices.
2. **Volatility surface.** ATM vol for tenor T is VIX (30d) and VIX3M (90d) interpolated linearly in total variance vs calendar days, extrapolated on the same line below 30 days (needed for marks between 21 and 30 DTE). Vol floor 1%; floor hits are counted in diagnostics. Skew is one smile in strike space: +0.8 vol pts per 1% below spot, -0.3 vol pts per 1% above spot — applied by strike, not by option type (put-call parity consistent). VIX9D is downloaded but not used by any pre-registered rule.
3. **VIX3M availability.** VIX3M history starts 2006-07-17. Before that the term structure is flat at VIX and the VIX > VIX3M filter cannot trigger (treated as not inverted). Affects Jan 2005 - Jul 2006 only.
4. **Fills and costs.** Every leg crosses 0.1 index points of spread on entry and on exit (0.40/condor each way). Commission $1.25 per leg per contract each way ($10 per contract round trip). Expiry settlement (guard path only) is cash-settled at intrinsic with no spread and no exit commission.
5. **Entry credit** is the net credit after spread. The 50% profit-take test uses the executable exit cost (mid + spread): captured = (credit_net - debit_net) / credit_net >= 50%. Checked at each daily close from the day after entry.
6. **Exit precedence.** At a close where both the profit target and DTE <= 21 hold, the exit is labelled profit_target.
7. **Entry timing.** An entry is attempted at every close on which some monthly expiry is 30-45 calendar days ahead and no position is open; if the filter blocks, the next close is tried while the window holds. Consequently a quick profit-take can be followed by a second cycle on the same expiry ("same-expiry re-entries", counted in the headline table). Entries where the mid credit is below the round-trip spread (net credit <= 0) are skipped and counted in diagnostics.
8. **Strikes.** Short strikes rounded to the 5-point grid first; width = 100 points if spot >= 6000 else 1.3% of spot, rounded to the grid (min one grid step); long strikes = short -/+ width.
9. **Realised vol** = stdev of daily log returns over the trailing 21 / 63 trading days ending at the entry close, annualised with sqrt(252). VIX-implied = VIX/100. sigma_H = max of the three x sqrt(DTE/365).
10. **Sizing B** uses equity at the entry close (= cash, as no position is open) and max loss = (width - credit_net) x 100.
11. **Cash** accrues daily at the previous close's DTB3-derived rate for the calendar days elapsed, on the whole cash balance (defined-risk spreads; no margin is deducted). Open positions are marked at cost-to-close incl. spread, excluding the exit commission.
12. **Premium-only statistics** (the A2 Sharpe) attribute each cycle's realised P&L to its exit month, ignore the open-position mark, use returns on the previous month's premium-only equity starting from $400,000, and Sharpe = mean / stdev x sqrt(12) with no further risk-free deduction (cash is already excluded). Months with no exits count as zero-return months.
13. **Breach definitions.** "finish" = index close beyond the short strike on the cycle's exit day; "touch" = daily low/high beyond the short strike on any day after entry up to and including exit. A3 is judged on the finish basis (the basis of the 2-5% / 4-9% ranges in docs/strike-analysis.md).
14. **Drawdowns** are on month-end values (with the starting book as the first peak), so intra-month drawdowns are understated.
15. **Book.** All dollar figures are on the $400,000 book. Python 3.14.3 rather than 3.12 (the brief's stack); no behavioural difference expected.
