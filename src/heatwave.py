"""
Heat-wave onset detection, leakage-safe.

A heat wave here is a run of >= `min_run_days` consecutive warm-season
days whose daily-maximum hazard (WBGT or 2 m temperature) is at or above a
percentile threshold, where that threshold for evaluation year Y is
computed from warm-season days in years strictly before Y. Onset is the
first day of such a run whose immediately preceding day was below the
threshold, so onsets mark the transition into a heat wave rather than
every day inside one.

Used by scripts/aiwp_humid_heat_study.py to define the pre-onset window
over which forecast bias is measured, the analogue of the pre-heat-wave
cold bias reported by arXiv 2504.21195.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def daily_max(
    df: pd.DataFrame,
    value_col: str,
    *,
    time_col: str = "time",
    tz: str = "Asia/Qatar",
    months: tuple[int, ...] = (5, 6, 7, 8, 9),
    hours: tuple[int, int] = (7, 18),
) -> pd.Series:
    """Daily maximum of `value_col` over warm-season daylight hours,
    indexed by local calendar date. Days with no qualifying hour are
    dropped."""
    t = pd.to_datetime(df[time_col], utc=True).dt.tz_convert(tz)
    lo, hi = hours
    keep = t.dt.month.isin(months) & t.dt.hour.between(lo, hi)
    local_date = t.dt.date
    s = pd.Series(df.loc[keep, value_col].to_numpy(),
                  index=pd.Index(local_date[keep], name="date"))
    return s.groupby(level=0).max().sort_index()


def prior_years_threshold(
    dmax: pd.Series,
    year: int,
    *,
    percentile: float = 90.0,
) -> float:
    """`percentile` of daily-max values over days in years strictly before
    `year`. NaN if there is no prior data."""
    idx = pd.DatetimeIndex(dmax.index)
    prior = dmax[idx.year < year]
    if prior.empty:
        return float("nan")
    return float(np.percentile(prior.to_numpy(), percentile))


def heatwave_onsets(
    dmax: pd.Series,
    *,
    percentile: float = 90.0,
    min_run_days: int = 2,
) -> list[pd.Timestamp]:
    """Onset dates across every year present in `dmax`, each year scored
    against a threshold from its own prior years. A year with no prior data
    contributes no onsets.

    An onset is day i where days i .. i+min_run_days-1 are all >= threshold,
    day i-1 exists and is < threshold, and all days in the run are
    consecutive calendar days (no gap)."""
    dmax = dmax.sort_index()
    dates = pd.DatetimeIndex(dmax.index)
    vals = dmax.to_numpy(dtype=float)
    onsets: list[pd.Timestamp] = []

    for year in sorted({d.year for d in dates}):
        thr = prior_years_threshold(dmax, year, percentile=percentile)
        if np.isnan(thr):
            continue
        yr_mask = dates.year == year
        yr_dates = dates[yr_mask]
        yr_vals = vals[yr_mask]
        hot = yr_vals >= thr
        n = len(yr_dates)
        for i in range(n - min_run_days + 1):
            run = slice(i, i + min_run_days)
            if not hot[run].all():
                continue
            # consecutive calendar days within the run
            span = (yr_dates[i + min_run_days - 1] - yr_dates[i]).days
            if span != min_run_days - 1:
                continue
            # transition: the day before exists and is below threshold
            if i == 0:
                continue
            if (yr_dates[i] - yr_dates[i - 1]).days != 1 or hot[i - 1]:
                continue
            onsets.append(pd.Timestamp(yr_dates[i]))
    return onsets


def preonset_date_ranges(
    onsets: list[pd.Timestamp],
    window_days: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """[onset - window_days, onset - 1] inclusive, one per onset."""
    return [(o - pd.Timedelta(days=window_days), o - pd.Timedelta(days=1))
            for o in onsets]


def preonset_mask(
    times_utc: pd.Series | pd.DatetimeIndex,
    onsets: list[pd.Timestamp],
    window_days: int,
    *,
    tz: str = "Asia/Qatar",
) -> np.ndarray:
    """Boolean mask over `times_utc`: True where the local date falls in
    any [onset - window_days, onset - 1]."""
    t = pd.to_datetime(pd.Series(times_utc), utc=True).dt.tz_convert(tz)
    d = pd.to_datetime(t.dt.date)
    out = np.zeros(len(d), dtype=bool)
    for lo, hi in preonset_date_ranges(onsets, window_days):
        out |= (d >= lo) & (d <= hi)
    return out
