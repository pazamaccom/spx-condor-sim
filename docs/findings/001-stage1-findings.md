# Findings 001 — Stage 1 backtester (synthetic pricing)

Date: 2026-09-09 · Run: [`results/2026-09-09_stage1/`](../../results/2026-09-09_stage1/) · Commit: `2617ea8` · Brief: [001](../briefs/001-stage1-backtester.md) · Config: [`config.yaml`](../../config.yaml) (frozen, unchanged)

**Status: acceptance gate NOT passed.** A2 and A5 pass; A1, A3 and A4 fail. Under the brief's rule the performance figures in §4 are **NOT VERIFIED** and are recorded here for completeness only. No strategy parameter was changed on the basis of these results; proposed amendments are in §7 and require a `docs/amendments.md` entry plus a new config file before any re-run.

---

## 1. What was run

| Item | Value |
|---|---|
| Data | `^GSPC` OHLC, `^VIX`, `^VIX3M`, `^VIX9D` (yfinance, Cboe CSV fallback), FRED `DTB3`; 2004-01-02 to 2026-09-09 |
| Simulation window | 2005-01-03 to 2026-09-09 (21.68 years, 5,456 trading days) |
| Cycles | 282 (both variants; sizing does not change the cycle set) |
| Variant A | fixed 2 contracts on a $400,000 book |
| Variant B | contracts = floor(0.035 × equity / max loss), recomputed at each entry; 2–16 contracts, mean 6.2 |
| Pricing | Black-Scholes, r = DTB3 (discount → continuous), q = 1.5 %, VIX/VIX3M variance-time tenor scaling, fixed skew +0.8 / −0.3 vol pts per 1 % OTM, 0.10 pts/leg spread, $1.25/leg/contract |
| Engine | `src/spx_condor/`; runner `scripts/run_stage1.py`; verifier `scripts/verify_summary.py` |

Pricing sanity checks: Black-Scholes matches the textbook reference (10.4506 / 5.5735) to 4 dp; tenor interpolation returns VIX at 30 days and VIX3M at 90 days; the cash/equity accounting identity (final equity = book + interest + realised P&L + open-position value) holds to 1e-9; the vol floor was never hit.

## 2. Acceptance tests

| Test | Verdict | Result |
|---|---|---|
| A1 losing cycles in stress windows (filter off) | **FAIL** | Oct 2008 ✓ · Feb 2018 ✗ (+$250) · Mar 2020 ✓ · 2022 ✓ (3 losers — exactly the minimum) |
| A2 Sharpe, premium only, ex-cash, in 0.4–1.2 | PASS | A = 1.00 · B = 0.77 |
| A3 breach frequency: put 2–5 %, call 4–9 % | **FAIL** | put 0.35 % · call 0.35 % (finish basis); touch basis 1.42 % / 0.35 % |
| A4 1-day lag on all inputs changes results ≤ 10 % | **FAIL** | final equity 0.4 % / 1.3 % ✓ · premium P&L 4.5 % ✓ / 10.9 % ✗ · Sharpe 16 % / 24 % ✗ · premium max-DD 22 % / 12 % ✗ (A / B) |
| A5 summary.md reproducible from trades.csv | PASS | 310 / 310 numbers reproduced per variant by an independent script |

Full tables: [`acceptance.md`](../../results/2026-09-09_stage1/acceptance.md).

### 2.1 A1 — why there is no Feb 2018 loser

The cycle open through the 5–8 Feb 2018 spike was entered 2018-01-30: short put 2530, net credit $590 (2 contracts). The intraday low on Feb 9 was 2532 — the strike was never breached. The mark bottomed at −$2,529 on Feb 8 (MAE −$1,939, 3.3× the credit), then recovered with the index; the 21-DTE exit on Feb 23 closed the cycle at **+$250**.

There is no stop-loss rule, so the pre-registered rules cannot realise that loss. The 2018 loss landed in **January** instead: the 2018-01-02 cycle's short call (2835) was breached by the melt-up and closed −$4,175 on Jan 26 — the worst cycle in the whole run.

Verdict: the pricing and exit logic behaved as specified; the test criterion assumed the exit would land inside the drawdown.

