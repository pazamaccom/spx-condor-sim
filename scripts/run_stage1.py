#!/usr/bin/env python3
"""Stage 1 run: both sizing variants, all five acceptance tests, results folder.

Usage: run_stage1.py [--run-id ID] [--config OVERLAY]... [--refresh-data]

Parameters are read from config.yaml (frozen). Each --config overlay is a YAML
file whose top-level sections replace the corresponding sections of config.yaml
(one file per entry in docs/amendments.md). Default overlay: config-002.yaml
(amendment 002: acceptance tests A1, A3, A4 re-specified).
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
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spx_condor.backtest import RunOptions, run_backtest, realised_vol  # noqa: E402
from spx_condor.calendar_utils import monthly_expiries  # noqa: E402
from spx_condor.config import load_config  # noqa: E402
from spx_condor.data import load_market_data  # noqa: E402
from spx_condor.report import compute_summary, md_table, plot_equity, write_summary  # noqa: E402

DEFAULT_OVERLAYS = ["config-002.yaml"]


def save_run(res, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    res.trades.to_csv(out / "trades.csv", index=False)
    res.monthly.to_csv(out / "monthly.csv")
    res.daily.to_csv(out / "daily.csv")


# ---------------------------------------------------------------------------- A1
def a1_stress_windows(trades: pd.DataFrame, acc: dict) -> tuple[list[list], bool]:
    """Amendment 002: per window, >= min_cycles cycles ACTIVE in the window (open on
    any day of it) with realised P&L < 0 or MAE <= -(mult x net credit), in dollars
    at position level. Filter OFF, variant A."""
    t = trades.copy()
    t["exit_date"], t["entry_date"] = pd.to_datetime(t.exit_date), pd.to_datetime(t.entry_date)
    mult = float(acc["a1_mae_credit_mult"])
    rows, ok_all = [], True
    for name, w in acc["a1_windows"].items():
        a, b, need = pd.Timestamp(w["start"]), pd.Timestamp(w["end"]), int(w["min_cycles"])
        act = t[(t.entry_date <= b) & (t.exit_date >= a)]
        lose = act.pnl_usd < 0
        mae_hit = act.mae_usd <= -mult * act.credit_usd
        qual = lose | mae_hit
        ok = int(qual.sum()) >= need
        ok_all &= ok
        rows.append([name, need, len(act), int(lose.sum()), int(mae_hit.sum()), int(qual.sum()),
                     float(act.pnl_usd.min()) if len(act) else 0.0,
                     float(act.mae_usd.min()) if len(act) else 0.0,
                     float((act.mae_usd / act.credit_usd).min()) if len(act) else 0.0,
                     "PASS" if ok else "FAIL"])
    return rows, ok_all


# ---------------------------------------------------------------------------- A3
def _raw_vol_inputs(mkt: pd.DataFrame) -> pd.DataFrame:
    """Independent (out-of-engine) realised vols from the raw close series."""
    lr = np.log(mkt["close"]).diff()
    return pd.DataFrame({
        "close": mkt["close"], "vix": mkt["vix"],
        "rv21": lr.rolling(21).std(ddof=1) * math.sqrt(252.0),
        "rv63": lr.rolling(63).std(ddof=1) * math.sqrt(252.0),
    })


def _strikes_raw(row, dte: int, s: dict) -> tuple[float, float, float]:
    """The strike rule as written in brief 001 §Strategy rules 2, on one row of raw inputs."""
    sigma_h = max(float(row.rv21), float(row.rv63), float(row.vix) / 100.0) * math.sqrt(dte / 365.0)
    grid = float(s["strike_grid"])
    short_put = round(float(row.close) * (1.0 - s["put_sigma_mult"] * sigma_h) / grid) * grid
    short_call = round(float(row.close) * (1.0 + s["call_sigma_mult"] * sigma_h) / grid) * grid
    return sigma_h, short_put, short_call


def strike_rule_replication(mkt: pd.DataFrame, cfg, sim_start: str) -> pd.DataFrame:
    """Out-of-engine replication of the strike rule on raw index data (A3, amendment 002).

    For every monthly expiry in the simulation window: the first trading day on which
    the expiry lies dte_min..dte_max calendar days ahead (the entry rule with no filter
    and no position state), sigma_H = max(rv21, rv63, VIX/100) x sqrt(dte/365),
    short put = spot x (1 - k_p sigma_H), short call = spot x (1 + k_c sigma_H), each
    rounded to the strike grid. Uses nothing from the engine except the expiry calendar."""
    raw = _raw_vol_inputs(mkt).dropna()
    raw = raw[raw.index >= pd.Timestamp(sim_start)]
    e, s = cfg.entry, cfg.strikes
    exp_tbl = monthly_expiries(mkt.index, raw.index[0], raw.index[-1] + pd.Timedelta(days=60))
    rows = []
    for expiry in exp_tbl["expiry"]:
        win = raw[(raw.index >= expiry - pd.Timedelta(days=e["dte_max"]))
                  & (raw.index <= expiry - pd.Timedelta(days=e["dte_min"]))]
        if win.empty:
            continue
        d, row = win.index[0], win.iloc[0]
        dte = (expiry - d).days
        sigma_h, sp, sc = _strikes_raw(row, dte, s)
        rows.append({
            "expiry": expiry.date(), "entry_date": d.date(), "dte": dte, "spot": float(row.close),
            "sigma_h": sigma_h, "short_put": sp, "short_call": sc,
            "put_distance_pct": (1.0 - sp / float(row.close)) * 100.0,
            "call_distance_pct": (sc / float(row.close) - 1.0) * 100.0,
        })
    return pd.DataFrame(rows)


def strike_rule_per_cycle(trades: pd.DataFrame, mkt: pd.DataFrame, cfg) -> tuple[int, int]:
    """Diagnostic: recompute both short strikes with the out-of-engine rule on each executed
    cycle's own entry date and DTE. Returns (cycles reproduced exactly, cycles)."""
    raw = _raw_vol_inputs(mkt)
    n_ok = 0
    for r in trades.itertuples():
        row = raw.loc[pd.Timestamp(r.entry_date)]
        _, sp, sc = _strikes_raw(row, int(r.entry_dte), cfg.strikes)
        n_ok += int(sp == float(r.short_put) and sc == float(r.short_call))
    return n_ok, len(trades)


