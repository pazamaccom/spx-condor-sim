# Findings 002 — Quote validation against optionsDX SPX end-of-day chains (brief 002, Part 2)

Date: 2026-09-10 · Brief: [002](../briefs/002-stage2-real-pricing.md) Part 2 · Source cycles: [`results/2026-09-09_stage1/variant_a/trades.csv`](../../results/2026-09-09_stage1/variant_a/trades.csv) · Config: `config.yaml` (frozen, unchanged) · Scripts: `scripts/quote_join.py`, `scripts/quote_report.py`, `scripts/quote_surface.py` · Derived tables: [`data/quotes/derived/`](../../data/quotes/derived/) (raw vendor data is git-ignored)

**Status: Part 2 complete.** Join coverage 98.5 % under the nearest-listed-strike rule confirmed by Paolo on 2026-09-10 (strict rule: 86.2 %, below the 90 % gate; stop-report and confirmation precede this document). No strategy rule, config parameter or result file was changed.

**Headline.** The observed median half-spread on the traded strikes is **0.125 points per leg**, but the cost that matters is the sum over eight legs, and that sum has a median of **1.62 points per contract per cycle**, equivalent to a flat **0.20 per leg** — 2× the stage-1 assumption. Spreads are, however, the smaller problem: the engine's synthetic net entry credit is **2.3× the observed one** (median 2.62 vs 1.15 points), because the engine treats VIX as the ATM implied vol. Repriced on observed mids and observed spreads, the 179 fully joined 2010–2023 cycles lose about **$59,000** on 2 contracts where stage 1 recorded a **$20,000** gain.

---

## 1. Source and provenance

| Item | Value |
|---|---|
| Vendor | optionsDX, SPX option chain, free end-of-day tier; 168 monthly files, 2010-01 to 2023-12, one consistent 33-column header; 5.2 GB extracted |
| Snapshot | 16:00 ET close (`QUOTE_TIME_HOURS` = 16 throughout); bid, ask, last, size, volume, vendor IV and greeks, underlying |
| Expiry labelling | 2010 – early 2016: the AM-settled monthly is labelled by its **Thursday** last trading day. 2016 onwards: by the **third Friday** itself. From 2022 a separate Thursday SPXW weekly (a different contract, ~2,500 rows) sits beside it. Census in `expiry_labels.csv` |
| Friday rows, 2017+ | Quotes exist on the Friday for Friday-labelled monthlies but are post-settlement (ITM mids 15–35 points off intrinsic). Unusable; no entry or exit date falls on an expiry day, so none was used |
| Underlying | Vendor `UNDERLYING_LAST` vs `^GSPC` close on the 10 seeded random dates: within 0.7 points; over all joined legs max 4.1 points (0.1 %) |
| Put-call parity | Near-ATM 20–60 DTE, 10 random dates: forward − spot median −1 to −9 points 2010–2021 (dividends > rates), +3 to +15 in 2022–2023. Consistent |
| Last trading day | ITM mid − intrinsic on the last quoted day of each monthly, 2010–2015: median 0.0–0.3 points. Consistent with next-morning settlement |
| Gaps | Three trading days with no rows at all: 2021-08-31, 2022-06-24, 2023-01-03. Jan–Feb 2010: 4.9 % of rows have blank bid/ask |

## 2. Join

Rule: (quote date, expiry, strike, right) for all four legs on the entry date and on the exit date. Expiry label = the engine's expiry date, else the previous calendar day. Where the engine strike is not listed, the nearest listed strike within 10 points is taken and the synthetic leg is repriced at that strike (`--substitute-strikes 10`); the original and substituted strikes are both recorded.

| | Legs | Cycles |
|---|---|---|
| Expected (186 cycles × 8) | 1,488 | 186 |
| Joined, strict rule | 1,283 (86.2 %) | 104 complete |
| Joined, substitution rule (used) | **1,466 (98.5 %)** | **179 complete** (181 with all entry legs, 184 with all exit legs) |
| Substituted legs | 183 (150 by 5 points, 33 by 10) | |
| Zero-bid legs among joined | 138 (136 calls; 100 on exit dates); mid taken as ask/2 | |