### 2.2 A3 — why breach rates are far below the range

`docs/strike-analysis.md` was replicated from this run's data and matches (finish 3.26 % / 6.60 % vs doc 3.3 % / 6.6 %; touch 8.71 % / 11.78 % vs 8.7 % / 12 %), so data and measurement are consistent. The gap is structural:

| Sigma definition (30-day horizon, all days) | Put median distance | Put finish | Call median distance | Call finish |
|---|---|---|---|---|
| rv21 only — the basis of the doc's table and of the A3 ranges | 7.5 % | 3.3 % | 5.6 % | 6.6 % |
| max(rv21, rv63, VIX) — the rule the same doc adopts | 10.0 % | 1.0 % | 7.5 % | 0.7 % |
| … and the 21-DTE / 50 % exit (executed cycles, avg 14 days held, 45 DTE at entry) | 11.8 % | 0.35 % | 8.9 % | 0.35 % |

The 2–5 % / 4–9 % ranges were calibrated on rv21-only strikes held for the full window. With the adopted sigma rule the expected rate is under 1 %, i.e. ~1 event per side in 282 cycles — a numeric range cannot be tested at that rate.

### 2.3 A4 — lag sensitivity

"1-day lag on all inputs" was implemented as a one-trading-day shift of OHLC, VIX, VIX3M, VIX9D and DTB3. Results **improve** under the lag (A: premium P&L $48,264 → $50,434; Sharpe 1.00 → 1.16), which is evidence *against* look-ahead — leaked information would hurt when removed. Final equity and cycle count are stable. Sharpe and max drawdown are ratios/extremes of small numbers: the standard error of a 21.7-year Sharpe is ≈ 0.26, so a 0.16 move is within noise. The test fails on the literal threshold because it does not say which metric the 10 % applies to.

## 3. Diagnostics (variant A; B identical unless stated)

| Item | Value |
|---|---|
| Entry days blocked by VIX > VIX3M | 150 |
| Expiries with no cycle because the filter held through the window | 31 |
| Entry days skipped because net credit ≤ 0 (mid credit below 0.40 round-trip spread) | 30 — all 2005–06, when widths were 15 pts |
| Same-expiry re-entries (second cycle on an expiry after a quick profit-take) | 31 |
| Expiry settlements (guard path) | 0 |
| Cycles whose adverse mark reached ≥ 1× the credit | 75 of 282; 25 of them recovered to a profit by the exit |
| Exits | 153 profit-target, 129 DTE |
| VIX3M history starts | 2006-07-17 — before that the filter cannot trigger and the term structure is flat at VIX |
| Mar 2020 | filter blocked every entry day; no cycle was open in March (the filter-off run loses −$1,339 there) |

## 4. Performance figures — NOT VERIFIED

All dollar figures on the $400,000 book. Premium-only statistics attribute each cycle to its exit month and exclude cash interest. Drawdowns are month-end. Source: [`variant_a/summary.md`](../../results/2026-09-09_stage1/variant_a/summary.md), [`variant_b/summary.md`](../../results/2026-09-09_stage1/variant_b/summary.md).

| Metric | Variant A | Variant B |
|---|---|---|
| Total premium P&L | $48,264 | $71,742 |
| Total cash interest | $197,845 | $202,756 |
| Final equity | $646,670 | $675,058 |
| CAGR, book | 2.24 % | 2.44 % |
| CAGR, premium only | 0.53 % | 0.76 % |
| Ann. vol, premium only | 0.53 % | 0.99 % |
| Sharpe, premium only ex-cash | 1.00 | 0.77 |
| Max drawdown, premium only | −$6,588 (−1.61 %), 2017-12 → 2020-02 | −$14,627 (−3.44 %), 2017-12 → 2020-02 |
| Max drawdown, book | −$3,569 (−0.75 %), 2017-12 → 2018-01 | −$9,826 (−1.99 %), 2017-12 → 2018-01 |
| Win rate | 75.5 % | 75.5 % |
| Avg win / avg loss | $354 / −$392 | $663 / −$1,006 |
| Profit factor | 2.78 | 2.03 |
| Avg net credit per contract | 3.15 pts ($315) | 3.15 pts |
| Avg credit / width | 7.6 % | 7.6 % |

