"""Monthly expiry calendar: third Friday of each month, shifted to the preceding
trading day when the third Friday is an exchange holiday (e.g. Good Friday)."""
from __future__ import annotations

import pandas as pd


def third_friday(year: int, month: int) -> pd.Timestamp:
    first = pd.Timestamp(year=year, month=month, day=1)
    # weekday(): Mon=0 ... Fri=4
    offset = (4 - first.weekday()) % 7
    return first + pd.Timedelta(days=offset + 14)


def monthly_expiries(trading_days: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Return DataFrame with columns nominal (3rd Friday) and expiry (actual
    trading day: same day if the exchange is open, else the previous trading day).
    Only expiries inside [start, end] of the trading calendar are considered
    resolvable; a nominal date beyond the last trading day is left as nominal."""
    rows = []
    td = pd.DatetimeIndex(sorted(trading_days))
    cur = pd.Timestamp(year=start.year, month=start.month, day=1)
    while cur <= end:
        nominal = third_friday(cur.year, cur.month)
        if nominal > td[-1]:
            actual = nominal  # future expiry, calendar unknown
        elif nominal in td:
            actual = nominal
        else:
            actual = td[td < nominal][-1]
        rows.append({"nominal": nominal, "expiry": actual})
        cur = cur + pd.offsets.MonthBegin(1)
    return pd.DataFrame(rows)