**Why 185 engine strikes were not listed.** The pre-registered rule rounds to a 5-point grid. SPX lists 5-point strikes only near the money; 8–20 % OTM the listed grid is 10 or 25 points. Long calls were worst hit (27 % unlisted), then short calls (19 %). Recent years are worst (2020–2023: 22–29 % of legs). This is a mismatch between the strike rule and what is tradable, not a data defect; see §6.

**Remaining 22 missing legs** (`missing_legs.csv`):

| Cycle | Date | Legs | Cause |
|---|---|---|---|
| 2010-01-05 → 2010-02-19 | exit 2010-01-29 | 4 | vendor rows present, bid/ask blank |
| 2010-02-02 → 2010-03-19 | entry 2010-02-02 | 4 | vendor rows present, bid/ask blank |
| 2016-04-05 → 2016-05-20 | entry | long call 2265 | not listed; nearest 2250 / 2300 (15 points) |
| 2020-09-01 → 2020-10-16 | entry | long call 4055 | not listed; nearest 4000 / 4100 (45 points) |
| 2021-08-31 → 2021-10-15 | entry 2021-08-31 | 4 | no vendor rows that day |
| 2022-05-31 → 2022-07-15 | exit 2022-06-24 | 4 | no vendor rows that day |
| 2023-01-03 → 2023-02-17 | entry 2023-01-03 | 4 | no vendor rows that day |

The engine's synthetic mids were recomputed leg by leg from the same inputs as the run and reproduce every `credit_mid` and `exit_debit_net` in `trades.csv` to 1e-9, so the comparison below is against the engine's own numbers.

## 3. Report (a) — is the pricing model right?

Full tables: [`report_tables.md`](../../data/quotes/derived/report_tables.md) §(a), [`surface_tables.md`](../../data/quotes/derived/surface_tables.md). Points are index points; % is of the observed mid.

### 3.1 Per leg, synthetic − observed

| Bucket | Legs | Observed mid, median | Synth − obs, mean | Synth − obs, median | IQR | Median % of obs |
|---|---|---|---|---|---|---|
| Entry (~45 DTE) | 730 | 2.15 | +2.55 | +2.14 | 2.17 | +88 % |
| Exit (~21 DTE) | 736 | 0.51 | +0.01 | −0.08 | 0.50 | −30 % |
| Put side | 734 | 3.30 | +1.53 | +1.03 | 3.08 | +24 % |
| Call side | 732 | 0.35 | +1.02 | +0.46 | 1.52 | +117 % |
| Short put | 367 | 3.60 | +1.73 | +1.38 | 3.28 | +29 % |
| Short call | 367 | 0.43 | +1.41 | +0.92 | 1.99 | +168 % |
| VIX < 15 | 516 | 0.72 | +0.82 | +0.20 | 2.01 | +34 % |
| VIX 15–25 | 759 | 0.79 | +1.31 | +0.65 | 2.36 | +54 % |
| VIX > 25 | 191 | 2.40 | +2.32 | +1.57 | 3.80 | +53 % |
| Moneyness 6–8 % | 208 | 0.40 | +0.87 | +0.28 | 1.71 | +46 % |
| Moneyness 8–10 % | 273 | 0.60 | +1.30 | +0.98 | 2.12 | +73 % |
| Moneyness 10–12 % | 277 | 1.10 | +1.21 | +0.60 | 2.50 | +53 % |
| Moneyness 12–14 % | 203 | 1.80 | +1.48 | +0.85 | 2.56 | +53 % |
| Moneyness 14–20 % | 301 | 1.38 | +1.47 | +0.49 | 2.95 | +32 % |
| Moneyness 20 %+ | 109 | 2.13 | +1.48 | −0.02 | 2.32 | −2 % |
| Exact strike | 1,283 | 0.98 | +1.20 | +0.49 | 2.33 | +44 % |
| Substituted strike | 183 | 0.47 | +1.80 | +0.88 | 2.57 | +141 % |

The synthetic surface is rich on every bucket at entry. The exit-date median near zero is largely the quote floor: 100 of 736 exit legs have a zero bid and a 0.05 ask, so the observed mid cannot fall below 0.025 while the synthetic value does.

### 3.2 Per cycle — the number that propagates to P&L