Worst five cycles (variant A; variant B has the same cycles at 4–5 contracts, worst −$10,438):

| Entry | Exit | Reason | Short put | Short call | Exit spot | P&L | MAE |
|---|---|---|---|---|---|---|---|
| 2018-01-02 | 2018-01-26 | DTE | 2,510 | 2,835 | 2,873 | −$4,175 | −$4,155 |
| 2020-02-04 | 2020-02-28 | DTE | 2,925 | 3,575 | 2,954 | −$3,007 | −$2,987 |
| 2018-10-02 | 2018-10-26 | DTE | 2,675 | 3,110 | 2,659 | −$2,847 | −$2,898 |
| 2023-10-31 | 2023-11-24 | DTE | 3,660 | 4,595 | 4,559 | −$2,767 | −$2,956 |
| 2026-03-31 | 2026-04-24 | DTE | 5,370 | 7,395 | 7,165 | −$1,804 | −$1,960 |

Event windows (variant A; cycles attributed to exit date; MAE over cycles active in the window):

| Window | Cycles | Losers | Premium P&L | Worst cycle | Worst MAE |
|---|---|---|---|---|---|
| 2008 | 9 | 5 | −$407 | −$260 | −$525 |
| Feb 2018 | 1 | 0 | $250 | $250 | −$1,939 |
| Mar 2020 | 0 | 0 | — | — | — (filter blocked entry) |
| 2022 | 16 | 3 | $1,785 | −$1,607 | −$2,187 |
| Aug 2024 | 2 | 0 | $942 | $211 | −$369 |
| Apr 2025 | 1 | 0 | $782 | $782 | −$4,088 |
| Mar 2026 | 1 | 1 | −$810 | −$810 | −$1,960 |

By calendar year (variant A, premium P&L): 2005 −$603 · 2006 $245 · 2007 $150 · 2008 −$407 · 2009 −$562 · 2010 −$100 · 2011 −$71 · 2012 $954 · 2013 $970 · 2014 $1,734 · 2015 $1,346 · 2016 $1,988 · 2017 $3,833 · 2018 −$5,781 · 2019 $2,039 · 2020 $340 · 2021 $10,807 · 2022 $1,785 · 2023 $2,734 · 2024 $9,093 · 2025 $10,900 · 2026 YTD $6,870. The 2005–2011 figures are tiny because a 2-contract position on a 15–20-point-wide spread risks under $3,000; the pre-2012 years are effectively a test of the rules, not of the strategy's economics.

Equity curves with filter-active periods shaded: [`variant_a/equity_curve.png`](../../results/2026-09-09_stage1/variant_a/equity_curve.png), [`variant_b/equity_curve.png`](../../results/2026-09-09_stage1/variant_b/equity_curve.png).

## 5. Strategy observations (for stage 2 — not acted on)

1. **No stop loss; the rules rely on recovery inside the window.** 75 of 282 cycles reached an adverse mark of at least the full credit and 25 of those still closed profitable. Feb 2018 (MAE 3.3× credit → +$250) and Apr 2025 (MAE −$4,088 → +$782) are the clearest cases. One episode where the recovery arrives a week later than the 21-DTE exit turns a win into a full-width loss.
2. **Thin credit against costs.** At 2σ / 1.5σ the mean gross credit is 3.55 pts; the assumed 0.10/leg spread takes 22.5 % of it and commissions another 2.8 %. Real far-OTM SPX spreads are often wider than 0.10, so stage 2 is more likely to shrink the premium leg than restore it. This is the single number most worth watching when real prices come in.
3. **Variant A is negligible relative to the book.** ≈ $630 credit per cycle on $400,000; cash interest is ~80 % of the equity gain and the book drawdown never exceeds 0.75 %. A is a valid baseline for testing the rules; only B says anything about the strategy as a trade.
4. **Same-expiry re-entry** (31 cases) follows from the literal entry rule ("no position is open") and doubles exposure to one expiry in fast vol-crush months. Decide whether it is intended.
5. **The term-structure filter earned its keep in 2020** (no cycle in March) and cost little elsewhere: filter on vs off, variant A premium P&L $48,264 vs $48,243.
6. **The loss profile is call-side as much as put-side.** Of the five worst cycles, two are call breaches (Jan 2018 melt-up, Nov 2023 rally). The 1.5σ call is closer than the 2σ put and rallies after a vol spike are fast because sigma_H was set on the elevated vol.
7. **2022 is a marginal pass** on A1 (exactly 3 losers): the hiking-year drawdown was mostly gradual and the strikes widened with vol, as the strike analysis predicted.

