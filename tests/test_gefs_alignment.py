"""
The valid-time alignment of the GEFS reforecast pull. A silent off-by-one
between init_time, lead, forecast-day and Asia/Qatar local hour would
invalidate every downstream GEFS result, so it gets its own test.
"""

import pathlib
import sys

import pandas as pd
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from fetch_gefs_reforecast import LEADS, LEAD_TO_FDAY, verify_lead_alignment


def test_every_lead_lands_in_the_working_window():
    ok, tbl = verify_lead_alignment(tz_offset_h=3, day_lo=9, day_hi=18)
    assert ok, tbl
    for r in tbl:
        assert 9 <= r["local_hour"] <= 18
        assert r["fday"] == r["exp_fday"]


def test_forecast_day_grouping_matches_lead():
    # 00Z init: leads 30-47 are +1 day, 54-71 are +2, 78-95 are +3
    for lead, fday in LEAD_TO_FDAY.items():
        assert fday == 1 + (lead - 24) // 24
        assert fday in (1, 2, 3)


def test_valid_time_arithmetic_end_to_end():
    """init_time + lead, converted to Asia/Qatar, is the working hour."""
    init = pd.Timestamp("2015-07-01 00:00", tz="UTC")
    for lead in LEADS:
        valid = init + pd.Timedelta(hours=lead)
        local = valid.tz_convert("Asia/Qatar")
        assert local.hour in (12, 15, 18)
        assert (local.date() - init.date()).days == LEAD_TO_FDAY[lead]


def test_coalesce_only_merges_consecutive_leads():
    """Regression: GRIB2 messages are gapless, so byte-adjacency alone must
    NOT merge leads that are 3h+ apart with unwanted messages between."""
    from fetch_gefs_reforecast import _coalesce
    # leads 33,36,39 are consecutive 3-hourly (msgs 11,12,13) -> one GET;
    # 57 is far away (msgs between) -> its own GET, even though byte-adjacent.
    spans = {33: (1000, 1400), 36: (1400, 1800), 39: (1800, 2200),
             57: (2200, 2600)}                       # 39->57 gap in leads
    out = _coalesce(spans)
    assert out == [(1000, 2200), (2200, 2600)]
    # single lead
    assert _coalesce({36: (5, 9)}) == [(5, 9)]
