# BRIEF 002 — Stage 2: real option prices, test amendments, live quote sampling

Date: 2026-09-09
Status: OPEN
Predecessor: brief 001 · findings 001 · run `results/2026-09-09_stage1/`

## Purpose

Stage 1 produced a working engine but an unpassed acceptance gate, and its performance figures rest on two untested assumptions: a flat 0.10-point bid-ask per leg, and a Black-Scholes surface with fixed skew that has never been compared to a real quote. Both are now testable against free data.

This brief does four things, in order:

1. Amend the three mis-specified acceptance tests (A1, A3, A4).
2. Validate the synthetic pricing surface and measure real bid-ask, against free SPX end-of-day option chains covering 2010-2023.
3. Stand up a forward-looking IBKR quote sampler to cover 2024-2026 and to cross-check the free source.
4. Re-run stage 1 with observed costs and the amended tests.

No strategy rule changes anywhere in this brief. Entry, strike selection, exit, filter and sizing stay exactly as pre-registered. Two rule questions are recorded in the Open Questions section as items for Paolo; do not implement them.

## Why this matters — the number that decides the project

The four legs, round trip, mean each extra nickel per leg of spread costs $40 per contract per cycle. Against the stage 1 result:

| Assumed spread | Variant A premium P&L | Variant B premium P&L |
|---|---|---|
| 0.10/leg (as run) | $48,264 | $71,742 |
| 0.15/leg | $25,704 | $1,822 |
| 0.20/leg | $3,144 | −$68,098 |

Real far-OTM SPX spreads are routinely wider than 0.10. If the observed median lands at or above 0.15, the strategy does not survive its own transaction costs and nothing else in this brief matters. Establish that number first.

## Part 1 — Amend the acceptance tests

`config.yaml` is frozen. Create `config-002.yaml` containing only the `acceptance:` section, amended as below, and append the corresponding entry to `docs/amendments.md`. All other parameters continue to be read from `config.yaml`.

Principle: amend the tests where they were mis-specified; do not change the strategy on the back of stage 1 results.

### A1 — widen the criterion, keep the windows

Current wording requires a losing cycle in each stress window. Feb 2018 failed because the 21-DTE exit landed after the recovery (MAE −$1,939, 3.3x the credit, closed +$250). A1 is a bug detector: what it must confirm is that the marks respond to stress, not that the exit date happens to fall inside the drawdown.

New criterion, per window: at least one cycle active in the window with realised P&L < 0 OR maximum adverse excursion <= −1x net credit.

Windows unchanged: Oct 2008, Feb 2018, Mar 2020, and >= 3 qualifying cycles in 2022. Do not move the Feb 2018 window to Jan-Feb 2018 — that would pass by accident of which cycle caught the melt-up.

Record in the amendment that 2022 passed the original test at exactly the minimum (3 losers of 16 cycles), so it is not read as a comfortable pass.

### A3 — replace the test

The 2-5% / 4-9% breach ranges were calibrated on rv21-only strikes held to expiry. The strategy uses max(rv21, rv63, VIX) and exits at 21 DTE, which moves median short-strike distance from 7.5%/5.6% to 11.8%/8.9%. Expected breach rate under the adopted rule is under 1% — roughly one event per side in 282 cycles. A numeric range is not testable at that rate.

Replace with a strike-placement check, which is what A3 was for:

- Median short-strike distance of executed cycles, put and call side, must match an out-of-engine replication of the strike rule on raw index data to within ±1.0 percentage point.
- Plus a loose ceiling: touch-basis breach <= 5% each side.

Delete `put_breach_range` and `call_breach_range` from the acceptance config.

### A4 — name the metric and the direction

The 10% threshold was applied to every metric including Sharpe and max drawdown, which are ratios and extremes of small numbers (the standard error of a 21.7-year Sharpe is about 0.26, so the observed 0.16 move is inside noise). Results also improved under the lag, which is evidence against look-ahead, not for it.

New wording: a 1-day lag on all inputs must not degrade net gain on the book (final equity − $400,000) by more than 10%. Total premium P&L is reported as a diagnostic under the same threshold. Sharpe and max drawdown are dropped from A4. Improvement under lag is not a failure.