## 6. Assumptions that affect the numbers

Also listed in each `summary.md`.

- VIX3M starts 2006-07-17: flat term structure and no filter before then (Jan 2005 – Jul 2006). VIX9D is downloaded but no pre-registered rule uses it.
- Skew is one smile in strike space (downside strikes +0.8 vol pts per 1 %, upside −0.3), applied by strike not by option type, so put-call parity holds. Tenor vol is extrapolated on the VIX/VIX3M variance line below 30 days for the 21–30 DTE marks; vol floor 1 %, never hit.
- Profit-take is tested on the executable exit cost (mid + 0.40); entry is skipped when net credit ≤ 0. Exit precedence when both conditions hold on one close: profit_target.
- Short strikes are rounded to the 5-point grid first; width rounded to the grid; long = short ∓ width.
- Sizing B uses cash at the entry close (no position open). Cash accrues at the previous close's DTB3 rate for calendar days elapsed on the whole balance; defined-risk margin is not deducted.
- Breach "finish" = close beyond the short strike on the exit day; "touch" = intraday low/high beyond the strike after entry. A3 was judged on the finish basis (the basis of the ranges in the strike analysis).
- Python 3.14 (3.12 not installed); no behavioural difference expected.
- Cosmetic: the `Year` column in the by-year tables of this run's `summary.md` files is printed with a thousands separator ("2,005"). Fixed in `report.py` after the run; the run files are left as written (append-only).

## 7. Recommendations

Principle: amend the *tests* where they are mis-specified; do not change the *strategy rules* on the back of these results. Each change goes in `docs/amendments.md` with a new config file (`config-002.yaml`, acceptance section only) and a new results folder.

1. **A3 — replace the test.** The ranges are wrong for the adopted sigma rule and no range is testable at ~1 event per side. Make A3 a strike-placement check: median short-strike distances of executed cycles must match an out-of-engine replication of the strike rule on raw index data within ±1 percentage point, plus a loose ceiling (touch breach ≤ 5 % each side). That tests what A3 is for — that strikes land where the analysis says.
2. **A1 — widen the criterion, keep the windows.** "At least one cycle active in the window with realised P&L < 0 **or** MAE ≤ −1× net credit." A1 is a bug detector; what it should confirm is that the marks respond to the stress, not that the exit date lands inside the drawdown. Do not simply move the window to Jan–Feb 2018 — that would pass by accident of which cycle caught the melt-up.
3. **A4 — name the metric.** Apply the 10 % threshold to net gain on the book (final equity − $400,000) and to total premium P&L; drop Sharpe and drawdown (too noisy for a 10 % band). State that the lag must not *hurt* by more than 10 %; improvement under lag is not a failure. Under that wording A passes and B fails marginally on premium P&L (10.9 %) while passing on net gain (3.3 %) — the amendment should say which of the two governs.
4. **Record the 2022 margin** (exactly the minimum) in the amendment so it is not read as a comfortable pass.
5. **Stage-2 brief** should carry §5 as open questions, in particular whether a stop-loss (or a mark-based exit) belongs in the rules, and should set the spread assumption from observed SPX quotes rather than a flat 0.10.
6. **Do not re-run stage 1 with changed strategy parameters** until stage 2 real prices are in; the cost and credit numbers in §5.2 will move and any tuning now would be to the synthetic surface.

## 8. Reproduction

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/run_stage1.py --run-id <new-id>          # both variants + A1–A5
.venv/bin/python scripts/verify_summary.py results/<run>/variant_a  # A5 alone
```
