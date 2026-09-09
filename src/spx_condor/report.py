"""Summary statistics, summary.md and equity chart for one variant run.

Every number written to summary.md is recomputed independently by
scripts/verify_summary.py from trades.csv + monthly.csv. Definitions are
stated in summary.md; keep the two in sync.
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import Config

EVENT_WINDOWS = {
    "2008": ("2008-01-01", "2008-12-31"),
    "Feb 2018": ("2018-02-01", "2018-02-28"),
    "Mar 2020": ("2020-03-01", "2020-03-31"),
    "2022": ("2022-01-01", "2022-12-31"),
    "Aug 2024": ("2024-08-01", "2024-08-31"),
    "Apr 2025": ("2025-04-01", "2025-04-30"),
    "Mar 2026": ("2026-03-01", "2026-03-31"),
}


def premium_monthly_from_trades(trades: pd.DataFrame, months: pd.Index) -> pd.Series:
    """Realised premium P&L by exit month, zero where no cycle closed."""
    if trades.empty:
        return pd.Series(0.0, index=months)
    m = pd.to_datetime(trades["exit_date"]).dt.to_period("M").astype(str)
    return trades.groupby(m)["pnl_usd"].sum().reindex(months).fillna(0.0)


def curve_stats(pnl: pd.Series, book: float, years: float) -> dict:
    eq = book + pnl.cumsum()
    prev = eq.shift(1).fillna(book)
    ret = pnl / prev
    sd = ret.std(ddof=1)
    return {
        "final": float(eq.iloc[-1]),
        "cagr_pct": ((eq.iloc[-1] / book) ** (1.0 / years) - 1.0) * 100.0,
        "vol_pct": sd * math.sqrt(12.0) * 100.0,
        "sharpe": (ret.mean() / sd * math.sqrt(12.0)) if sd > 0 else float("nan"),
        **drawdown(eq, book),
    }


def drawdown(eq: pd.Series, book: float) -> dict:
    """Max drawdown on month-end values, with the starting book as the first peak."""
    full = pd.concat([pd.Series([book], index=["start"]), eq])
    peak = full.cummax()
    dd_pct = full / peak - 1.0
    trough = dd_pct.idxmin()
    trough_pos = list(full.index).index(trough)
    peak_val = peak.loc[trough]
    peak_month = [i for i in full.index[: trough_pos + 1] if full.loc[i] == peak_val][-1]
    return {
        "mdd_pct": float(dd_pct.min()) * 100.0,
        "mdd_usd": float(full.loc[trough] - peak_val),
        "mdd_peak": str(peak_month),
        "mdd_trough": str(trough),
    }


def compute_summary(trades: pd.DataFrame, monthly: pd.DataFrame, cfg: Config,
                    sim_start: str, sim_end: str) -> dict:
    book = float(cfg.sizing["book_usd"])
    years = (pd.Timestamp(sim_end) - pd.Timestamp(sim_start)).days / 365.25
    months = monthly.index
    t = trades.copy()
    t["exit_date"] = pd.to_datetime(t["exit_date"])
    t["entry_date"] = pd.to_datetime(t["entry_date"])

    prem = premium_monthly_from_trades(t, months)
    prem_stats = curve_stats(prem, book, years)
    total_pnl = monthly["equity"] - monthly["equity"].shift(1).fillna(book)
    tot_stats = curve_stats(total_pnl, book, years)

    wins, losses = t[t.pnl_usd > 0], t[t.pnl_usd < 0]
    headline = {
        "Cycles": len(t),
        "Total premium P&L ($)": float(t.pnl_usd.sum()),
        "Premium-only CAGR (%)": prem_stats["cagr_pct"],
        "Premium-only ann. vol (%)": prem_stats["vol_pct"],
        "Sharpe, premium-only ex-cash": prem_stats["sharpe"],
        "Premium-only max drawdown ($)": prem_stats["mdd_usd"],
        "Premium-only max drawdown (%)": prem_stats["mdd_pct"],
        "Win rate (%)": float((t.pnl_usd > 0).mean() * 100.0),
        "Avg win ($)": float(wins.pnl_usd.mean()) if len(wins) else 0.0,
        "Avg loss ($)": float(losses.pnl_usd.mean()) if len(losses) else 0.0,
        "Profit factor": float(wins.pnl_usd.sum() / -losses.pnl_usd.sum()) if len(losses) else float("inf"),
        "Profit-target exits": int((t.exit_reason == "profit_target").sum()),
        "DTE exits": int((t.exit_reason == "dte_exit").sum()),
        "Expiry settlements": int((t.exit_reason == "expiry_settlement").sum()),
        "Avg days held": float(t.days_held.mean()),
        "Avg contracts": float(t.contracts.mean()),
        "Max contracts": int(t.contracts.max()),
        "Avg net credit (index pts)": float(t.credit_net.mean()),
        "Avg credit / width (%)": float((t.credit_net / t.width).mean() * 100.0),
        "Put-side breach, finish (%)": float(t.put_finish.mean() * 100.0),
        "Call-side breach, finish (%)": float(t.call_finish.mean() * 100.0),
        "Put-side breach, touch (%)": float(t.put_touch.mean() * 100.0),
        "Call-side breach, touch (%)": float(t.call_touch.mean() * 100.0),
        "Same-expiry re-entries": int(t.same_expiry_reentry.sum()),
    }
    book_tbl = {
        "Final equity ($)": float(monthly["equity"].iloc[-1]),
        "Total cash interest ($)": float(monthly["cash_pnl"].sum()),
        "Total premium P&L incl. open mark ($)": float(monthly["premium_pnl"].sum()),
        "CAGR (%)": tot_stats["cagr_pct"],
        "Ann. vol (%)": tot_stats["vol_pct"],
        "Max drawdown ($)": tot_stats["mdd_usd"],
        "Max drawdown (%)": tot_stats["mdd_pct"],
    }
    dd_dates = {
        "premium": (prem_stats["mdd_peak"], prem_stats["mdd_trough"]),
        "total": (tot_stats["mdd_peak"], tot_stats["mdd_trough"]),
    }
    worst5 = t.nsmallest(5, "pnl_usd")[["entry_date", "exit_date", "exit_reason", "contracts",
                                         "short_put", "short_call", "exit_spot", "pnl_usd", "mae_usd"]]

    years_idx = sorted(set(t.exit_date.dt.year) | set(int(m[:4]) for m in months))
    by_year = []
    for y in years_idx:
        ty = t[t.exit_date.dt.year == y]
        my = monthly[[m.startswith(str(y)) for m in months]]
        by_year.append({
            "Year": y, "Cycles": len(ty),
            "Win rate (%)": float((ty.pnl_usd > 0).mean() * 100.0) if len(ty) else 0.0,
            "Premium P&L ($)": float(ty.pnl_usd.sum()),
            "Worst cycle ($)": float(ty.pnl_usd.min()) if len(ty) else 0.0,
            "Cash P&L ($)": float(my["cash_pnl"].sum()),
            "Total P&L ($)": float(my["total_pnl"].sum()),
            "Year-end equity ($)": float(my["equity"].iloc[-1]),
        })

    events = []
    for name, (a, b) in EVENT_WINDOWS.items():
        te = t[(t.exit_date >= a) & (t.exit_date <= b)]
        ta = t[(t.entry_date <= b) & (t.exit_date >= a)]
        pa, pb = pd.Timestamp(a).to_period("M"), pd.Timestamp(b).to_period("M")
        me = monthly[[pa <= pd.Period(m, "M") <= pb for m in months]]
        events.append({
            "Window": name, "Cycles exiting": len(te), "Losing cycles": int((te.pnl_usd < 0).sum()),
            "Premium P&L, exits ($)": float(te.pnl_usd.sum()),
            "Worst cycle ($)": float(te.pnl_usd.min()) if len(te) else 0.0,
            "Worst MAE, active cycles ($)": float(ta.mae_usd.min()) if len(ta) else 0.0,
            "Premium P&L, monthly ($)": float(me["premium_pnl"].sum()),
            "Total P&L, monthly ($)": float(me["total_pnl"].sum()),
        })
    return {
        "book": book, "years": years, "sim_start": sim_start, "sim_end": sim_end,
        "headline": headline, "book_tbl": book_tbl, "dd_dates": dd_dates,
        "worst5": worst5, "by_year": by_year, "events": events,
    }


# ---------------------------------------------------------------- formatting

def fmt(v) -> str:
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    if isinstance(v, float):
        if math.isinf(v):
            return "inf"
        if abs(v) >= 100:
            return f"{v:,.0f}"
        return f"{v:.2f}"
    return str(v)


def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(fmt(c) for c in r) + " |")
    return "\n".join(out)


ASSUMPTIONS = """\
1. **Pricing is synthetic.** Black-Scholes on the index, r = DTB3 converted from bank-discount basis to a continuously-compounded actual/365 rate (91-day bill), q = {q:.1%} continuous, T = calendar days / 365. Stage 2 replaces this with real option prices.
2. **Volatility surface.** ATM vol for tenor T is VIX (30d) and VIX3M (90d) interpolated linearly in total variance vs calendar days, extrapolated on the same line below 30 days (needed for marks between 21 and 30 DTE). Vol floor {vf:.0%}; floor hits are counted in diagnostics. Skew is one smile in strike space: +{ps} vol pts per 1% below spot, {cs} vol pts per 1% above spot — applied by strike, not by option type (put-call parity consistent). VIX9D is downloaded but not used by any pre-registered rule.
3. **VIX3M availability.** VIX3M history starts {vix3m_first}. Before that the term structure is flat at VIX and the VIX > VIX3M filter cannot trigger (treated as not inverted). Affects Jan 2005 - Jul 2006 only.
4. **Fills and costs.** Every leg crosses {ba} index points of spread on entry and on exit (0.40/condor each way). Commission ${comm} per leg per contract each way ($10 per contract round trip). Expiry settlement (guard path only) is cash-settled at intrinsic with no spread and no exit commission.
5. **Entry credit** is the net credit after spread. The 50% profit-take test uses the executable exit cost (mid + spread): captured = (credit_net - debit_net) / credit_net >= {pt:.0%}. Checked at each daily close from the day after entry.
6. **Exit precedence.** At a close where both the profit target and DTE <= {dte} hold, the exit is labelled profit_target.
7. **Entry timing.** An entry is attempted at every close on which some monthly expiry is {dmin}-{dmax} calendar days ahead and no position is open; if the filter blocks, the next close is tried while the window holds. Consequently a quick profit-take can be followed by a second cycle on the same expiry ("same-expiry re-entries", counted in the headline table). Entries where the mid credit is below the round-trip spread (net credit <= 0) are skipped and counted in diagnostics.
8. **Strikes.** Short strikes rounded to the {grid}-point grid first; width = {w} points if spot >= 6000 else {wp:.1%} of spot, rounded to the grid (min one grid step); long strikes = short -/+ width.
9. **Realised vol** = stdev of daily log returns over the trailing 21 / 63 trading days ending at the entry close, annualised with sqrt(252). VIX-implied = VIX/100. sigma_H = max of the three x sqrt(DTE/365).
10. **Sizing B** uses equity at the entry close (= cash, as no position is open) and max loss = (width - credit_net) x {mult}.
11. **Cash** accrues daily at the previous close's DTB3-derived rate for the calendar days elapsed, on the whole cash balance (defined-risk spreads; no margin is deducted). Open positions are marked at cost-to-close incl. spread, excluding the exit commission.
12. **Premium-only statistics** (the A2 Sharpe) attribute each cycle's realised P&L to its exit month, ignore the open-position mark, use returns on the previous month's premium-only equity starting from ${book:,.0f}, and Sharpe = mean / stdev x sqrt(12) with no further risk-free deduction (cash is already excluded). Months with no exits count as zero-return months.
13. **Breach definitions.** "finish" = index close beyond the short strike on the cycle's exit day; "touch" = daily low/high beyond the short strike on any day after entry up to and including exit. A3 is judged on the finish basis (the basis of the 2-5% / 4-9% ranges in docs/strike-analysis.md).
14. **Drawdowns** are on month-end values (with the starting book as the first peak), so intra-month drawdowns are understated.
15. **Book.** All dollar figures are on the ${book:,.0f} book. Python {py} rather than 3.12 (the brief's stack); no behavioural difference expected.
"""


def write_summary(path: Path, s: dict, cfg: Config, variant: str, run_id: str,
                  diagnostics: dict, py_version: str) -> None:
    p = cfg.pricing
    a = ASSUMPTIONS.format(
        q=cfg.data["dividend_yield"], vf=0.01, ps=p["put_skew_per_pct_otm"], cs=p["call_skew_per_pct_otm"],
        vix3m_first=diagnostics.get("first_vix3m_date"), ba=p["bid_ask_per_leg_points"],
        comm=p["commission_per_leg_contract_usd"], pt=cfg.exit["profit_take_fraction"], dte=cfg.exit["dte_exit"],
        dmin=cfg.entry["dte_min"], dmax=cfg.entry["dte_max"], grid=cfg.strikes["strike_grid"],
        w=cfg.strikes["width_points"], wp=cfg.strikes["width_pct_below_6000"], mult=p["multiplier"],
        book=s["book"], py=py_version,
    )
    sizing = ("fixed %d contracts" % cfg.sizing["variant_a_contracts"]) if variant == "A" else (
        "contracts = floor(%.3f x equity / max loss)" % cfg.sizing["variant_b_risk_fraction"])
    lines = [
        f"# Stage 1 summary — variant {variant} ({sizing})",
        "",
        f"Run: `{run_id}`. Simulation window: {s['sim_start']} to {s['sim_end']} ({s['years']:.2f} years). "
        f"Book: ${s['book']:,.0f}. Config: `config.yaml` (frozen 2026-09-09, copied into this run folder).",
        "",
        "All numbers below are recomputed from `trades.csv` (and `monthly.csv` for cash / book-equity figures) "
        "by `scripts/verify_summary.py`.",
        "",
        "## Headline — premium P&L only (from trades.csv)",
        "",
        md_table(["Metric", "Value"], [[k, v] for k, v in s["headline"].items()]),
        "",
        f"Premium-only max drawdown: peak {s['dd_dates']['premium'][0]}, trough {s['dd_dates']['premium'][1]} (month-end basis).",
        "",
        "## Book equity incl. cash (from monthly.csv)",
        "",
        md_table(["Metric", "Value"], [[k, v] for k, v in s["book_tbl"].items()]),
        "",
        f"Book max drawdown: peak {s['dd_dates']['total'][0]}, trough {s['dd_dates']['total'][1]} (month-end basis).",
        "",
        "## Worst 5 cycles",
        "",
        md_table(["Entry", "Exit", "Reason", "Contracts", "Short put", "Short call", "Exit spot", "P&L ($)", "MAE ($)"],
                 [[str(r.entry_date.date()), str(r.exit_date.date()), r.exit_reason, int(r.contracts),
                   float(r.short_put), float(r.short_call), float(r.exit_spot), float(r.pnl_usd), float(r.mae_usd)]
                  for r in s["worst5"].itertuples()]),
        "",
        "## By calendar year (cycles attributed to exit year)",
        "",
        md_table(list(s["by_year"][0].keys()), [list(r.values()) for r in s["by_year"]]),
        "",
        "## Event windows (cycles attributed to exit date; MAE over cycles active in the window)",
        "",
        md_table(list(s["events"][0].keys()), [list(r.values()) for r in s["events"]]),
        "",
        "## Diagnostics",
        "",
        md_table(["Item", "Value"], [[k, str(v)] for k, v in diagnostics.items()]),
        "",
        "## Assumptions affecting the numbers",
        "",
        a,
    ]
    path.write_text("\n".join(lines))


def plot_equity(path: Path, daily: pd.DataFrame, trades: pd.DataFrame, book: float, variant: str) -> None:
    fig, ax = plt.subplots(figsize=(13, 6))
    d = daily.copy()
    t = trades.copy()
    t["exit_date"] = pd.to_datetime(t["exit_date"])
    prem = t.groupby("exit_date")["pnl_usd"].sum().reindex(d.index).fillna(0.0).cumsum() + book
    ax.plot(d.index, d["equity"], lw=1.2, label="Book equity (premium + cash)")
    ax.plot(d.index, prem, lw=1.0, label="Premium-only (realised, no cash)")
    # shade filter-active periods (VIX > VIX3M)
    fa = d["filter_active"].astype(bool).values
    idx = d.index
    start = None
    first = True
    for i, flag in enumerate(fa):
        if flag and start is None:
            start = idx[i]
        if (not flag or i == len(fa) - 1) and start is not None:
            ax.axvspan(start, idx[i], color="tab:red", alpha=0.15, lw=0,
                       label="Filter active (VIX > VIX3M)" if first else None)
            first = False
            start = None
    ax.set_title(f"SPX iron condor — stage 1 synthetic pricing — variant {variant}")
    ax.set_ylabel("USD")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
