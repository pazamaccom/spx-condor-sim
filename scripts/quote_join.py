#!/usr/bin/env python3
"""Brief 002 Part 2 — join the stage-1 cycles to observed optionsDX SPX end-of-day quotes.

For every cycle of results/2026-09-09_stage1/variant_a/trades.csv with entry >= 2010-01-01 and
exit <= 2023-12-31, look up all four legs on the entry date and on the exit date in the vendor
chains (data/quotes/eod/, git-ignored), keyed on (quote date, expiry, strike, right). Alongside
each observed quote the engine's own synthetic Black-Scholes mid is recomputed leg by leg
(src/spx_condor/pricing.py, same inputs as the run) and checked against trades.csv.

Vendor expiry labels (established from the label census, data/quotes/derived/expiry_labels.csv):
  2010 – early 2016  the AM-settled monthly is labelled by its last trading day (the Thursday);
  2016 onwards       by the third Friday itself, and from 2022 a separate Thursday SPXW weekly
                     exists beside it (a different contract).
Join rule: the engine expiry date first; the previous calendar day only if that label is absent.

Outputs (data/quotes/derived/, committed — derived tables only, never raw vendor rows):
  legs_joined.csv      one row per leg per date: engine strike/spot/dte/vix/r, synthetic mid,
                       observed bid/ask/mid/half-spread/size/volume/IV, join status and cause
  missing_legs.csv     every leg that did not join: date, expiry, strike, moneyness, nearest listed
                       strikes and the probable cause
  expiry_labels.csv    census of every expiry label in the vendor files (rows, first/last quote date)
  join_coverage.md     coverage summary for the report

--substitute-strikes N   (off by default) when the engine strike is not listed, take the nearest
                         listed strike within N points and reprice the synthetic leg at that strike,
                         flagging the row (`substituted`). Requires Paolo's confirmation before use.
--refresh-extract        re-read the 168 monthly vendor files instead of data/cache/optionsdx_extract.pkl.
"""
from __future__ import annotations

import argparse
import glob
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from spx_condor.config import load_config  # noqa: E402
from spx_condor.data import load_market_data  # noqa: E402
from spx_condor.pricing import bs_price, condor_leg_mids, condor_net, strike_vol, atm_vol_for_tenor  # noqa: E402

TRADES = ROOT / "results/2026-09-09_stage1/variant_a/trades.csv"
EOD_DIR = ROOT / "data/quotes/eod"
DERIVED = ROOT / "data/quotes/derived"
EXTRACT_CACHE = ROOT / "data/cache/optionsdx_extract.pkl"
WINDOW = ("2010-01-01", "2023-12-31")
KEEP_COLS = ["QUOTE_DATE", "UNDERLYING_LAST", "EXPIRE_DATE", "DTE", "STRIKE",
             "C_BID", "C_ASK", "C_LAST", "C_SIZE", "C_VOLUME", "C_IV", "C_DELTA",
             "P_BID", "P_ASK", "P_LAST", "P_SIZE", "P_VOLUME", "P_IV", "P_DELTA"]
LEGS = ["long_put", "short_put", "short_call", "long_call"]


def third_friday(y: int, m: int) -> pd.Timestamp:
    d = pd.Timestamp(y, m, 1)
    return d + pd.Timedelta(days=(4 - d.weekday()) % 7 + 14)


def cycles_in_window() -> pd.DataFrame:
    t = pd.read_csv(TRADES, parse_dates=["entry_date", "exit_date", "expiry", "nominal_expiry"])
    s = t[(t.entry_date >= WINDOW[0]) & (t.exit_date <= WINDOW[1])].reset_index(drop=True)
    s.index.name = "cycle"
    return s


def needed_dates(cycles: pd.DataFrame) -> set[str]:
    """Entry and exit dates, plus Wed–Fri of every third-Friday week (expiry-week checks) and 10
    seeded random business days (provenance sample)."""
    dates = set(cycles.entry_date) | set(cycles.exit_date)
    for y in range(2010, 2024):
        for m in range(1, 13):
            f = third_friday(y, m)
            dates |= {f - pd.Timedelta(days=k) for k in (0, 1, 2)}
    rng = np.random.default_rng(20260910)
    dates |= set(pd.Timestamp(x) for x in rng.choice(pd.bdate_range(*WINDOW), 10, replace=False))
    return {d.strftime("%Y-%m-%d") for d in dates}


