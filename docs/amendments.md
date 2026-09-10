# Amendments to the pre-registered configuration (append-only)

Each amendment: date, what changes, why, and the name of the new config file
(`config.yaml` itself is frozen as of 2026-09-09).

Acceptance-test outcomes for the first results run are in
`results/2026-09-09_stage1/acceptance.md`; any rule or threshold change they
motivate must be recorded here before a new run.

---

## 002 — 2026-09-10 — acceptance tests A1, A3, A4 re-specified (brief 002, Part 1)

**New config file:** `config-002.yaml`, containing only the `acceptance:` section. It is applied as an
overlay: `scripts/run_stage1.py --config config-002.yaml` (now the default) replaces the `acceptance:`
section of `config.yaml` with it and reads every other section from `config.yaml`, which is unchanged.
Each results folder now records the config chain (`config.yaml`, `config-002.yaml`,
`config_effective.yaml`, and `config_chain` in `run_meta.json`).

**Scope:** tests only. No change to entry, strike selection, exit, filter, sizing, pricing or cash
parameters. Principle: amend the tests where they were mis-specified; do not change the strategy on
the back of stage-1 results. The stage-1 run `results/2026-09-09_stage1/` is left as written
(append-only); its `acceptance.md` remains the record under the original wording.

### A1 — criterion widened, windows unchanged

- **Was:** with the filter off, a losing cycle (realised P&L < 0) must *exit* in each of Oct 2008,
  Feb 2018, Mar 2020, and at least three in 2022.
- **Now:** per window, at least `min_cycles` cycles **active** in the window (open on any day of it)
  with realised P&L < 0 **or** maximum adverse excursion <= −1× net credit (`a1_mae_credit_mult: 1.0`,
  dollars at position level). Required counts unchanged: 1, 1, 1, 3.
- **Why:** A1 is a bug detector — it must confirm that the marks respond to stress, not that the exit
  date happens to fall inside the drawdown. Feb 2018 failed because the cycle entered 2018-01-30 marked
  to −$1,939 (3.3× its $590 credit) on Feb 8 but the 21-DTE exit on Feb 23 landed after the recovery
  and closed +$250. The pricing and exit logic behaved as specified.
- **Windows:** unchanged (Oct 2008, Feb 2018, Mar 2020, calendar 2022) and now listed in the config as
  `a1_windows`; the values are the ones hardcoded in the stage-1 runner. The Feb 2018 window is
  deliberately **not** moved to Jan–Feb 2018 — that would pass by accident of which cycle caught the
  January melt-up.
- **MAE definition:** the engine's MAE is the worst close-to-close mark net of the round-trip exit
  spread (4 × 0.10 pts), as recorded in `trades.csv`; it therefore starts at −$80 per 2 contracts on
  entry day. The −1× credit threshold is unaffected in practice (credits are $300–$1,000).
- **2022 margin note:** under the original test 2022 passed at exactly the minimum — 3 losers of 16
  cycles exiting in the year. Under the amended wording on the stage-1 outputs, 5 of 16 active cycles
  qualify (3 by P&L, 2 more by MAE) against 3 required. Neither is a comfortable pass; the 2022
  drawdown was gradual and the strikes widened with vol.

### A3 — test replaced

- **Was:** put-side breach frequency (index close beyond the short strike on the exit day) in 2–5 %,
  call-side in 4–9 %, across all cycles (`put_breach_range`, `call_breach_range`).
- **Now:** a strike-placement check. The median short-strike distance of executed cycles (put and call
  side, % of entry spot) must be within ±1.0 percentage point
  (`a3_median_distance_tolerance_pp`) of an out-of-engine replication of the strike rule on raw
  index data; plus a loose ceiling, touch-basis breach <= 5 % on each side (`a3_touch_breach_max`).
  `put_breach_range` and `call_breach_range` are deleted.