Governing metric: net gain on the book. Under this wording both variants pass on the stage 1 numbers; state that explicitly in the amendment so the change is not mistaken for a threshold loosened until it passed.

### Part 1 closure criteria

- [ ] `config-002.yaml` exists, `acceptance:` section only, `config.yaml` untouched.
- [ ] `docs/amendments.md` entry: date, each change, the reason, the new config filename, and the 2022 margin note.
- [ ] A1/A3/A4 implemented to the new wording in `scripts/run_stage1.py`.
- [ ] Stop and report before running anything. Do not proceed to Part 2 until Paolo confirms.

## Part 2 — Real quotes: validate the surface, measure the spread

### Source

optionsDX, SPX Option Chain, free end-of-day tier: 2010-2023, monthly CSVs, containing bid/ask/last, greeks, IV and underlying price. https://www.optionsdx.com/product/spx-option-chain/

Free tier, zero-value checkout, account required; delivery via ShareFile. Do not buy anything. If the free tier turns out not to cover SPX EOD for the full 2010-2023 range, stop and report rather than substituting a paid source.

Coverage note: 2010-2023 is roughly 180 of the 282 cycles and contains all three stress episodes (Jan/Feb 2018, Mar 2020, the 2022 hiking year). The pre-2010 cycles are the ones findings 001 section 4 already discounts as a test of the rules rather than of the economics. 2024-2026 is covered by Part 3.

Timestamp alignment: the EOD snapshot is the close, and the engine enters and exits at the close. No interpolation. A closing snapshot is if anything wider than a realistic intraday fill, which biases conservative — the right direction.

Provenance is not published by the vendor. Sanity-check a sample: pick 10 random dates and verify observed mids are consistent with the index level, and verify expiry-day values against SPX settlement.

### Store

Raw CSVs under `data/quotes/` (git-ignored, like `data/cache/`). Commit the derived summary tables, never the raw vendor data.

### Join

Take `results/2026-09-09_stage1/variant_a/trades.csv`. For every cycle with entry date >= 2010-01-01 and exit date <= 2023-12-31, join the observed chain on (date, expiry, strike, right) for all four legs, on both the entry date and the exit date.

Gate: the join must cover >= 90% of expected legs. Itemise every missing leg with its date, strike and probable cause. Below 90%, stop and report.

### Report — (a) is the pricing model right?

For each leg, compare the engine's synthetic Black-Scholes mid to the observed mid. Report mean, median and IQR of (synthetic − observed), in points and as a percentage of the observed mid, bucketed by:

- moneyness (distance from spot, in 2% bands)
- VIX regime (< 15, 15-25, > 25)
- DTE (entry ~45 vs exit ~21)
- side (put wing vs call wing)

Then the same for the net credit per cycle: synthetic vs observed. This is the number that propagates to P&L.

This tests the fixed skew (+0.8 / −0.3 vol points per 1% OTM) and the VIX/VIX3M variance-time tenor scaling, neither of which has ever met a real quote. If synthetic mids are systematically rich, the stage 1 P&L is overstated before spreads enter the picture at all.

### Report — (b) what is the real spread?

Observed half-spread per leg, in index points. Report median, p75 and p90, bucketed the same four ways as above. Then:

- Implied round-trip cost per contract per cycle, in points and dollars, against the 0.80 points assumed in stage 1.
- The same figure restricted to the stress windows (Feb 2018, Mar 2020, 2022) — spreads widen exactly when the strategy is losing, and that interaction is the one the flat assumption hides.

### Part 2 closure criteria

- [ ] `docs/findings/002-quote-validation.md` with both report sections, all tables in points and dollars.
- [ ] Join coverage stated as a percentage with missing legs itemised.
- [ ] A single headline number: median observed half-spread per leg on the traded strikes, and where it falls against the 0.10 / 0.15 / 0.20 table above.
- [ ] Stop and report. Do not proceed to Part 4 until Paolo confirms.

## Part 3 — IBKR forward quote sampler

Runs alongside Part 2 review; it is data collection, not analysis, so it does not violate the no-parallel-work rule.

### Why

