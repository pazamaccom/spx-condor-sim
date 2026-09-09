"""Daily data: ^GSPC OHLC, ^VIX, ^VIX3M, ^VIX9D (yfinance, Cboe fallback), DTB3 (FRED).

Everything is cached under data/cache/ as CSV. Use refresh=True to re-download.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from .config import REPO_ROOT, Config

CACHE_DIR = REPO_ROOT / "data" / "cache"
CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{name}.csv"


def _yf_ohlc(ticker: str, start: str) -> pd.DataFrame:
    df = yf.download(ticker, start=start, auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    return df.dropna(subset=["close"])


def _cboe_close(sym: str) -> pd.Series:
    """Cboe published history (CLOSE column). Returns empty series on failure."""
    try:
        r = requests.get(CBOE_URL.format(sym=sym), timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip().upper() for c in df.columns]
        df["DATE"] = pd.to_datetime(df["DATE"])
        s = df.set_index("DATE")["CLOSE"].astype(float)
        s.index.name = "date"
        return s.sort_index()
    except Exception:  # noqa: BLE001 — optional source
        return pd.Series(dtype=float, name="close")


def _vol_index(ticker: str, cboe_sym: str, start: str) -> pd.Series:
    """Close of a Cboe vol index: yfinance primary, Cboe CSV to fill gaps."""
    yfs = _yf_ohlc(ticker, start)["close"]
    cb = _cboe_close(cboe_sym)
    cb = cb[cb.index >= pd.Timestamp(start)]
    combined = yfs.combine_first(cb) if len(cb) else yfs
    return combined.sort_index().rename(ticker.strip("^").lower())


def _fred(series: str) -> pd.Series:
    r = requests.get(FRED_URL.format(series=series), timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", series]
    df["date"] = pd.to_datetime(df["date"])
    s = pd.to_numeric(df.set_index("date")[series], errors="coerce")
    s.index.name = "date"
    return s


def _load_or_fetch(name: str, fetch, refresh: bool) -> pd.DataFrame | pd.Series:
    p = _cache_path(name)
    if p.exists() and not refresh:
        df = pd.read_csv(p, index_col=0, parse_dates=True)
        df.index.name = "date"
        return df.iloc[:, 0] if df.shape[1] == 1 else df
    obj = fetch()
    obj.to_csv(p)
    return obj


def discount_to_cc(dtb3_pct: pd.Series, days: int = 91) -> pd.Series:
    """DTB3 is a bank-discount-basis rate (percent, actual/360). Convert to a
    continuously-compounded annual rate (actual/365):
        price  = 1 - d * days/360
        r_cc   = -ln(price) / (days/365)
    """
    d = dtb3_pct / 100.0
    price = (1.0 - d * days / 360.0).clip(lower=1e-6)
    return -np.log(price) / (days / 365.0)


def load_market_data(cfg: Config, refresh: bool = False) -> pd.DataFrame:
    """One row per ^GSPC trading day.

    Columns: open, high, low, close, vix, vix3m, vix9d, dtb3 (pct), r (cc, decimal).
    vix/vix3m/vix9d are NaN where the index did not yet exist (no forward-fill
    across the start of a series). dtb3 is forward-filled onto trading days.
    """
    d = cfg.data
    start = d["start"]
    spx = _load_or_fetch("gspc", lambda: _yf_ohlc(d["index"], start), refresh)
    vix = _load_or_fetch("vix", lambda: _vol_index(d["vix"], "VIX", start), refresh)
    vix3m = _load_or_fetch("vix3m", lambda: _vol_index(d["vix3m"], "VIX3M", start), refresh)
    vix9d = _load_or_fetch("vix9d", lambda: _vol_index(d["vix9d"], "VIX9D", start), refresh)
    dtb3 = _load_or_fetch("dtb3", lambda: _fred(d["riskfree_fred"]), refresh)

    df = spx.copy()
    df["vix"] = vix.reindex(df.index)
    df["vix3m"] = vix3m.reindex(df.index)
    df["vix9d"] = vix9d.reindex(df.index)
    # Vol indices: fill isolated holidays/gaps by ffill, but only after series start.
    for col in ("vix", "vix3m", "vix9d"):
        first = df[col].first_valid_index()
        if first is not None:
            df.loc[first:, col] = df.loc[first:, col].ffill()
    # DTB3: FRED has a few blank days; ffill onto trading calendar.
    dtb3_full = dtb3.reindex(df.index.union(dtb3.index)).ffill()
    df["dtb3"] = dtb3_full.reindex(df.index)
    df["r"] = discount_to_cc(df["dtb3"])
    return df
