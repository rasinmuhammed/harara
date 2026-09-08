"""
Predictive distributions for hourly WBGT used by the scheduler. Both
classes share the interface `scenarios(...) -> (S, H) array`.

AnalogResidualModel: analog residual resampling of a single-member
forecast archive. For a target day it takes the K past days (strictly
earlier, same season, closest daytime-mean forecast) and reuses their
hourly residual trajectories (observation minus forecast). It makes no
distributional assumption and preserves the diurnal error structure. This
is the fallback when no ensemble is available.

GEFSEnsembleModel: a lagged ensemble from the NOAA GEFS v12 reforecast
(scripts/fetch_gefs_reforecast.py). For a working day it pools the members
of the 00Z inits from D-1, D-2 and D-3 (forecast days +1, +2, +3), each
(init, member) an independent trajectory, and interpolates each onto the
working-hour grid. With an EMOS model attached it recalibrates the
scenarios by ensemble copula coupling.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd


class AnalogResidualModel:
    def __init__(self, hours_grid: np.ndarray):
        self.hours = np.asarray(hours_grid)          # local-hour grid, length H
        self._days = []                              # list of dict(date, month, fc_mean, resid[H])

    def fit(self, day_table: pd.DataFrame):
        """
        day_table: one row per past day with columns
          date (datetime64), month (int),
          fc_<h> for each grid hour  (forecast WBGT),
          resid_<h> for each grid hour (true - forecast).
        Only fully-observed days are kept.
        """
        rcols = [f"resid_{h}" for h in self.hours]
        fcols = [f"fc_{h}" for h in self.hours]
        for _, r in day_table.iterrows():
            resid = r[rcols].to_numpy(dtype=float)
            fc = r[fcols].to_numpy(dtype=float)
            if np.isnan(resid).any() or np.isnan(fc).any():
                continue
            self._days.append(dict(date=r["date"], month=int(r["month"]),
                                   fc_mean=float(np.nanmean(fc)), resid=resid))
        self._days.sort(key=lambda d: d["date"])
        return self

    def scenarios(self, before_date, target_month: int, forecast_hourly: np.ndarray,
                  k: int = 100, month_window: int = 1) -> np.ndarray:
        """K analog scenarios of hourly WBGT for a day being scheduled."""
        f_mean = float(np.nanmean(forecast_hourly))
        pool = [d for d in self._days
                if d["date"] < np.datetime64(before_date)
                and abs(((d["month"] - target_month + 6) % 12) - 6) <= month_window]
        if len(pool) < 10:
            pool = [d for d in self._days if d["date"] < np.datetime64(before_date)]
        if not pool:
            return forecast_hourly[None, :].copy()
        pool.sort(key=lambda d: abs(d["fc_mean"] - f_mean))
        chosen = pool[:min(k, len(pool))]
        R = np.vstack([d["resid"] for d in chosen])          # (k, H)
        return forecast_hourly[None, :] + R                  # (k, H) scenarios


class GEFSEnsembleModel:
    """
    Lagged ensemble of hourly WBGT for a working day, from the GEFS v12
    reforecast point store (data/gefs/*.parquet, scripts/fetch_gefs_reforecast.py).

    scenarios(valid_date, hours_grid, fday=None) -> (S, H) WBGT.
      Each row is one (00Z init, member) trajectory: the daytime GEFS
      points (leads 33/36/39 h for forecast day +1, +57.. for +2,
      +81.. for +3), interpolated onto `hours_grid` (local hour), with a
      mild morning ramp below 12:00 and an evening ramp above 18:00.
      `fday` restricts to one forecast-day's members (single-init
      ensemble); default pools all available inits (lagged ensemble).

    If an `emos` model (src.emos.EMOS) is supplied, the raw member
    trajectories are recalibrated by Ensemble Copula Coupling: each hour's
    marginal is replaced by the EMOS Normal(mu, sigma) evaluated at the
    raw members' ranks, so the diurnal rank structure the scheduler's
    peak-load objective depends on is preserved while the marginals are
    made honest.
    """

    def __init__(self, source, lat=25.27, lon=51.61, emos=None):
        from scripts.fetch_gefs_reforecast import compute_gefs_wbgt, load_gefs

        if isinstance(source, pd.DataFrame):
            df = source.copy()
        elif pathlib.Path(str(source)).is_dir():
            df = load_gefs(source)
        elif str(source).endswith(".parquet"):
            df = pd.read_parquet(source)
        else:
            df = pd.read_csv(source)
        for c in ("init_time", "valid_time"):
            df[c] = pd.to_datetime(df[c])
        if "pressure_hpa" not in df:
            df["pressure_hpa"] = 1000.0

        df["wbgt"], _ = compute_gefs_wbgt(df, lat, lon)
        df["local"] = df["valid_time"] + pd.Timedelta(hours=3)   # Doha UTC+3
        df["vdate"] = df["local"].dt.date
        df["lhour"] = df["local"].dt.hour + df["local"].dt.minute / 60.0
        df["month"] = df["local"].dt.month
        self.df = df
        self.emos = emos

    # --------------------------------------------------------------
    def _raw_member_trajs(self, valid_date, hg, fday):
        sub = self.df[self.df["vdate"] == pd.Timestamp(valid_date).date()]
        if fday is not None:
            sub = sub[sub["fday"] == fday]
        rows, leadmap = [], None
        for _, g in sub.groupby(["init_time", "member"]):
            g = g.sort_values("lhour")
            if len(g) < 2:
                continue
            lh, wb = g["lhour"].to_numpy(), g["wbgt"].to_numpy()
            traj = np.interp(hg, lh, wb)
            traj[hg < lh[0]] = wb[0] - 0.5 * (lh[0] - hg[hg < lh[0]])
            traj[hg > lh[-1]] = wb[-1] - 0.6 * (hg[hg > lh[-1]] - lh[-1])
            rows.append(traj)
            if leadmap is None:
                # local-hour -> GEFS lead for this fday (nearest of 12/15/18)
                base = 24 * int(g["fday"].iloc[0])
                pts = np.array([base + 9, base + 12, base + 15])   # 33/36/39 style
                loc = np.array([12.0, 15.0, 18.0])
                leadmap = pts[np.abs(hg[:, None] - loc[None, :]).argmin(1)]
        if not rows:
            return np.empty((0, len(hg))), None, sub
        return np.vstack(rows), leadmap, sub

    def scenarios(self, valid_date, hours_grid, fday=None) -> np.ndarray:
        hg = np.asarray(hours_grid, dtype=float)
        E, leadmap, sub = self._raw_member_trajs(valid_date, hg, fday)
        if E.shape[0] == 0 or self.emos is None:
            return E
        month = int(pd.Timestamp(valid_date).month)
        S = E.shape[0]
        from scipy.stats import norm
        out = np.empty_like(E)
        for j in range(E.shape[1]):
            col = E[:, j]
            mu, sig = self.emos.predict(np.array([col.mean()]),
                                        np.array([col.var(ddof=1) if S > 1 else 0.25]),
                                        int(leadmap[j]), month)
            ranks = col.argsort().argsort()               # 0..S-1
            out[:, j] = np.ravel(mu)[0] + np.ravel(sig)[0] * norm.ppf((ranks + 0.5) / S)
        return out