IBKR has no historical data for expired options — no bid/ask, no EOD, at any subscription level. This is a stated platform limitation, not an entitlement issue, so IB can never validate 2005-2023. What it can do is cover the 2024-2026 gap going forward and cross-check the free vendor.

### Spec

- `ib_async` against TWS or IB Gateway. Confirm with Paolo which machine runs it and that the API port is reachable from where the job runs.
- If OPRA is not enabled on the account, use `reqMarketDataType(3)`. Delayed quotes are perfectly adequate for measuring spread width. Do not subscribe to anything.
- Daily snapshot at 15:55 ET. Identify the monthly expiry 30-45 DTE, compute sigma_H and the four strikes exactly per `config.yaml`, and record bid, ask, mid, size and volume for all four legs, plus spot, VIX and VIX3M at the same instant.
- Append to `data/live_quotes/` (git-ignored). Commit a weekly summary table.
- Pacing: trivial at this volume, but respect the 60-requests-per-10-minutes limit and note that BID_ASK requests count double.

### Part 3 closure criteria

- [ ] Sampler running daily, cron entry committed.
- [ ] First weekly summary committed.
- [ ] One overlapping-period comparison of IB observed spreads against the optionsDX methodology, to show the two sources agree on the same structure.

## Part 4 — Re-run stage 1 on observed costs

Only after Parts 1 and 2 are confirmed.

Create `config-003.yaml`. Changes from `config.yaml`, and nothing else:

- `pricing.bid_ask_per_leg_points` replaced by a spread model: a lookup table keyed on moneyness band x VIX regime, populated from the Part 2 medians. Keep the flat-0.10 path available behind a flag so the two runs are comparable.
- `pricing.commission_per_leg_contract_usd`: 1.31 for legs with premium >= $1.00, 1.22 below. Verified fee stack, IBKR Pro smart-routed at $0.65 commission: Cboe transaction $0.45 (>= $1.00) or $0.36 (< $1.00), index surcharge $0.20, ORF $0.0125, trade processing $0.0025. Note in `summary.md` that direct routing would be $1.00/contract commission, taking the all-in to about $1.66 per side.
- Optionally, if Part 2(a) shows a systematic mid error, a documented correction to the skew or tenor parameters. This is a pricing model correction, not a strategy change — it still requires its own amendments entry.

Runs required:

- Primary: 2010-2023, observed spread model, both sizing variants.
- Secondary: full 2005-2026, spread model extrapolated outside the observed window, clearly labelled as extrapolated.
- Comparison: 2010-2023 on the old flat 0.10, so the cost delta is isolated.

Report the same tables as findings 001 section 4, plus a direct before/after on premium P&L, Sharpe, max drawdown and win rate for both variants.

### Part 4 closure criteria

- [ ] `results/<new-run>/` with all three runs, append-only, new run id.
- [ ] A1-A5 under the amended wording, all five reported before any performance figure.
- [ ] `docs/findings/003-stage2-results.md`.
- [ ] A5 verifier passes on every variant.

## Open questions — recorded, not to be implemented

For Paolo's decision. Do not build either of these; note anything you learn that bears on them.

1. **No stop-loss.** 75 of 282 cycles reached an adverse mark of at least the full credit; 25 of those still closed profitable. The P&L depends on recovery arriving before a fixed time-based exit. One episode where the recovery is a week late turns a win into a full-width loss. Does a mark-based stop belong in the rules?
2. **Same-expiry re-entry.** 31 cases follow from the literal entry rule ("no position is open") and double exposure to a single expiry in fast vol-crush months. Intended or not?

## Out of scope

Intraday fills, early assignment, mid-cycle adjustment or rolling, tax, any change to entry / strike / exit / filter / sizing rules, and any purchase of data.

## Pushback

If any part of this brief is underscoped, internally inconsistent, or asks for something the data cannot support, say so before implementing. Stop-reports are honoured without override. In particular: if the free tier does not deliver what Part 2 assumes, stop rather than working around it.

## Report format

Terse. Tables in dollars on the $400k book, and in index points where the quantity is a price. State every assumption that affects the numbers. Atomic commits bundling all artifacts. Push to origin, then report acceptance-test results before any performance figures.