def executed_distances(trades: pd.DataFrame) -> tuple[float, float]:
    """Median short-strike distance of executed cycles, % of entry spot, (put, call)."""
    return (float((1.0 - trades.short_put / trades.entry_spot).median() * 100.0),
            float((trades.short_call / trades.entry_spot - 1.0).median() * 100.0))


def a3_strike_placement(trades_by_variant: dict[str, pd.DataFrame], rep: pd.DataFrame, acc: dict) -> tuple[list[list], bool]:
    tol, ceil = float(acc["a3_median_distance_tolerance_pp"]), float(acc["a3_touch_breach_max"]) * 100.0
    rep_put, rep_call = float(rep.put_distance_pct.median()), float(rep.call_distance_pct.median())
    rows, ok_all = [], True
    for v, t in trades_by_variant.items():
        ex_put, ex_call = executed_distances(t)
        tp, tc = float(t.put_touch.mean() * 100.0), float(t.call_touch.mean() * 100.0)
        okp = abs(ex_put - rep_put) <= tol and tp <= ceil
        okc = abs(ex_call - rep_call) <= tol and tc <= ceil
        ok_all &= okp and okc
        rows.append([v, len(t), ex_put, rep_put, ex_put - rep_put, tp, "PASS" if okp else "FAIL",
                     ex_call, rep_call, ex_call - rep_call, tc, "PASS" if okc else "FAIL"])
    return rows, ok_all


def strike_analysis_replication(mkt: pd.DataFrame, put_k: float, call_k: float) -> pd.DataFrame:
    """Diagnostic (kept from stage 1): replicate docs/strike-analysis.md from our data,
    21-trading-day horizon, sigma = 21d realised daily vol x sqrt(21) (the doc's
    definition), plus the same measurement with the strategy's sigma definition."""
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


