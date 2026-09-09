"""
Heat-wave onset: threshold from strictly prior years, onset only on a
below->above transition into a run of >= min_run_days consecutive days,
no onset without a preceding day, gaps in a run break it.
"""

import numpy as np
import pandas as pd
import pytest

from src.heatwave import (
    daily_max, heatwave_onsets, preonset_mask, prior_years_threshold,
)


def _daily(year_vals: dict[int, list[float]], start_md=(5, 1)) -> pd.Series:
    """Build a daily series: {year: [day1, day2, ...]} starting at start_md."""
    idx, vals = [], []
    for yr, seq in year_vals.items():
        d0 = pd.Timestamp(yr, *start_md)
        for k, v in enumerate(seq):
            idx.append(d0 + pd.Timedelta(days=k))
            vals.append(v)
    return pd.Series(vals, index=pd.DatetimeIndex(idx)).sort_index()


# --------------------------------------------------------------- daily_max
def test_daily_max_filters_hours_and_months():
    times = pd.date_range("2025-07-10 00:00", "2025-07-11 23:00",
                          freq="h", tz="UTC")
    df = pd.DataFrame({"time": times, "wbgt_c": np.arange(len(times), dtype=float)})
    dm = daily_max(df, "wbgt_c", months=(7,), hours=(7, 18))
    # local Asia/Qatar = UTC+3; local hours 7..18 -> UTC 4..15 each day
    assert list(dm.index.astype(str)) == ["2025-07-10", "2025-07-11"]
    # first day: UTC rows 4..15 -> max at row 15
    assert dm.iloc[0] == 15.0


# ------------------------------------------------ prior_years_threshold
def test_threshold_uses_only_strictly_prior_years():
    s = _daily({2019: [30.0] * 10, 2020: [40.0] * 10, 2021: [50.0] * 10})
    assert np.isnan(prior_years_threshold(s, 2019))
    assert prior_years_threshold(s, 2020, percentile=50) == 30.0
    # 2021 sees 2019+2020: median of twenty values, ten 30s and ten 40s
    assert prior_years_threshold(s, 2021, percentile=50) == 35.0


# ------------------------------------------------------- heatwave_onsets
def test_single_clean_onset():
    # 2020 establishes climatology; 2021 has one 3-day spike mid-season
    base = [28.0] * 20
    spike = list(base)
    spike[10:13] = [40.0, 41.0, 40.0]
    s = _daily({2020: [26.0, 27.0, 28.0, 29.0, 30.0] * 4, 2021: spike})
    onsets = heatwave_onsets(s, percentile=90, min_run_days=2)
    assert onsets == [pd.Timestamp(2021, 5, 11)]


def test_run_of_exactly_min_run_days_counts():
    seq = [28.0] * 20
    seq[5:7] = [39.0, 39.0]
    s = _daily({2020: [26.0, 27.0, 28.0, 29.0, 30.0] * 4, 2021: seq})
    assert heatwave_onsets(s, min_run_days=2) == [pd.Timestamp(2021, 5, 6)]


def test_no_onset_on_first_day_of_season():
    seq = [40.0, 41.0, 40.0] + [28.0] * 17
    s = _daily({2020: [26.0, 27.0, 28.0, 29.0, 30.0] * 4, 2021: seq})
    assert heatwave_onsets(s, min_run_days=2) == []


def test_back_to_back_events_give_two_onsets():
    seq = [28.0] * 20
    seq[4:6] = [40.0, 40.0]      # event 1
    seq[6] = 28.0               # one cool day
    seq[7:9] = [40.0, 40.0]      # event 2
    s = _daily({2020: [26.0, 27.0, 28.0, 29.0, 30.0] * 4, 2021: seq})
    assert heatwave_onsets(s, min_run_days=2) == [
        pd.Timestamp(2021, 5, 5), pd.Timestamp(2021, 5, 8)]


def test_gap_in_run_breaks_it():
    # two hot days, then a missing calendar day, then a hot day
    idx = [pd.Timestamp(2021, 5, 2), pd.Timestamp(2021, 5, 3),
           pd.Timestamp(2021, 5, 5), pd.Timestamp(2021, 5, 6)]
    s = pd.concat([
        _daily({2020: [26.0, 27.0, 28.0, 29.0, 30.0] * 2}),
        pd.Series([40.0, 40.0, 40.0, 28.0], index=pd.DatetimeIndex(idx)),
    ])
    # day 2-3 is a valid 2-run with 5-1 absent as the "preceding" day ->
    # no preceding row, so no onset; 5-3 to 5-5 is not consecutive
    assert heatwave_onsets(s, min_run_days=2) == []


def test_year_without_prior_data_contributes_nothing():
    seq = [40.0] * 5 + [28.0] * 15
    s = _daily({2021: seq})
    assert heatwave_onsets(s) == []


# --------------------------------------------------------- preonset_mask
def test_preonset_mask_marks_window():
    onsets = [pd.Timestamp(2021, 7, 10)]
    times = pd.date_range("2021-07-01 00:00", "2021-07-12 23:00",
                          freq="h", tz="UTC")
    m = preonset_mask(pd.Series(times), onsets, window_days=5)
    local_date = pd.to_datetime(
        pd.Series(times), utc=True).dt.tz_convert("Asia/Qatar").dt.date
    marked = {str(d) for d, keep in zip(local_date, m) if keep}
    assert marked == {"2021-07-05", "2021-07-06", "2021-07-07",
                      "2021-07-08", "2021-07-09"}