| Quantity | Cycles | Observed, median | Synthetic, median | Synth − obs, mean | Synth − obs, median | IQR | Median % of obs | Mean $ per cycle (2 contracts) |
|---|---|---|---|---|---|---|---|---|
| Net entry credit (pts) | 181 | 1.15 | 2.62 | +1.87 | +1.55 | 1.58 | **+140 %** | **+$374** |
| Net exit debit (pts) | 184 | 0.52 | 0.81 | +0.49 | +0.33 | 0.62 | +53 % | +$99 |

The overstatement is uniform across VIX regimes (+140 %, +139 %, +140 % for VIX < 15, 15–25, > 25). Sold at the bid and bought at the ask, the executable entry credit has a median of **0.24 points**, and **45 % of the 181 cycles have an executable credit ≤ 0** — the pre-registered structure could not have been opened at a positive net credit in nearly half the months.

### 3.3 Where the error comes from (vendor implied vols, `surface_tables.md`)

| Component | Engine | Vendor | Gap |
|---|---|---|---|
| ATM vol, entry (~45 DTE), median vol points | 17.6 (VIX 16.7 interpolated to 45 days on the VIX/VIX3M variance line) | 14.3 | **+3.4** (vendor/engine ratio 0.81, IQR 0.08) |
| ATM vol, exit (~21 DTE) | 15.4 | 13.3 | +2.0 (ratio 0.87) |
| Decomposition at entry | VIX − vendor ATM IV = +2.3; tenor interpolation adds +1.0 (VIX3M − VIX median +2.2) | | |
| Put skew, vol pts per 1 % OTM, entry | +0.80 | +0.81 (IQR 0.18) | ≈ 0 |
| Put skew, exit | +0.80 | +1.10 (IQR 0.24) | engine too flat at short tenor |
| Call skew, entry | −0.30 | −0.21 (IQR 0.18) | engine slightly too steep (makes calls cheaper, not richer) |
| Call skew, exit | −0.30 | −0.05 (IQR 0.29) | |
| Leg vol, engine − vendor, entry | | | puts +3.2, calls +2.6 vol pts |

The fixed skew slopes are close to the market at 45 DTE. The error is the **level**: VIX is a variance-swap-style index over the whole smile and sits 2–3 vol points above the ATM implied vol; treating it as ATM vol, then extrapolating up the VIX/VIX3M term structure, prices every leg 2.6–3.4 vol points too high. At 10–15 % OTM that multiplies far-OTM prices by 2–3×, which is the +140 % on the credit.

### 3.4 Premium P&L repriced (179 cycles with all eight legs, variant A, 2 contracts)

Repricing only: entry dates, exit dates and strikes are the stage-1 ones. Bid-ask charged as the four half-spreads on each side; commissions $1.25/leg/contract as in stage 1.

| Pricing | Premium P&L |
|---|---|
| Stage 1 as run (synthetic mids, flat 0.10/leg) — these 179 cycles | $20,183 |
| Synthetic mids, observed spreads | −$10,100 |
| Observed mids, flat 0.10/leg | −$28,693 |
| **Observed mids, observed spreads** | **−$59,286** |

Both errors go the same way. The mid error costs more than the spread error. A true re-run (Part 4) will differ because profit-target exits were triggered on synthetic marks; with observed credits half as large, the 50 % target and the 21-DTE exit would fire on different days.

## 4. Report (b) — what is the real spread?

Half-spread per leg = (ask − bid) / 2, index points. Full tables: `report_tables.md` §(b).

### 4.1 Per leg