# ---------------------------------------------------------------------------- A4
A4_METRICS = {
    "net_gain_on_book": ("Net gain on book ($)", lambda s, book: s["book_tbl"]["Final equity ($)"] - book),
    "total_premium_pnl": ("Total premium P&L ($)", lambda s, book: s["headline"]["Total premium P&L ($)"]),
}


def a4_lag_sensitivity(variant: str, base: dict, lag: dict, acc: dict, book: float) -> tuple[list[list], bool]:
    """Amendment 002: the lag must not DEGRADE the governing metric by more than
    lag_sensitivity_max (relative to |base|). Improvement is not a failure. Diagnostic
    metrics are reported under the same threshold but do not decide the verdict."""
    thr = float(acc["lag_sensitivity_max"])
    rows, ok_all = [], True
    for key in [acc["a4_governing_metric"]] + list(acc.get("a4_diagnostic_metrics", [])):
        label, getter = A4_METRICS[key]
        governing = key == acc["a4_governing_metric"]
        b0, b1 = getter(base, book), getter(lag, book)
        change = (b1 - b0) / abs(b0) if b0 else (0.0 if b1 == 0 else float("inf"))
        degraded = change < -thr
        if governing:
            ok_all &= not degraded
            verdict = "FAIL" if degraded else "PASS"
        else:
            verdict = "degraded > threshold (diagnostic)" if degraded else "within threshold (diagnostic)"
        rows.append([variant, label, "governing" if governing else "diagnostic", b0, b1, change * 100.0, verdict])
    return rows, ok_all


