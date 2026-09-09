"""Iron-condor cycle engine. One pass over the daily trading calendar.

Rules implemented exactly as in docs/briefs/001-stage1-backtester.md and
config.yaml. See summary.md "Assumptions" for the interpretive choices.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .calendar_utils import monthly_expiries
from .config import Config
from .pricing import condor_leg_mids, condor_net

INPUT_COLS = ["open", "high", "low", "close", "vix", "vix3m", "vix9d", "dtb3", "r"]


@dataclass
class RunOptions:
    variant: str = "A"          # "A" fixed contracts, "B" risk-fraction sizing
    filter_on: bool = True      # VIX > VIX3M entry filter
    lag_days: int = 0           # shift all inputs by N trading days (acceptance test A4)
    sim_start: str = "2005-01-01"


@dataclass
class Position:
    entry_date: pd.Timestamp
    expiry: pd.Timestamp
    nominal_expiry: pd.Timestamp
    entry_spot: float
    entry_dte: int
    sigma_h: float
    rv21: float
    rv63: float
    vix_entry: float
    vix3m_entry: float
    strikes: dict[str, float]
    width: float
    credit_mid: float
    credit_net: float
    contracts: int
    equity_at_entry: float
    mae_usd: float = 0.0
    mfe_usd: float = 0.0
    put_touch: bool = False
    call_touch: bool = False
    min_low: float = math.inf
    max_high: float = -math.inf
    days_held: int = 0
    vol_floor_hits: int = 0
    same_expiry_reentry: bool = False


@dataclass
class RunResult:
    trades: pd.DataFrame
    daily: pd.DataFrame
    monthly: pd.DataFrame
    diagnostics: dict = field(default_factory=dict)


def round_to_grid(x: float, grid: float) -> float:
    return float(round(x / grid) * grid)


def realised_vol(close: pd.Series, window: int) -> pd.Series:
    lr = np.log(close).diff()
    return lr.rolling(window).std(ddof=1) * math.sqrt(252.0)


def prepare_inputs(market: pd.DataFrame, opts: RunOptions) -> pd.DataFrame:
    df = market.copy()
    if opts.lag_days:
        df[INPUT_COLS] = df[INPUT_COLS].shift(opts.lag_days)
    df["rv21"] = realised_vol(df["close"], 21)
    df["rv63"] = realised_vol(df["close"], 63)
    df["filter_active"] = df["vix"] > df["vix3m"]  # NaN vix3m -> False
    return df


def select_strikes(spot: float, sigma_h: float, cfg: Config) -> tuple[dict[str, float], float]:
    s = cfg.strikes
    grid = s["strike_grid"]
    short_put = round_to_grid(spot * (1.0 - s["put_sigma_mult"] * sigma_h), grid)
    short_call = round_to_grid(spot * (1.0 + s["call_sigma_mult"] * sigma_h), grid)
    width_raw = s["width_points"] if spot >= 6000 else s["width_pct_below_6000"] * spot
    width = max(round_to_grid(width_raw, grid), grid)
    strikes = {
        "long_put": short_put - width,
        "short_put": short_put,
        "short_call": short_call,
        "long_call": short_call + width,
    }
    return strikes, width


def run_backtest(market: pd.DataFrame, cfg: Config, opts: RunOptions) -> RunResult:
    p, e, x, z, f = cfg.pricing, cfg.entry, cfg.exit, cfg.sizing, cfg.filter
    mult = p["multiplier"]
    ba = p["bid_ask_per_leg_points"]
    comm = p["commission_per_leg_contract_usd"]
    q = cfg.data["dividend_yield"]
    put_skew, call_skew = p["put_skew_per_pct_otm"], p["call_skew_per_pct_otm"]
    book = float(z["book_usd"])
    earn_cash = bool(cfg.cash["earn_riskfree_on_idle"])

    df = prepare_inputs(market, opts)
    sim = df[df.index >= pd.Timestamp(opts.sim_start)]
    sim = sim.dropna(subset=["close", "vix", "r", "rv63"])
    exp_tbl = monthly_expiries(df.index, sim.index[0], sim.index[-1] + pd.Timedelta(days=60))
    expiries = exp_tbl["expiry"].tolist()
    nominal_of = dict(zip(exp_tbl["expiry"], exp_tbl["nominal"]))

    cash = book
    pos: Position | None = None
    last_expiry_traded: pd.Timestamp | None = None
    trades: list[dict] = []
    daily: list[dict] = []
    diag = {
        "entries_blocked_by_filter_days": 0,
        "expiries_skipped_filter": 0,
        "entries_skipped_nonpositive_credit": 0,
        "entries_skipped_zero_contracts": 0,
        "expiry_settlements": 0,
        "vol_floor_hits": 0,
        "same_expiry_reentries": 0,
        "first_vix3m_date": str(df["vix3m"].first_valid_index().date()) if df["vix3m"].notna().any() else None,
    }
    blocked_expiries: set = set()

    prev_date: pd.Timestamp | None = None
    prev_r = float(sim["r"].iloc[0])
    interest_today = 0.0

    for date, row in sim.iterrows():
        spot = float(row["close"])
        vix, vix3m, r = float(row["vix"]), float(row["vix3m"]), float(row["r"])
        # 1. cash accrues at DTB3 (cc rate known at the previous close) for calendar days elapsed
        interest_today = 0.0
        if earn_cash and prev_date is not None:
            cal_days = (date - prev_date).days
            interest_today = cash * (math.exp(prev_r * cal_days / 365.0) - 1.0)
            cash += interest_today
        prev_date, prev_r = date, r

        realised_today = 0.0
        mark = 0.0
        exit_reason = None

        # 2. manage open position at this close
        if pos is not None:
            dte = (pos.expiry - date).days
            n = pos.contracts
            pos.days_held += 1
            pos.min_low = min(pos.min_low, float(row["low"]))
            pos.max_high = max(pos.max_high, float(row["high"]))
            if float(row["low"]) < pos.strikes["short_put"]:
                pos.put_touch = True
            if float(row["high"]) > pos.strikes["short_call"]:
                pos.call_touch = True

            if dte <= 0:
                # guard: settle at intrinsic (cash settled, no spread, no exit commission)
                mids, _ = condor_leg_mids(spot, pos.strikes, 0, r, q, vix, vix3m, put_skew, call_skew)
                debit_net = condor_net(mids)
                pnl = (pos.credit_net - debit_net) * mult * n - 4 * comm * n
                cash -= debit_net * mult * n
                exit_reason = "expiry_settlement"
                diag["expiry_settlements"] += 1
            else:
                mids, fh = condor_leg_mids(spot, pos.strikes, dte, r, q, vix, vix3m, put_skew, call_skew)
                pos.vol_floor_hits += int(fh)
                debit_net = condor_net(mids) + 4 * ba
                unreal = (pos.credit_net - debit_net) * mult * n
                pos.mae_usd = min(pos.mae_usd, unreal)
                pos.mfe_usd = max(pos.mfe_usd, unreal)
                captured = (pos.credit_net - debit_net) / pos.credit_net
                if captured >= x["profit_take_fraction"]:
                    exit_reason = "profit_target"
                elif dte <= x["dte_exit"]:
                    exit_reason = "dte_exit"
                if exit_reason:
                    pnl = unreal - 8 * comm * n
                    cash -= debit_net * mult * n + 4 * comm * n
                else:
                    mark = -debit_net * mult * n

            if exit_reason:
                realised_today = pnl
                diag["vol_floor_hits"] += pos.vol_floor_hits
                sp, sc = pos.strikes["short_put"], pos.strikes["short_call"]
                trades.append({
                    "entry_date": pos.entry_date.date(), "expiry": pos.expiry.date(),
                    "nominal_expiry": pos.nominal_expiry.date(),
                    "entry_spot": pos.entry_spot, "entry_dte": pos.entry_dte,
                    "sigma_h": pos.sigma_h, "rv21": pos.rv21, "rv63": pos.rv63,
                    "vix_entry": pos.vix_entry, "vix3m_entry": pos.vix3m_entry,
                    "long_put": pos.strikes["long_put"], "short_put": sp,
                    "short_call": sc, "long_call": pos.strikes["long_call"],
                    "width": pos.width, "credit_mid": pos.credit_mid, "credit_net": pos.credit_net,
                    "credit_usd": pos.credit_net * mult * pos.contracts,
                    "max_loss_usd": (pos.width - pos.credit_net) * mult * pos.contracts,
                    "contracts": pos.contracts, "equity_at_entry": pos.equity_at_entry,
                    "exit_date": date.date(), "exit_dte": dte, "exit_spot": spot,
                    "exit_debit_net": debit_net, "exit_reason": exit_reason,
                    "days_held": pos.days_held, "pnl_usd": pnl,
                    "mae_usd": pos.mae_usd, "mfe_usd": pos.mfe_usd,
                    "min_low": pos.min_low, "max_high": pos.max_high,
                    "put_touch": pos.put_touch, "call_touch": pos.call_touch,
                    "put_finish": spot < sp, "call_finish": spot > sc,
                    "same_expiry_reentry": pos.same_expiry_reentry,
                })
                pos = None

        # 3. entry at this close if flat
        if pos is None:
            cands = [ex for ex in expiries if e["dte_min"] <= (ex - date).days <= e["dte_max"]]
            if cands:
                expiry = min(cands)
                dte = (expiry - date).days
                if opts.filter_on and bool(row["filter_active"]):
                    diag["entries_blocked_by_filter_days"] += 1
                    blocked_expiries.add(expiry)
                else:
                    rv21, rv63 = float(row["rv21"]), float(row["rv63"])
                    sigma_ann = max(rv21, rv63, vix / 100.0)
                    sigma_h = sigma_ann * math.sqrt(dte / 365.0)
                    strikes, width = select_strikes(spot, sigma_h, cfg)
                    mids, fh = condor_leg_mids(spot, strikes, dte, r, q, vix, vix3m, put_skew, call_skew)
                    credit_mid = condor_net(mids)
                    credit_net = credit_mid - 4 * ba
                    if credit_net <= 0:
                        diag["entries_skipped_nonpositive_credit"] += 1
                    else:
                        equity_now = cash
                        if opts.variant.upper() == "A":
                            n = int(z["variant_a_contracts"])
                        else:
                            max_loss = (width - credit_net) * mult
                            n = int(math.floor(z["variant_b_risk_fraction"] * equity_now / max_loss))
                        if n <= 0:
                            diag["entries_skipped_zero_contracts"] += 1
                        else:
                            cash += credit_net * mult * n - 4 * comm * n
                            reentry = last_expiry_traded == expiry
                            diag["same_expiry_reentries"] += int(reentry)
                            pos = Position(
                                entry_date=date, expiry=expiry, nominal_expiry=nominal_of[expiry],
                                entry_spot=spot, entry_dte=dte, sigma_h=sigma_h, rv21=rv21, rv63=rv63,
                                vix_entry=vix, vix3m_entry=vix3m, strikes=strikes, width=width,
                                credit_mid=credit_mid, credit_net=credit_net, contracts=n,
                                equity_at_entry=equity_now, vol_floor_hits=int(fh),
                                same_expiry_reentry=reentry,
                            )
                            last_expiry_traded = expiry
                            # cost to close immediately = mid + 4*ba
                            mark = -(credit_mid + 4 * ba) * mult * n

        daily.append({
            "date": date, "spot": spot, "vix": vix, "vix3m": vix3m, "r": r,
            "cash": cash, "mark": mark, "equity": cash + mark,
            "interest": interest_today, "realised_pnl": realised_today,
            "position_open": pos is not None, "filter_active": bool(row["filter_active"]),
        })

    diag["expiries_skipped_filter"] = sum(
        1 for ex in blocked_expiries if ex not in {t["expiry"] for t in trades} and (pos is None or ex != pos.expiry)
    )
    if pos is not None:
        diag["open_position_at_end"] = {
            "entry_date": str(pos.entry_date.date()), "expiry": str(pos.expiry.date()),
            "contracts": pos.contracts, "credit_net": pos.credit_net,
        }

    trades_df = pd.DataFrame(trades)
    daily_df = pd.DataFrame(daily).set_index("date")
    monthly_df = build_monthly(daily_df, book)
    diag["n_trades"] = len(trades_df)
    diag["sim_start"] = str(sim.index[0].date())
    diag["sim_end"] = str(sim.index[-1].date())
    return RunResult(trades=trades_df, daily=daily_df, monthly=monthly_df, diagnostics=diag)


def build_monthly(daily: pd.DataFrame, book: float) -> pd.DataFrame:
    g = daily.groupby(daily.index.to_period("M"))
    m = pd.DataFrame({
        "month_end": g.apply(lambda d: d.index[-1].date()),
        "equity": g["equity"].last(),
        "cash": g["cash"].last(),
        "open_mark": g["mark"].last(),
        "cash_pnl": g["interest"].sum(),
        "realised_premium_pnl": g["realised_pnl"].sum(),
        "filter_active_days": g["filter_active"].sum(),
        "trading_days": g["equity"].count(),
    })
    prev_equity = m["equity"].shift(1).fillna(book)
    m["total_pnl"] = m["equity"] - prev_equity
    m["premium_pnl"] = m["total_pnl"] - m["cash_pnl"]
    m["total_return"] = m["total_pnl"] / prev_equity
    m.index = m.index.astype(str)
    m.index.name = "month"
    return m