| Bucket | Legs | Median | p75 | p90 | Mean |
|---|---|---|---|---|---|
| **All legs** | 1,466 | **0.125** | 0.275 | 0.450 | 0.205 |
| Entry (~45 DTE) | 730 | 0.190 | 0.350 | 0.500 | 0.246 |
| Exit (~21 DTE) | 736 | 0.098 | 0.200 | 0.355 | 0.164 |
| Put side | 734 | 0.195 | 0.374 | 0.550 | 0.260 |
| Call side | 732 | 0.080 | 0.200 | 0.329 | 0.150 |
| Short legs | 734 | 0.145 | 0.300 | 0.467 | 0.218 |
| Long legs | 732 | 0.115 | 0.255 | 0.425 | 0.192 |
| VIX < 15 | 516 | 0.150 | 0.295 | 0.405 | 0.202 |
| VIX 15–25 | 759 | 0.100 | 0.255 | 0.450 | 0.191 |
| VIX > 25 | 191 | 0.145 | 0.287 | 0.650 | 0.269 |
| Moneyness 6–10 % | 481 | 0.125 | 0.275 | 0.400 | 0.188 |
| Moneyness 10–14 % | 480 | 0.145 | 0.300 | 0.461 | 0.208 |
| Moneyness 14–20 % | 301 | 0.100 | 0.260 | 0.440 | 0.198 |
| Moneyness 20 %+ | 109 | 0.100 | 0.220 | 0.651 | 0.232 |
| Exact strike | 1,283 | 0.150 | 0.300 | 0.464 | 0.217 |
| Substituted strike | 183 | 0.075 | 0.125 | 0.291 | 0.119 |

Time dominates every other bucket:

| Era × DTE | VIX < 15 | VIX 15–25 | VIX > 25 |
|---|---|---|---|
| 2010–2016, entry | 0.350 | 0.370 | 0.487 |
| 2010–2016, exit | 0.225 | 0.100 | 0.253 |
| 2017–2023, entry | 0.100 | 0.100 | 0.125 |
| 2017–2023, exit | 0.075 | 0.075 | 0.100 |

By year, median per leg: 2010 0.21 · 2011 0.30 · 2012 0.31 · 2013 0.29 · 2014 0.36 · 2015 0.28 · 2016 0.23 · 2017 0.15 · 2018 0.10 · 2019 0.08 · 2020 0.10 · 2021 0.10 · 2022 0.10 · 2023 0.08. Puts are consistently 2× calls at entry (2017–2023: 0.15 vs 0.075).

### 4.2 Implied round-trip cost per contract per cycle (179 fully joined cycles)

Sum of the eight half-spreads. Stage 1 assumed 0.80 points = $80 per contract = $160 per 2-contract cycle.

| | Points per contract | $ per contract | $ per cycle (2 contracts) | Equivalent flat per leg |
|---|---|---|---|---|
| Median | **1.62** | **$162** | **$324** | 0.20 |
| p75 | 2.29 | $229 | $457 | 0.29 |
| p90 | 2.86 | $286 | $572 | 0.36 |
| Mean | 1.65 | $165 | $331 | 0.21 |
| 2010–2016, median by year | 1.82–2.84 | $182–284 | $364–569 | 0.23–0.36 |
| 2017–2023, median by year | 0.61–1.16 | $61–116 | $122–232 | 0.08–0.15 |

Against a median observed net entry credit of 1.15 points, the median round trip of 1.62 points exceeds the credit itself; against the synthetic credit of 2.62 it would have been 62 %.

### 4.3 Stress windows

| Window | Legs quoted in window | Half-spread median | p75 | p90 | Fully joined cycles touching window | Round trip median (pts) | $ per cycle (2 contracts) |
|---|---|---|---|---|---|---|---|
| Feb 2018 | 4 | 0.120 | 0.145 | 0.145 | 1 | 1.25 | $250 |
| Mar 2020 | 0 | — | — | — | 0 | — | — |
| 2022 | 124 | 0.100 | 0.150 | 0.200 | 15 | 0.80 | $160 |
| All other dates | 1,338 | 0.145 | 0.300 | 0.455 | | | |

The stress interaction the brief was looking for does not show in these windows on this data: the one Feb 2018 cycle's round trip (1.25) is above the 2017–2023 norm (0.6–1.2) but not extreme, and 2022 is at the norm. Mar 2020 has no observation because the filter blocked every entry (findings 001 §3). The VIX > 25 bucket shows the widening instead: p90 0.65 vs 0.41–0.45 in calmer regimes, and the 2020 round-trip median (1.03) is above 2019 and 2021 (0.64, 0.89). The sample is 191 legs.

## 5. Headline number

Median observed half-spread per leg on the traded strikes: **0.125 points**. Equivalent flat per leg from the median round trip: **0.20 points**. Placed in the brief's table (linear, mid error excluded):

