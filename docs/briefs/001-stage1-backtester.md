# BRIEF 001 — SPX iron-condor backtester (stage 1: synthetic pricing)

Date: 2026-09-09
Status: OPEN

## Purpose

Simulate the monthly defined-risk SPX premium strategy from 2005 to present. Output a monthly P&L series and diagnostics so the rules can be judged before trading. Stage 1 prices options synthetically from the index level and VIX. Stage 2 (later, separate brief) swaps in real option prices.

## Stack

- Python 3.12, pandas, numpy, scipy, yfinance, matplotlib.
- `docs/` markdown is the source of truth.
- Parameters are pre-registered in `config.yaml` before any results are produced. Do not change `config.yaml` after the first results run; amendments go in `docs/amendments.md` (append-only) with a new config file.
- Results are written under `results/` and are append-only (new run = new dated subfolder).

## Data (daily)

- `^GSPC` OHLC, 2004-01-01 to today (yfinance).
- `^VIX` (30-day implied), `^VIX3M` (3-month), `^VIX9D` (9-day). Source: yfinance or Cboe/FRED. `VIX9D` begins 2011; before that use VIX vs VIX3M only.
- 3-month T-bill yield, FRED series `DTB3`, for the risk-free rate and cash return.
- Cboe monthly expiry calendar: third Friday of each month; handle exchange-holiday shifts.

## Pricing model

- Black-Scholes on the index. r = DTB3 (annualised, converted from discount basis). q = 1.5% dividend yield. Time to expiry = calendar days / 365.
- Volatility per strike: VIX as ATM 30-day vol, scaled to the option's expiry by linear interpolation between VIX and VIX3M in variance-time. Fixed skew: +0.8 vol points per 1% of moneyness OTM on puts; -0.3 vol points per 1% OTM on calls. Both skew slopes are config parameters. Document this as an assumption in `summary.md`.
- Bid-ask: 0.10 index points per leg on entry and exit. Commission $1.25 per leg per contract.

## Strategy rules (pre-registered — see `config.yaml`)

1. **Entry.** First trading day on which a monthly expiry lies 30-45 calendar days ahead and no position is open. Open the four-leg condor at that day's close.
2. **Strike selection.** sigma_H = max(21-day realised vol, 63-day realised vol, VIX-implied) x sqrt(days_to_expiry / 365). Short put = spot x (1 - 2.0 x sigma_H). Short call = spot x (1 + 1.5 x sigma_H). Long legs 100 index points beyond each short leg when spot >= 6,000; 1.3% of spot otherwise. Round to the nearest 5-point strike.
3. **Exit.** Close at the first daily close where (a) the mark-to-market shows >= 50% of the entry credit captured, or (b) calendar days to expiry <= 21 — whichever comes first. If a position is still open at expiry (should not happen given rule b; guard anyway), settle at intrinsic.
4. **Filter.** No new entry when VIX > VIX3M at the entry day's close (term-structure inversion). Open positions are not closed by the filter.
5. **Sizing.** Variant A: fixed 2 contracts against a $400,000 book. Variant B: contracts = floor(0.035 x equity / ((width - credit) x 100)), recomputed at each entry. Run both.
6. **Cash.** Uninvested balance earns DTB3 daily.

## Outputs

- `results/<run>/trades.csv`: one row per cycle — entry date, expiry, spot, sigma_H, four strikes, credit, contracts, exit date, exit reason, P&L, max adverse excursion.
- `results/<run>/monthly.csv`: month-end equity, P&L split into premium and cash, open-position mark.
- `results/<run>/summary.md`: CAGR, vol, Sharpe, max drawdown with dates, win rate, avg win / avg loss, worst 5 cycles, by calendar year; and separately for 2008, Feb 2018, Mar 2020, 2022, Aug 2024, Apr 2025, Mar 2026. All dollar figures on the $400k book.
- Equity-curve chart with filter-active periods shaded.

## Acceptance tests — must pass before any performance figure is reported

- **A1.** With the filter switched off, losing cycles must appear in Oct 2008, Feb 2018, Mar 2020 and at least three cycles in 2022. If not, pricing or exit logic is wrong.
- **A2.** Full-period Sharpe (premium P&L only, ex-cash) between 0.4 and 1.2. Above 1.2: STOP, report `NOT VERIFIED`, look for look-ahead in sigma_H or exit marks.
- **A3.** Put-side breach frequency across all cycles 2-5%; call-side 4-9%. Must be consistent with `docs/strike-analysis.md`.
- **A4.** Re-running with a 1-day lag on all inputs must change results by no more than 10%.
- **A5.** Every number in `summary.md` must be reproducible from `trades.csv` by a separate script (`scripts/verify_summary.py`).

## Out of scope for stage 1

Intraday fills, early assignment (not applicable to SPX), real skew surfaces, mid-cycle adjustment or rolling, tax.

## Report format

Terse. Tables in dollars on the $400k book. State every assumption that affects the numbers. Push to origin, then report acceptance-test results before any performance figures.
