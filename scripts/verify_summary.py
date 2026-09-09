#!/usr/bin/env python3
"""Acceptance test A5: recompute every number in summary.md from trades.csv
(and monthly.csv for cash / book-equity figures) with independent code, and
compare against the numbers parsed out of summary.md.

Deliberately does NOT import spx_condor — the point is an independent path.

Usage: verify_summary.py <variant_dir> [--book 400000]
Exit code 0 = every number reproduced, 1 otherwise.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EVENT_WINDOWS = {
    "2008": ("2008-01-01", "2008-12-31"), "Feb 2018": ("2018-02-01", "2018-02-28"),
    "Mar 2020": ("2020-03-01", "2020-03-31"), "2022": ("2022-01-01", "2022-12-31"),
    "Aug 2024": ("2024-08-01", "2024-08-31"), "Apr 2025": ("2025-04-01", "2025-04-30"),
    "Mar 2026": ("2026-03-01", "2026-03-31"),
}


# ------------------------------------------------------------- parse summary.md

def parse_tables(md: str) -> dict[str, list[dict]]:
    """Return {section heading: [row dicts]} for every markdown table."""
    tables, section, headers, rows = {}, None, None, []
    for line in md.splitlines():
        if line.startswith("## "):
            if headers:
                tables[section] = rows
            section, headers, rows = line[3:].strip(), None, []
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if headers is None:
                headers = cells
            elif all(set(c) <= {"-"} for c in cells):
                continue
            else:
                rows.append(dict(zip(headers, cells)))
        elif headers and rows:
            tables[section] = rows
            headers, rows = None, []
    if headers and rows:
        tables[section] = rows
    return tables


def num(s: str) -> float:
    s = s.replace(",", "")
    if s == "inf":
        return math.inf
    return float(s)


def tol(printed: str) -> float:
    """Half a unit of the last printed digit, plus slack for float formatting."""
    s = printed.replace(",", "")
    if "." in s:
        dec = len(s.split(".")[1])
        return 0.5 * 10 ** (-dec) + 1e-9
    return 0.5 + 1e-9


# --------------------------------------------------------------- recompute

def monthly_returns(pnl: pd.Series, book: float):
    eq = book + pnl.cumsum()
    prev = eq.shift(1)
    prev.iloc[0] = book
    return eq, pnl / prev


def max_dd(eq: pd.Series, book: float):
    vals = np.concatenate([[book], eq.values])
    labels = ["start"] + list(eq.index)
    peak = np.maximum.accumulate(vals)
    dd = vals / peak - 1.0
    i = int(np.argmin(dd))
    j = max(k for k in range(i + 1) if vals[k] == peak[i])
    return dd[i] * 100.0, vals[i] - peak[i], labels[j], labels[i]


def recompute(trades: pd.DataFrame, monthly: pd.DataFrame, book: float, sim_start: str, sim_end: str) -> dict:
    t = trades.copy()
    t["exit_date"] = pd.to_datetime(t["exit_date"])
    t["entry_date"] = pd.to_datetime(t["entry_date"])
    months = list(monthly["month"])
    years = (pd.Timestamp(sim_end) - pd.Timestamp(sim_start)).days / 365.25

    pm = t.groupby(t["exit_date"].dt.strftime("%Y-%m"))["pnl_usd"].sum()
    prem = pd.Series([float(pm.get(m, 0.0)) for m in months], index=months)
    peq, pret = monthly_returns(prem, book)
    p_dd_pct, p_dd_usd, p_peak, p_trough = max_dd(peq, book)

    eq = pd.Series(monthly["equity"].values, index=months)
    tot_pnl = eq.diff()
    tot_pnl.iloc[0] = eq.iloc[0] - book
    _, tret = monthly_returns(tot_pnl, book)
    t_dd_pct, t_dd_usd, t_peak, t_trough = max_dd(eq, book)

    w, l = t[t.pnl_usd > 0], t[t.pnl_usd < 0]
    out = {}
    out["Headline — premium P&L only (from trades.csv)"] = {
        "Cycles": len(t),
        "Total premium P&L ($)": t.pnl_usd.sum(),
        "Premium-only CAGR (%)": ((peq.iloc[-1] / book) ** (1 / years) - 1) * 100,
        "Premium-only ann. vol (%)": pret.std(ddof=1) * math.sqrt(12) * 100,
        "Sharpe, premium-only ex-cash": pret.mean() / pret.std(ddof=1) * math.sqrt(12),
        "Premium-only max drawdown ($)": p_dd_usd,
        "Premium-only max drawdown (%)": p_dd_pct,
        "Win rate (%)": (t.pnl_usd > 0).mean() * 100,
        "Avg win ($)": w.pnl_usd.mean(),
        "Avg loss ($)": l.pnl_usd.mean(),
        "Profit factor": w.pnl_usd.sum() / -l.pnl_usd.sum() if len(l) else math.inf,
        "Profit-target exits": (t.exit_reason == "profit_target").sum(),
        "DTE exits": (t.exit_reason == "dte_exit").sum(),
        "Expiry settlements": (t.exit_reason == "expiry_settlement").sum(),
        "Avg days held": t.days_held.mean(),
        "Avg contracts": t.contracts.mean(),
        "Max contracts": t.contracts.max(),
        "Avg net credit (index pts)": t.credit_net.mean(),
        "Avg credit / width (%)": (t.credit_net / t.width).mean() * 100,
        "Put-side breach, finish (%)": t.put_finish.mean() * 100,
        "Call-side breach, finish (%)": t.call_finish.mean() * 100,
        "Put-side breach, touch (%)": t.put_touch.mean() * 100,
        "Call-side breach, touch (%)": t.call_touch.mean() * 100,
        "Same-expiry re-entries": t.same_expiry_reentry.sum(),
    }
    out["Book equity incl. cash (from monthly.csv)"] = {
        "Final equity ($)": eq.iloc[-1],
        "Total cash interest ($)": monthly["cash_pnl"].sum(),
        "Total premium P&L incl. open mark ($)": monthly["premium_pnl"].sum(),
        "CAGR (%)": ((eq.iloc[-1] / book) ** (1 / years) - 1) * 100,
        "Ann. vol (%)": tret.std(ddof=1) * math.sqrt(12) * 100,
        "Max drawdown ($)": t_dd_usd,
        "Max drawdown (%)": t_dd_pct,
    }
    out["_dd_dates"] = {"premium": (p_peak, p_trough), "total": (t_peak, t_trough)}

    worst = t.nsmallest(5, "pnl_usd")
    out["Worst 5 cycles"] = [
        {"Entry": str(r.entry_date.date()), "Exit": str(r.exit_date.date()), "Reason": r.exit_reason,
         "Contracts": r.contracts, "Short put": r.short_put, "Short call": r.short_call,
         "Exit spot": r.exit_spot, "P&L ($)": r.pnl_usd, "MAE ($)": r.mae_usd}
        for r in worst.itertuples()
    ]
    by_year = []
    for y in sorted(set(t.exit_date.dt.year) | {int(m[:4]) for m in months}):
        ty = t[t.exit_date.dt.year == y]
        my = monthly[monthly["month"].str.startswith(str(y))]
        by_year.append({
            "Year": y, "Cycles": len(ty),
            "Win rate (%)": (ty.pnl_usd > 0).mean() * 100 if len(ty) else 0.0,
            "Premium P&L ($)": ty.pnl_usd.sum(), "Worst cycle ($)": ty.pnl_usd.min() if len(ty) else 0.0,
            "Cash P&L ($)": my["cash_pnl"].sum(), "Total P&L ($)": my["total_pnl"].sum(),
            "Year-end equity ($)": my["equity"].iloc[-1],
        })
    out["By calendar year (cycles attributed to exit year)"] = by_year
    ev = []
    for name, (a, b) in EVENT_WINDOWS.items():
        te = t[(t.exit_date >= a) & (t.exit_date <= b)]
        ta = t[(t.entry_date <= b) & (t.exit_date >= a)]
        me = monthly[(monthly["month"] >= a[:7]) & (monthly["month"] <= b[:7])]
        ev.append({
            "Window": name, "Cycles exiting": len(te), "Losing cycles": (te.pnl_usd < 0).sum(),
            "Premium P&L, exits ($)": te.pnl_usd.sum(),
            "Worst cycle ($)": te.pnl_usd.min() if len(te) else 0.0,
            "Worst MAE, active cycles ($)": ta.mae_usd.min() if len(ta) else 0.0,
            "Premium P&L, monthly ($)": me["premium_pnl"].sum(),
            "Total P&L, monthly ($)": me["total_pnl"].sum(),
        })
    out["Event windows (cycles attributed to exit date; MAE over cycles active in the window)"] = ev
    return out


# ------------------------------------------------------------------ compare

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("variant_dir")
    ap.add_argument("--book", type=float, default=400000.0)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    d = Path(args.variant_dir)
    md = (d / "summary.md").read_text()
    trades = pd.read_csv(d / "trades.csv")
    monthly = pd.read_csv(d / "monthly.csv")
    m = re.search(r"Simulation window: (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", md)
    sim_start, sim_end = m.group(1), m.group(2)
    tables = parse_tables(md)
    calc = recompute(trades, monthly, args.book, sim_start, sim_end)

    checked = failed = 0
    fails: list[str] = []

    def check(label: str, printed: str, value) -> None:
        nonlocal checked, failed
        checked += 1
        try:
            ok = abs(num(printed) - float(value)) <= tol(printed) or (num(printed) == value)
        except ValueError:
            ok = printed == str(value)
        if not ok:
            failed += 1
            fails.append(f"{label}: summary={printed} recomputed={value}")

    for section in ("Headline — premium P&L only (from trades.csv)", "Book equity incl. cash (from monthly.csv)"):
        rows = {r["Metric"]: r["Value"] for r in tables[section]}
        for k, v in calc[section].items():
            check(f"{section} / {k}", rows[k], v)
    for section in ("Worst 5 cycles", "By calendar year (cycles attributed to exit year)",
                    "Event windows (cycles attributed to exit date; MAE over cycles active in the window)"):
        rows = tables[section]
        exp = calc[section]
        if len(rows) != len(exp):
            failed += 1
            fails.append(f"{section}: {len(rows)} rows in summary vs {len(exp)} recomputed")
            continue
        for r, e in zip(rows, exp):
            for k, v in e.items():
                check(f"{section} / {list(e.values())[0]} / {k}", r[k], v)
    # drawdown dates (text lines)
    for key, label in (("premium", "Premium-only max drawdown"), ("total", "Book max drawdown")):
        mm = re.search(rf"{label}: peak (\S+), trough (\S+)", md)
        checked += 1
        if mm is None or (mm.group(1), mm.group(2)) != tuple(calc["_dd_dates"][key]):
            failed += 1
            fails.append(f"{label} dates: summary={mm.groups() if mm else None} recomputed={calc['_dd_dates'][key]}")

    status = "PASS" if failed == 0 else "FAIL"
    print(f"A5 verify_summary [{d}]: {status} — {checked - failed}/{checked} numbers reproduced")
    for f in fails:
        print("  MISMATCH", f)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