def extract(dates: set[str], refresh: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One pass over the monthly vendor files. Returns (rows on the needed dates, expiry-label census)."""
    census_path = DERIVED / "expiry_labels.csv"
    if EXTRACT_CACHE.exists() and census_path.exists() and not refresh:
        ex = pd.read_pickle(EXTRACT_CACHE)
        if set(ex.QUOTE_DATE.dt.strftime("%Y-%m-%d").unique()) >= (dates & set(ex.attrs.get("requested", dates))):
            return ex, pd.read_csv(census_path)
    files = sorted(glob.glob(str(EOD_DIR / "spx_eod_*.txt")))
    if len(files) != 168:
        sys.exit(f"expected 168 monthly files under {EOD_DIR}, found {len(files)} — is the SSD mounted?")
    parts, census, t0 = [], [], time.time()
    for i, f in enumerate(files):
        df = pd.read_csv(f, skipinitialspace=True, low_memory=False)
        df.columns = [c.strip().strip("[]") for c in df.columns]
        g = df.groupby("EXPIRE_DATE").agg(rows=("STRIKE", "size"), first_quote=("QUOTE_DATE", "min"),
                                          last_quote=("QUOTE_DATE", "max")).reset_index()
        g["file"] = Path(f).name
        census.append(g)
        parts.append(df.loc[df.QUOTE_DATE.isin(dates), KEEP_COLS])
        print(f"  {i + 1}/{len(files)} {Path(f).name} rows={len(df)} kept={len(parts[-1])} {time.time() - t0:.0f}s", flush=True)
    ex = pd.concat(parts, ignore_index=True)
    ex["QUOTE_DATE"] = pd.to_datetime(ex.QUOTE_DATE)
    ex["EXPIRE_DATE"] = pd.to_datetime(ex.EXPIRE_DATE)
    ex.attrs["requested"] = sorted(dates)
    EXTRACT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ex.to_pickle(EXTRACT_CACHE)
    cen = pd.concat(census, ignore_index=True)
    cen.to_csv(census_path, index=False)
    return ex, cen


def synthetic_legs(cycles: pd.DataFrame) -> pd.DataFrame:
    """Engine mids per leg on entry and exit dates; asserts they reproduce trades.csv exactly."""
    cfg = load_config("config.yaml")
    md = load_market_data(cfg)
    p, q, ba = cfg.pricing, cfg.data["dividend_yield"], cfg.pricing["bid_ask_per_leg_points"]
    rows, bad = [], 0
    for i, c in cycles.iterrows():
        strikes = {k: float(c[k]) for k in LEGS}
        for when, date in (("entry", c.entry_date), ("exit", c.exit_date)):
            m = md.loc[date]
            dte = (c.expiry - date).days
            mids, _ = condor_leg_mids(float(m["close"]), strikes, dte, float(m["r"]), q, float(m["vix"]), float(m["vix3m"]),
                                      p["put_skew_per_pct_otm"], p["call_skew_per_pct_otm"])
            net = condor_net(mids)
            ref = c.credit_mid if when == "entry" else c.exit_debit_net - 4 * ba
            bad += abs(net - ref) > 1e-9
            for leg in LEGS:
                rows.append(dict(cycle=i, when=when, date=date, entry_date=c.entry_date, exit_date=c.exit_date,
                                 expiry=c.expiry, exit_reason=c.exit_reason, leg=leg, right="P" if "put" in leg else "C",
                                 strike=strikes[leg], spot=float(m["close"]), dte=dte, vix=float(m["vix"]),
                                 vix3m=float(m["vix3m"]), r=float(m["r"]), synth_mid=mids[leg], synth_net=net))
    if bad:
        sys.exit(f"synthetic reconstruction does not reproduce trades.csv on {bad} cycle-dates")
    return pd.DataFrame(rows), (cfg, md)


def reprice(leg_row, strike: float, cfg, q: float) -> float:
    p = cfg.pricing
    atm, _ = atm_vol_for_tenor(leg_row.vix, leg_row.vix3m, leg_row.dte)
    sig = strike_vol(atm, leg_row.spot, strike, p["put_skew_per_pct_otm"], p["call_skew_per_pct_otm"])
    return bs_price("put" if leg_row.right == "P" else "call", leg_row.spot, strike, leg_row.dte / 365.0, leg_row.r, q, sig)


def join(legs: pd.DataFrame, ex: pd.DataFrame, cfg, substitute: float | None) -> pd.DataFrame:
    chain_rows = ex.groupby(["QUOTE_DATE", "EXPIRE_DATE"]).size()
    idx = ex.set_index(["QUOTE_DATE", "EXPIRE_DATE", "STRIKE"]).sort_index()
    have_dates = set(ex.QUOTE_DATE.unique())
    q = cfg.data["dividend_yield"]
    out = []
    for _, l in legs.iterrows():
        rec = dict(l)
        rec.update(label=pd.NaT, label_offset=np.nan, chain_rows=0, listed_below=np.nan, listed_above=np.nan,
                   substituted=False, obs_strike=np.nan, synth_mid_obs_strike=np.nan,
                   bid=np.nan, ask=np.nan, last=np.nan, size="", volume=np.nan, iv=np.nan, delta=np.nan, u_last=np.nan, cause="")
        if l.date not in have_dates:
            rec["cause"] = "vendor has no rows on this quote date"
            out.append(rec)
            continue
        label = None
        for off in (0, 1):
            cand = l.expiry - pd.Timedelta(days=off)
            if (l.date, cand) in chain_rows.index:
                label, rec["label"], rec["label_offset"], rec["chain_rows"] = cand, cand, off, int(chain_rows.loc[(l.date, cand)])
                break
        if label is None:
            near = sorted(str(x.date()) for x in ex.loc[ex.QUOTE_DATE == l.date, "EXPIRE_DATE"].unique() if abs((x - l.expiry).days) <= 7)
            rec["cause"] = f"no chain labelled {l.expiry.date()} or the day before; labels within a week: {near}"
            out.append(rec)
            continue
        strikes = idx.loc[(l.date, label)].index.get_level_values("STRIKE").values
        below, above = strikes[strikes < l.strike], strikes[strikes > l.strike]
        rec["listed_below"] = below.max() if len(below) else np.nan
        rec["listed_above"] = above.min() if len(above) else np.nan
        k = l.strike
        if l.strike not in strikes:
            cands = [x for x in (rec["listed_below"], rec["listed_above"]) if np.isfinite(x)]
            nearest = min(cands, key=lambda x: abs(x - l.strike)) if cands else np.nan
            if substitute is not None and np.isfinite(nearest) and abs(nearest - l.strike) <= substitute:
                k, rec["substituted"] = nearest, True
            else:
                rec["cause"] = (f"strike {l.strike:.0f} not listed (chain of {rec['chain_rows']} strikes; nearest "
                                f"{rec['listed_below']:.0f} / {rec['listed_above']:.0f})")
                out.append(rec)
                continue
        r = idx.loc[(l.date, label, k)]
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        s = l.right
        rec.update(obs_strike=k, synth_mid_obs_strike=reprice(l, k, cfg, q) if rec["substituted"] else l.synth_mid,
                   bid=r[f"{s}_BID"], ask=r[f"{s}_ASK"], last=r[f"{s}_LAST"], size=r[f"{s}_SIZE"], volume=r[f"{s}_VOLUME"],
                   iv=r[f"{s}_IV"], delta=r[f"{s}_DELTA"], u_last=r["UNDERLYING_LAST"])
        if not np.isfinite(rec["bid"]) or not np.isfinite(rec["ask"]):
            rec["cause"] = "row present but bid/ask blank in the vendor file"
        out.append(rec)
    j = pd.DataFrame(out)
    j["found"] = j.bid.notna() & j.ask.notna()
    j["obs_mid"] = (j.bid + j.ask) / 2
    j["half_spread"] = (j.ask - j.bid) / 2
    j["zero_bid"] = j.found & (j.bid <= 0)
    j["moneyness_pct"] = 100 * (j.strike / j.spot - 1)
    return j


def coverage_report(j: pd.DataFrame, substitute: float | None) -> str:
    n, f = len(j), int(j.found.sum())
    lines = [f"# Join coverage — brief 002 Part 2", "",
             f"Cycles: {j.cycle.nunique()} (entry >= {WINDOW[0]}, exit <= {WINDOW[1]}); legs expected {n}, joined {f} "
             f"(**{100 * f / n:.1f} %**), missing {n - f}. Gate: >= 90 %.",
             f"Strike substitution: {'off' if substitute is None else f'nearest listed strike within {substitute:g} pts'}"
             + (f"; substituted legs {int(j.substituted.sum())}" if substitute is not None else "") + ".", ""]
    def tbl(title, s):
        lines.extend([f"## {title}", "", "| | joined % |", "|---|---|"] + [f"| {k} | {100 * v:.1f} |" for k, v in s.items()] + [""])
    tbl("By date type", j.groupby("when").found.mean())
    tbl("By leg", j.groupby("leg").found.mean())
    tbl("By year", j.groupby(j.date.dt.year).found.mean())
    full = j.groupby("cycle").found.all()
    lines += [f"Cycles with all 8 legs joined: {int(full.sum())} of {full.size}; all 4 entry legs: "
              f"{int(j[j.when == 'entry'].groupby('cycle').found.all().sum())}; all 4 exit legs: "
              f"{int(j[j.when == 'exit'].groupby('cycle').found.all().sum())}.", "",
              "## Missing legs by cause", "", "| cause | legs |", "|---|---|"]
    cause = j[~j.found].cause.str.replace(r"strike \d+ not listed.*", "engine strike not listed on the vendor chain", regex=True) \
                          .str.replace(r"no chain labelled.*", "no chain for the expiry", regex=True)
    lines += [f"| {k} | {v} |" for k, v in cause.value_counts().items()]
    m = j[(~j.found) & j.cause.str.startswith("strike")]
    if len(m):
        dist = np.minimum((m.strike - m.listed_below).abs(), (m.listed_above - m.strike).abs())
        lines += ["", "Distance from the engine strike to the nearest listed strike (unlisted-strike legs): "
                  + ", ".join(f"{int(k)} pts: {v}" for k, v in dist.value_counts().sort_index().items()) + ".",
                  f"Label offset used on joined legs: exact date {int((j.found & (j.label_offset == 0)).sum())}, "
                  f"previous day {int((j.found & (j.label_offset == 1)).sum())}. Zero-bid joined legs: {int(j.zero_bid.sum())}."]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--substitute-strikes", type=float, default=None, metavar="PTS")
    ap.add_argument("--refresh-extract", action="store_true")
    a = ap.parse_args()
    DERIVED.mkdir(parents=True, exist_ok=True)
    cycles = cycles_in_window()
    dates = needed_dates(cycles)
    print(f"cycles {len(cycles)}, quote dates requested {len(dates)}")
    ex, _ = extract(dates, a.refresh_extract)
    print(f"extract rows {len(ex)} on {ex.QUOTE_DATE.nunique()} dates")
    legs, (cfg, _) = synthetic_legs(cycles)
    print(f"synthetic legs {len(legs)} — reproduce trades.csv exactly")
    j = join(legs, ex, cfg, a.substitute_strikes)
    j.to_csv(DERIVED / "legs_joined.csv", index=False, float_format="%.6f")
    miss = j[~j.found][["cycle", "when", "date", "expiry", "leg", "strike", "moneyness_pct", "spot", "label", "chain_rows",
                        "listed_below", "listed_above", "cause"]]
    miss.to_csv(DERIVED / "missing_legs.csv", index=False, float_format="%.2f")
    rep = coverage_report(j, a.substitute_strikes)
    (DERIVED / "join_coverage.md").write_text(rep)
    print(rep)


if __name__ == "__main__":
    main()
