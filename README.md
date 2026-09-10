# spx-condor-sim

Monthly defined-risk SPX iron-condor simulator. `docs/` is the source of truth;
`config.yaml` holds the pre-registered parameters and is frozen; amendments are
overlay files (`config-002.yaml`, ...) that replace whole sections of it, one per
entry in `docs/amendments.md`.

## Stage 1 — synthetic pricing (brief 001)

Options are priced with Black-Scholes from the index level, VIX / VIX3M and DTB3.
Spec: `docs/briefs/001-stage1-backtester.md`; strike rationale: `docs/strike-analysis.md`.

### Run

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/run_stage1.py --run-id YYYY-MM-DD_stage1   # add --refresh-data to re-download
#   --config config-002.yaml (default; repeatable) selects the amendment overlays applied on config.yaml
.venv/bin/python scripts/verify_summary.py results/<run>/variant_a    # A5 on its own
```

Market data is cached under `data/cache/` (git-ignored). Results are append-only:
`run_stage1.py` refuses to overwrite an existing run id.

### Layout

```
src/spx_condor/
  data.py            ^GSPC, ^VIX, ^VIX3M, ^VIX9D (yfinance, Cboe fallback), DTB3 (FRED)
  calendar_utils.py  third-Friday expiries, holiday shift
  pricing.py         Black-Scholes, VIX/VIX3M variance-time tenor scaling, fixed skew
  backtest.py        entry / strike / exit / filter / sizing / cash engine
  report.py          summary statistics, summary.md, equity chart
scripts/
  run_stage1.py      both sizing variants + acceptance tests A1-A5 (A1/A3/A4 per amendment 002) -> results/<run>/
  verify_summary.py  independent recomputation of every number in summary.md (A5)
results/<run>/
  config.yaml + overlays, config_effective.yaml, run_meta.json, acceptance.md
  variant_a/, variant_b/   trades.csv, monthly.csv, daily.csv, summary.md, equity_curve.png
  acceptance/              filter-off run (A1), strike-rule replication (A3), lag-1 runs (A4)
```