| Assumed half-spread per leg | Variant A premium P&L | Variant B |
|---|---|---|
| 0.10 (stage 1) | $48,264 | $71,742 |
| 0.125 (observed median per leg) | $36,984 | $36,782 |
| 0.15 | $25,704 | $1,822 |
| 0.20 (observed round trip ÷ 8) | $3,144 | −$68,098 |

The per-leg median understates the cost because the legs that cost most (entry-side, put-side) are averaged with the cheap exit-side calls; the round trip is the number a fill would pay. Even the per-leg median is above the level at which variant B's edge is gone. And the table holds the credit at its synthetic value; on observed credits (§3.4) both variants are negative in 2010–2023.

## 6. Implications for Part 4 — proposed, not implemented

Each needs its own `docs/amendments.md` entry and `config-003.yaml` before any run.

1. **Spread model.** The brief's moneyness × VIX-regime lookup is in `report_tables.md` (§(b), pivot with leg counts) but is dominated by time, not by either key; many cells have under 30 legs. Recommend keying on era (2010–2016 / 2017–2023) × side (put/call) × date type (entry/exit), which has 8 cells of 130–370 legs, with the VIX > 25 uplift as a multiplier. Keep the flat-0.10 path behind the flag as specified. For extrapolation outside 2010–2023, 2017–2023 values are the relevant ones for 2024–2026 and should be cross-checked in Part 3.
2. **ATM level correction (pricing model, not strategy).** Replace "VIX = ATM vol" with a calibrated discount: ATM vol = 0.81 × engine ATM at 45 DTE and 0.87 at 21 DTE (or VIX − 2.3 vol points before tenor interpolation). Leave the skew slopes; optionally steepen the put slope at short tenor (+1.1 at 21 DTE). Recalibrating on the same data that judges the result is circular, so state it as a correction fitted on 2010–2023 and test it out of sample on the Part 3 IBKR quotes.
3. **Listed-strike grid (rule question for Paolo).** `strike_grid: 5` is not executable 8–20 % OTM. Snapping to the listed grid (10 or 25 points there) moves strikes by ≤ 12 points. This is a change to the pre-registered strike rule and needs a decision, not just an amendment. Not required for Part 4 if the spread and mid tables are applied at the engine strike, but the 2024–2026 sampler (Part 3) will need listed strikes anyway.
4. **Entry rule at real prices.** 45 % of cycles have an executable net credit ≤ 0 on observed quotes. The existing "skip entry when net credit ≤ 0" guard would then remove nearly half the cycles in a Part 4 run; that is the correct behaviour of the pre-registered rule and should be reported as such, not patched.
5. **Open question 1 (no stop-loss)** is unaffected by this Part. **Open question 2 (same-expiry re-entry)** bears on spreads: the 31 re-entries pay a second round trip on the same expiry.

## 7. Assumptions that affect the numbers

- Observed mid = (bid + ask)/2 including 138 zero-bid legs (mid = ask/2); excluding them would lower observed mids further and widen the gap in §3.
- Substituted-strike legs (183) are repriced synthetically at the substituted strike; both strikes are in `legs_joined.csv`. Their median half-spread (0.075) is lower than exact-strike legs because they are concentrated in 2020–2023.
- From 2016 the Friday-labelled chain could be the AM-settled SPX or the PM-settled SPXW on the same date; the data does not distinguish them. The difference is one trading day of tenor, immaterial here.
- Vendor IV is the vendor's inversion (model, r, q unknown); used only for level and slope comparisons in §3.3, never for prices.
- Repricing in §3.4 keeps the stage-1 exit dates; it isolates price error, it is not a re-run.
- VIX regime is the close on the quote date (entry and exit dates each bucketed separately).
- Stress-window legs are those quoted on dates inside the window; cycles "touching" a window have entry or exit inside it.

## 8. Reproduction

```
.venv/bin/python scripts/quote_join.py --substitute-strikes 10   # needs the Extreme SSD mounted; caches the extract under data/cache/
.venv/bin/python scripts/quote_report.py                          # -> data/quotes/derived/report_tables.md, cycle_nets.csv
.venv/bin/python scripts/quote_surface.py                         # -> data/quotes/derived/surface_tables.md, legs_surface.csv
```
