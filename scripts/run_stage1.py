#!/usr/bin/env python3
"""Stage 1 run: both sizing variants, all five acceptance tests, results folder.

Usage: run_stage1.py [--run-id ID] [--refresh-data]
Writes results/<run-id>/ (append-only: refuses to overwrite an existing run).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spx_condor.backtest import RunOptions, run_backtest, realised_vol  # noqa: E402
from spx_condor.config import CONFIG_PATH, load_config  # noqa: E402
from spx_condor.data import load_market_data  # noqa: E402
from spx_condor.report import compute_summary, md_table, plot_equity, write_summary  # noqa: E402

A1_WINDOWS = {
    "Oct 2008": ("2008-10-01", "2008-10-31", 1),
    "Feb 2018": ("2018-02-01", "2018-02-28", 1),
    "Mar 2020": ("2020-03-01", "2020-03-31", 1),
    "2022": ("2022-01-01", "2022-12-31", 3),
}


def save_run(res, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    res.trades.to_csv(out / "trades.csv", index=False)
    res.monthly.to_csv(out / "monthly.csv")
    res.daily.to_csv(out / "daily.csv")


def strike_analysis_replication(mkt: pd.DataFrame, put_k: float, call_k: float) -> pd.DataFrame:
    """Replicate docs/strike-analysis.md from our data: 21-trading-day horizon,
    sigma = 21d realised daily vol x sqrt(21) (the doc's definition), plus the
    same measurement with the strategy's sigma definition (max of rv21, rv63,
    VIX-implied, scaled to 30 calendar days)."""
    d = mkt[(mkt.index >= "2005-02-28")].copy()
    lr = np.log(d["close"]).diff()
    h = 21
    finish = d["close"].shift(-h)
    min_low = d["low"][::-1].rolling(h).min()[::-1].shift(-1)   # min low over (t, t+h]
    max_high = d["high"][::-1].rolling(h).max()[::-1].shift(-1)
    rows = []
    sig_doc = lr.rolling(21).std(ddof=1) * math.sqrt(21)
    sig_strat = pd.concat([realised_vol(d["close"], 21), realised_vol(d["close"], 63), d["vix"] / 100.0], axis=1).max(axis=1) * math.sqrt(30 / 365)
    for label, sig in (("doc: rv21 only", sig_doc), ("strategy: max(rv21, rv63, VIX)", sig_strat)):
        ok = sig.notna() & finish.notna()
        for side, k in (("put", put_k), ("call", call_k)):
            if side == "put":
                lvl = d["close"] * (1 - k * sig)
                fin, tch = finish < lvl, min_low < lvl
            else:
                lvl = d["close"] * (1 + k * sig)
                fin, tch = finish > lvl, max_high > lvl
            y22 = ok & (d.index.year == 2022)
            rows.append({
                "sigma definition": label, "side": side, "k": k,
                "median distance (%)": float(((lvl / d["close"] - 1).abs()[ok]).median() * 100),
                "finish beyond, all (%)": float(fin[ok].mean() * 100), "finish beyond, 2022 (%)": float(fin[y22].mean() * 100),
                "touch, all (%)": float(tch[ok].mean() * 100), "touch, 2022 (%)": float(tch[y22].mean() * 100),
                "windows": int(ok.sum()),
            })
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=dt.datetime.now().strftime("%Y-%m-%d_%H%M") + "_stage1")
    ap.add_argument("--refresh-data", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    acc = cfg.acceptance
    book = float(cfg.sizing["book_usd"])
    run_dir = ROOT / "results" / args.run_id
    if run_dir.exists():
        sys.exit(f"results/{args.run_id} exists; results are append-only — choose a new --run-id")
    run_dir.mkdir(parents=True)
    shutil.copy(CONFIG_PATH, run_dir / "config.yaml")

    mkt = load_market_data(cfg, refresh=args.refresh_data)
    py = platform.python_version()

    # ---------------------------------------------------------------- main runs
    main_runs, summaries = {}, {}
    for v in ("A", "B"):
        res = run_backtest(mkt, cfg, RunOptions(variant=v, filter_on=True))
        out = run_dir / f"variant_{v.lower()}"
        save_run(res, out)
        s = compute_summary(res.trades, res.monthly, cfg, res.diagnostics["sim_start"], res.diagnostics["sim_end"])
        write_summary(out / "summary.md", s, cfg, v, args.run_id, res.diagnostics, py)
        plot_equity(out / "equity_curve.png", res.daily, res.trades, book, v)
        main_runs[v], summaries[v] = res, s

    # ---------------------------------------------------------------- A1
    a1 = run_backtest(mkt, cfg, RunOptions(variant="A", filter_on=False))
    save_run(a1, run_dir / "acceptance" / "a1_filter_off_variant_a")
    t = a1.trades.copy()
    t["exit_date"], t["entry_date"] = pd.to_datetime(t.exit_date), pd.to_datetime(t.entry_date)
    a1_rows, a1_pass = [], True
    for name, (a, b, need) in A1_WINDOWS.items():
        ex = t[(t.exit_date >= a) & (t.exit_date <= b)]
        act = t[(t.entry_date <= b) & (t.exit_date >= a)]
        n_ex, n_act = int((ex.pnl_usd < 0).sum()), int((act.pnl_usd < 0).sum())
        ok = n_ex >= need
        a1_pass &= ok
        a1_rows.append([name, need, len(ex), n_ex, len(act), n_act, float(ex.pnl_usd.min()) if len(ex) else 0.0,
                        float(act.mae_usd.min()) if len(act) else 0.0, "PASS" if ok else "FAIL"])

    # ---------------------------------------------------------------- A2
    a2_rows, a2_pass, a2_status = [], True, "PASS"
    for v in ("A", "B"):
        sh = summaries[v]["headline"]["Sharpe, premium-only ex-cash"]
        ok = acc["sharpe_min"] <= sh <= acc["sharpe_max"]
        a2_pass &= ok
        if sh > acc["sharpe_max"]:
            a2_status = "NOT VERIFIED"
        a2_rows.append([v, sh, acc["sharpe_min"], acc["sharpe_max"], "PASS" if ok else "FAIL"])
    if not a2_pass and a2_status == "PASS":
        a2_status = "FAIL"

    # ---------------------------------------------------------------- A3
    a3_rows, a3_pass = [], True
    for v in ("A", "B"):
        h = summaries[v]["headline"]
        pf, cf = h["Put-side breach, finish (%)"] / 100, h["Call-side breach, finish (%)"] / 100
        okp = acc["put_breach_range"][0] <= pf <= acc["put_breach_range"][1]
        okc = acc["call_breach_range"][0] <= cf <= acc["call_breach_range"][1]
        a3_pass &= okp and okc
        a3_rows.append([v, h["Cycles"], pf * 100, h["Put-side breach, touch (%)"], f"{acc['put_breach_range'][0]*100:.0f}-{acc['put_breach_range'][1]*100:.0f}", "PASS" if okp else "FAIL",
                        cf * 100, h["Call-side breach, touch (%)"], f"{acc['call_breach_range'][0]*100:.0f}-{acc['call_breach_range'][1]*100:.0f}", "PASS" if okc else "FAIL"])
    rep = strike_analysis_replication(mkt, cfg.strikes["put_sigma_mult"], cfg.strikes["call_sigma_mult"])
    rep.to_csv(run_dir / "acceptance" / "a3_strike_analysis_replication.csv", index=False)

    # ---------------------------------------------------------------- A4
    a4_rows, a4_pass = [], True
    for v in ("A", "B"):
        lag = run_backtest(mkt, cfg, RunOptions(variant=v, filter_on=True, lag_days=1))
        save_run(lag, run_dir / "acceptance" / f"a4_lag1_variant_{v.lower()}")
        sl = compute_summary(lag.trades, lag.monthly, cfg, lag.diagnostics["sim_start"], lag.diagnostics["sim_end"])
        base = summaries[v]
        for label, getter in (
            ("Total premium P&L ($)", lambda s: s["headline"]["Total premium P&L ($)"]),
            ("Final equity ($)", lambda s: s["book_tbl"]["Final equity ($)"]),
            ("Net gain on book ($)", lambda s: s["book_tbl"]["Final equity ($)"] - book),
            ("Sharpe, premium-only", lambda s: s["headline"]["Sharpe, premium-only ex-cash"]),
            ("Premium-only max drawdown ($)", lambda s: s["headline"]["Premium-only max drawdown ($)"]),
            ("Win rate (%)", lambda s: s["headline"]["Win rate (%)"]),
            ("Cycles", lambda s: float(s["headline"]["Cycles"])),
        ):
            b0, b1 = getter(base), getter(sl)
            rel = abs(b1 - b0) / abs(b0) if b0 else float("inf")
            ok = rel <= acc["lag_sensitivity_max"]
            a4_pass &= ok
            a4_rows.append([v, label, b0, b1, rel * 100, "PASS" if ok else "FAIL"])

    # ---------------------------------------------------------------- A5
    a5_rows, a5_pass = [], True
    for v in ("A", "B"):
        cp = subprocess.run([sys.executable, "scripts/verify_summary.py",
                             str((run_dir / f"variant_{v.lower()}").relative_to(ROOT)), "--book", str(book)],
                            capture_output=True, text=True, cwd=ROOT)
        ok = cp.returncode == 0
        a5_pass &= ok
        a5_rows.append([v, cp.stdout.strip().splitlines()[0] if cp.stdout else cp.stderr.strip()[-300:], "PASS" if ok else "FAIL"])

    # ---------------------------------------------------------------- write acceptance.md
    verdicts = {"A1": a1_pass, "A2": a2_pass, "A3": a3_pass, "A4": a4_pass, "A5": a5_pass}
    overall = all(verdicts.values())
    L = [
        f"# Acceptance tests — run `{args.run_id}`", "",
        f"Data: {mkt.index[0].date()} to {mkt.index[-1].date()}; simulation {main_runs['A'].diagnostics['sim_start']} to {main_runs['A'].diagnostics['sim_end']}.", "",
        md_table(["Test", "Verdict"], [[k, ("PASS" if v else ("NOT VERIFIED" if k == "A2" and a2_status == "NOT VERIFIED" else "FAIL"))] for k, v in verdicts.items()]
                 + [["Overall", "PASS" if overall else "FAIL"]]), "",
        "## A1 — losing cycles in stress windows (filter OFF, variant A)", "",
        "Losing cycle = realised P&L < 0. 'Exiting' attributes a cycle to the window of its exit date; 'active' counts cycles open on any day of the window. Verdict uses the exiting count.", "",
        md_table(["Window", "Losers required", "Cycles exiting", "Losers exiting", "Cycles active", "Losers active", "Worst cycle ($)", "Worst MAE active ($)", "Verdict"], a1_rows), "",
        "## A2 — full-period Sharpe, premium P&L only, ex-cash", "",
        md_table(["Variant", "Sharpe", "Min", "Max", "Verdict"], a2_rows), "",
        f"Status: **{a2_status}**.", "",
        "## A3 — short-strike breach frequency across all cycles", "",
        "finish = index close beyond the short strike on the exit day (the basis of the ranges in docs/strike-analysis.md); touch = intraday low/high beyond the strike on any day of the cycle after entry.", "",
        md_table(["Variant", "Cycles", "Put finish (%)", "Put touch (%)", "Put range", "Put verdict", "Call finish (%)", "Call touch (%)", "Call range", "Call verdict"], a3_rows), "",
        "Replication of docs/strike-analysis.md from this run's data (21-trading-day horizon, all days from 2005-02-28), first with the document's sigma (rv21 only) and then with the strategy's sigma definition:", "",
        md_table(list(rep.columns), rep.values.tolist()), "",
        "## A4 — 1-day lag on all inputs (OHLC, VIX, VIX3M, VIX9D, DTB3)", "",
        md_table(["Variant", "Metric", "Base", "Lag 1", "Change (%)", "Verdict"], a4_rows), "",
        f"Threshold: {acc['lag_sensitivity_max']*100:.0f}% on every metric listed.", "",
        "## A5 — summary.md reproducible from trades.csv (scripts/verify_summary.py)", "",
        md_table(["Variant", "Output", "Verdict"], a5_rows), "",
    ]
    (run_dir / "acceptance.md").write_text("\n".join(L))

    meta = {
        "run_id": args.run_id, "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "python": py, "pandas": pd.__version__, "numpy": np.__version__,
        "data_start": str(mkt.index[0].date()), "data_end": str(mkt.index[-1].date()),
        "acceptance": {k: ("PASS" if v else "FAIL") for k, v in verdicts.items()},
        "a2_status": a2_status,
        "diagnostics": {v: main_runs[v].diagnostics for v in ("A", "B")},
    }
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    print((run_dir / "acceptance.md").read_text())
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