- **Replication:** for every monthly expiry in the simulation window, the first trading day on which
  it lies 30–45 calendar days ahead (the entry rule with no filter and no position state);
  sigma_H = max(rv21, rv63, VIX/100) × sqrt(DTE/365) with rv = stdev of log returns (ddof 1) ×
  sqrt(252); short put = spot × (1 − 2.0 sigma_H), short call = spot × (1 + 1.5 sigma_H), rounded to
  the 5-point grid. Coded independently in `scripts/run_stage1.py` (`strike_rule_replication`); the
  only engine import is the expiry calendar. Written to `acceptance/a3_strike_rule_replication.csv`.
  A per-cycle recomputation on each executed cycle's own entry date and DTE is reported as a
  diagnostic (cycles reproduced exactly), as is the stage-1 replication of `docs/strike-analysis.md`.
- **Why:** the 2–5 % / 4–9 % ranges were calibrated on rv21-only strikes held to expiry. The strategy
  uses max(rv21, rv63, VIX) and exits at 21 DTE, which moves the median short-strike distance from
  7.5 % / 5.6 % to 11.8 % / 8.9 %; the expected breach rate under the adopted rule is under 1 %,
  roughly one event per side in 282 cycles, and no numeric range is testable at that rate. What A3
  was for is that strikes land where the analysis says.

### A4 — metric and direction named

- **Was:** re-running with a 1-day lag on all inputs must change results by no more than 10 %,
  applied to every metric reported (premium P&L, final equity, net gain, Sharpe, max drawdown, win
  rate, cycles), in either direction.
- **Now:** the lag must not **degrade** net gain on the book (final equity − $400,000) by more than
  10 % (`a4_governing_metric: net_gain_on_book`, `lag_sensitivity_max: 0.10`). Total premium P&L is
  reported as a diagnostic under the same threshold and does not decide the verdict
  (`a4_diagnostic_metrics`). Sharpe and max drawdown are dropped. Improvement under lag is not a
  failure.
- **Why:** Sharpe and max drawdown are ratios and extremes of small numbers — the standard error of a
  21.7-year Sharpe is about 0.26, so the observed 0.16 move is inside noise. Results also improved
  under the lag, which is evidence against look-ahead, not for it; a two-sided threshold penalises
  that.
- **Stated explicitly so the change is not mistaken for a threshold loosened until it passed:** on
  the stage-1 numbers both variants pass. Net gain on the book: A $246,670 → $249,079 (+0.98 %),
  B $275,058 → $283,985 (+3.25 %). Diagnostic total premium P&L: A +4.50 %, B +10.89 %. All four are
  improvements. Every stage-1 A4 failure was an *improvement* under lag (Sharpe +16 % / +24 %, premium
  max drawdown +22 % / +12 %, B premium P&L +10.9 %); no metric degraded. The 10 % threshold itself is
  unchanged.

### Outcome of the amended tests on the stage-1 outputs

Applied to the existing `results/2026-09-09_stage1/` files (a check of the test code, not a new
results run; nothing under `results/` was written):

| Test | Result |
|---|---|
| A1 | PASS — Oct 2008 (P&L −$102, MAE −5.1× credit), Feb 2018 (MAE −$1,939 = −3.3× credit, P&L +$250), Mar 2020 (P&L −$1,339), 2022 (5 qualifying of 16, 3 required) |
| A3 | PASS — put 11.82 % executed vs 12.45 % replication (−0.63 pp); call 8.88 % vs 9.36 % (−0.48 pp); touch 1.42 % / 0.35 %; 282 of 282 cycles reproduced exactly on their own entry date and DTE |
| A4 | PASS — net gain A +0.98 %, B +3.25 %; diagnostic premium P&L A +4.50 %, B +10.89 % |

A3 note: the residual −0.6 / −0.5 pp is sample composition, not strike error (the per-cycle check
is exact). The replication takes every expiry at ~45 DTE with no filter; the executed set excludes
the 31 filter-blocked expiries (higher-vol months, wider strikes) and includes 61 entries below 45 DTE
(re-entries and filter-delayed entries). The put side sits 0.37 pp inside the ±1.0 pp tolerance.
