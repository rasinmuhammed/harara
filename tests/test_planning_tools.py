"""
The in-domain forecast tools the assistant narrates: nowcast, coolest_window,
climatology_compare, heat_trend. Deterministic against the mock forecast and
the committed 16-year WBGT record; none invents a number.
"""

import datetime as dt
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

os.environ.setdefault("HARARA_FORECAST_SOURCE", "mock")

from fastapi.testclient import TestClient

from api.main import app
from api.planning import (
    climatology_compare, coolest_window, heat_trend, nowcast,
)

client = TestClient(app)
LAT, LON = 25.2854, 51.531
TODAY = dt.date(2026, 7, 14)


def test_nowcast_shape():
    nc = nowcast(LAT, LON, today=TODAY, source="mock")
    assert nc["available"] is True
    assert 15.0 < nc["wbgt"] < 45.0
    assert nc["over_threshold"] in (True, False)
    assert "rest" in nc["acgih_band_acclimatised"] or "continuous" in nc["acgih_band_acclimatised"]
    assert nc["as_of_local"].endswith(":00")


def test_coolest_window_shape_and_ordering():
    cw = coolest_window(LAT, LON, TODAY + dt.timedelta(days=1), today=TODAY,
                        source="mock")
    assert cw["available"] is True
    assert cw["coolest_start"] < cw["coolest_end"]
    assert 15.0 < cw["coolest_mean_wbgt"] < 45.0
    # the mock summer day is hot through the middle
    assert cw["crosses_32_1_up"] is not None


def test_climatology_compare_uses_the_record():
    cc = climatology_compare(LAT, LON, TODAY + dt.timedelta(days=1), today=TODAY,
                             source="mock")
    assert cc["available"] and cc["comparable"]
    assert 0 <= cc["percentile"] <= 100
    assert cc["record_years"] >= 15
    assert cc["verdict"] in {
        "unusually hot for the time of year",
        "unusually mild for the time of year",
        "about typical for the time of year",
    }
    assert cc["climatology_median_peak"] > 20.0


def test_heat_trend_is_computed_from_the_record():
    tr = heat_trend(LAT, LON, today=TODAY)
    assert tr["first_year"] == 2010
    assert tr["last_year"] <= 2025  # partial 2026 dropped
    years = tr["stop_work_hours_per_year"]
    assert len(years) >= 14
    assert all(v >= 0 for v in years.values())
    assert tr["direction"] in {"rising", "falling", "flat"}
    assert "Doha" in tr["note"]


def test_tool_endpoints():
    r = client.get("/api/nowcast", params={"lat": LAT, "lon": LON})
    assert r.status_code == 200 and "wbgt" in r.json()
    r = client.get("/api/coolest-window",
                   params={"lat": LAT, "lon": LON, "date": "2026-07-15"})
    assert r.status_code == 200 and r.json()["coolest_start"]
    r = client.get("/api/climatology",
                   params={"lat": LAT, "lon": LON, "date": "2026-07-15"})
    assert r.status_code == 200 and "forecast_peak_wbgt" in r.json()
    r = client.get("/api/heat-trend", params={"lat": LAT, "lon": LON})
    assert r.status_code == 200 and r.json()["stop_work_hours_per_year"]
    r = client.get("/api/chat-refusals")
    assert r.status_code == 200 and "buckets" in r.json()
