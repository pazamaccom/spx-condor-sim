"""Black-Scholes on the index with a fixed linear skew and VIX/VIX3M term scaling."""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm

VOL_FLOOR = 0.01  # 1 vol point: keeps BS well-defined; binding count is reported
VOL_CAP = 3.00


def bs_price(kind: str, S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    """European option on an index paying continuous dividend yield q. T in years."""
    if T <= 0.0:
        return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
    sig_sqrt_t = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / sig_sqrt_t
    d2 = d1 - sig_sqrt_t
    if kind == "call":
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def atm_vol_for_tenor(vix: float, vix3m: float, days: float) -> tuple[float, bool]:
    """ATM vol for `days` calendar days to expiry.

    VIX is the 30-day ATM vol, VIX3M the 90-day. Total variance is linear in
    calendar time between the two points, extrapolated linearly outside
    [30, 90]. If VIX3M is unavailable the term structure is flat at VIX.
    Returns (vol, floor_hit)."""
    v30 = vix / 100.0
    if vix3m is None or not np.isfinite(vix3m):
        return max(v30, VOL_FLOOR), v30 < VOL_FLOOR
    v90 = vix3m / 100.0
    w30 = v30 * v30 * 30.0
    w90 = v90 * v90 * 90.0
    w = w30 + (w90 - w30) * (days - 30.0) / 60.0
    floor_w = VOL_FLOOR * VOL_FLOOR * days
    if w < floor_w:
        return VOL_FLOOR, True
    return math.sqrt(w / days), False


def strike_vol(atm: float, spot: float, strike: float, put_skew: float, call_skew: float) -> float:
    """One smile in strike space (put-call parity consistent). Moneyness
    m = (K/S - 1) * 100 in percent. Strikes below spot use the put slope
    (+put_skew vol points per 1% OTM), strikes above spot use the call slope
    (call_skew vol points per 1% OTM, negative = vol falls with strike)."""
    m = (strike / spot - 1.0) * 100.0
    if m < 0:
        v = atm + put_skew * (-m) / 100.0
    else:
        v = atm + call_skew * m / 100.0
    return min(max(v, VOL_FLOOR), VOL_CAP)


def condor_leg_mids(
    spot: float, strikes: dict[str, float], days: float, r: float, q: float,
    vix: float, vix3m: float, put_skew: float, call_skew: float,
) -> tuple[dict[str, float], bool]:
    """Mid prices of the four legs at a daily close. strikes keys:
    long_put, short_put, short_call, long_call. Returns (mids, vol_floor_hit)."""
    T = days / 365.0
    atm, floor_hit = atm_vol_for_tenor(vix, vix3m, days) if days > 0 else (0.0, False)
    mids = {}
    for leg, K in strikes.items():
        kind = "put" if "put" in leg else "call"
        sig = strike_vol(atm, spot, K, put_skew, call_skew) if days > 0 else 0.0
        mids[leg] = bs_price(kind, spot, K, T, r, q, sig)
    return mids, floor_hit


def condor_net(mids: dict[str, float]) -> float:
    """Net value of the short condor in index points (positive = credit)."""
    return mids["short_put"] + mids["short_call"] - mids["long_put"] - mids["long_call"]