# ---------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=dt.datetime.now().strftime("%Y-%m-%d_%H%M") + "_stage1")
    ap.add_argument("--config", action="append", metavar="OVERLAY",
                    help=f"overlay YAML applied on config.yaml; repeatable; default {DEFAULT_OVERLAYS}")
    ap.add_argument("--refresh-data", action="store_true")
    args = ap.parse_args()
    overlays = args.config if args.config is not None else DEFAULT_OVERLAYS

    cfg = load_config(overlays=overlays)
    acc = cfg.acceptance
    book = float(cfg.sizing["book_usd"])
    run_dir = ROOT / "results" / args.run_id
    if run_dir.exists():
        sys.exit(f"results/{args.run_id} exists; results are append-only — choose a new --run-id")
    run_dir.mkdir(parents=True)
    for p in cfg.chain:
        shutil.copy(p, run_dir / p.name)
    (run_dir / "config_effective.yaml").write_text(
        "# Effective configuration: " + " + ".join(p.name for p in cfg.chain) + "\n" + yaml.safe_dump(cfg.raw, sort_keys=False))
    chain_str = " + ".join(p.name for p in cfg.chain)

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
    sim_start = main_runs["A"].diagnostics["sim_start"]

    # ---------------------------------------------------------------- A1
    a1 = run_backtest(mkt, cfg, RunOptions(variant="A", filter_on=False))
    save_run(a1, run_dir / "acceptance" / "a1_filter_off_variant_a")
    a1_rows, a1_pass = a1_stress_windows(a1.trades, acc)

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
    rep = strike_rule_replication(mkt, cfg, sim_start)
    rep.to_csv(run_dir / "acceptance" / "a3_strike_rule_replication.csv", index=False)
    a3_rows, a3_pass = a3_strike_placement({v: main_runs[v].trades for v in ("A", "B")}, rep, acc)
    a3_cycle_ok, a3_cycle_n = strike_rule_per_cycle(main_runs["A"].trades, mkt, cfg)
    doc_rep = strike_analysis_replication(mkt, cfg.strikes["put_sigma_mult"], cfg.strikes["call_sigma_mult"])
    doc_rep.to_csv(run_dir / "acceptance" / "a3_strike_analysis_replication.csv", index=False)

    # ---------------------------------------------------------------- A4
    a4_rows, a4_pass = [], True
    for v in ("A", "B"):
        lag = run_backtest(mkt, cfg, RunOptions(variant=v, filter_on=True, lag_days=1))
        save_run(lag, run_dir / "acceptance" / f"a4_lag1_variant_{v.lower()}")
        sl = compute_summary(lag.trades, lag.monthly, cfg, lag.diagnostics["sim_start"], lag.diagnostics["sim_end"])
        rows, ok = a4_lag_sensitivity(v, summaries[v], sl, acc, book)
        a4_rows += rows
        a4_pass &= ok

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
    thr = acc["lag_sensitivity_max"] * 100
    L = [
        f"# Acceptance tests — run `{args.run_id}`", "",
        f"Config: {chain_str} (A1, A3, A4 per amendment 002, docs/amendments.md). "
        f"Data: {mkt.index[0].date()} to {mkt.index[-1].date()}; simulation {sim_start} to {main_runs['A'].diagnostics['sim_end']}.", "",
        md_table(["Test", "Verdict"], [[k, ("PASS" if v else ("NOT VERIFIED" if k == "A2" and a2_status == "NOT VERIFIED" else "FAIL"))] for k, v in verdicts.items()]
                 + [["Overall", "PASS" if overall else "FAIL"]]), "",
        "## A1 — marks respond to stress (filter OFF, variant A)", "",
        f"Qualifying cycle = active in the window (open on any day of it) with realised P&L < 0 **or** MAE <= -{acc['a1_mae_credit_mult']:g}x net credit "
        "(dollars, position level; MAE = worst close-to-close mark net of the round-trip exit spread, as recorded in trades.csv). "
        "Verdict: qualifying cycles >= required.", "",
        md_table(["Window", "Required", "Cycles active", "P&L < 0", "MAE <= -credit", "Qualifying", "Worst cycle ($)", "Worst MAE ($)", "Worst MAE / credit", "Verdict"], a1_rows), "",
        "## A2 — full-period Sharpe, premium P&L only, ex-cash", "",
        md_table(["Variant", "Sharpe", "Min", "Max", "Verdict"], a2_rows), "",
        f"Status: **{a2_status}**.", "",
        "## A3 — strike placement", "",
        f"Executed = median short-strike distance of executed cycles, % of entry spot. Replication = the same median from an out-of-engine replication of the strike rule "
        f"on raw index data, one entry per monthly expiry at the first day of the {cfg.entry['dte_min']}-{cfg.entry['dte_max']} DTE window, no filter, no position state "
        f"(acceptance/a3_strike_rule_replication.csv, {len(rep)} expiries). Verdict per side: |executed - replication| <= {acc['a3_median_distance_tolerance_pp']:g} pp "
        f"and touch-basis breach <= {acc['a3_touch_breach_max']*100:g}%.", "",
        md_table(["Variant", "Cycles", "Put executed (%)", "Put replication (%)", "Put diff (pp)", "Put touch (%)", "Put verdict",
                  "Call executed (%)", "Call replication (%)", "Call diff (pp)", "Call touch (%)", "Call verdict"], a3_rows), "",
        f"Diagnostic: recomputing both short strikes with the out-of-engine rule on each executed cycle's own entry date and DTE reproduces {a3_cycle_ok} of {a3_cycle_n} cycles exactly.", "",
        "Diagnostic: replication of docs/strike-analysis.md from this run's data (21-trading-day horizon, all days from 2005-02-28), first with the document's sigma (rv21 only) and then with the strategy's sigma definition:", "",
        md_table(list(doc_rep.columns), doc_rep.values.tolist()), "",
        "## A4 — 1-day lag on all inputs (OHLC, VIX, VIX3M, VIX9D, DTB3)", "",
        f"Governing metric: {A4_METRICS[acc['a4_governing_metric']][0]}. The lag must not degrade it by more than {thr:g}% of |base|; improvement is not a failure. "
        "Diagnostic rows are reported under the same threshold and do not decide the verdict. Sharpe and max drawdown are not tested (amendment 002).", "",
        md_table(["Variant", "Metric", "Role", "Base", "Lag 1", "Change (%)", "Verdict"], a4_rows), "",
        "## A5 — summary.md reproducible from trades.csv (scripts/verify_summary.py)", "",
        md_table(["Variant", "Output", "Verdict"], a5_rows), "",
    ]
    (run_dir / "acceptance.md").write_text("\n".join(L))

    meta = {
        "run_id": args.run_id, "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "python": py, "pandas": pd.__version__, "numpy": np.__version__,
        "config_chain": [str(p.relative_to(ROOT)) for p in cfg.chain],
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
