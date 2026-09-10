"""
The 24-hour WBGT context view (`day_curve`): a full local day, ordered, with a
daylight flag for the working window and no solar term at night. Deterministic
against the mock forecast, no model.
"""

import datetime as dt
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

os.environ.setdefault("HARARA_FORECAST_SOURCE", "mock")

import numpy as np
from fastapi.testclient import TestClient

from api.main import app
from api.planning import build_plan, day_curve
from api.schemas import PlanRequest
from src.agent.schemas import ComputeWbgtRequest, GetForecastRequest
from src.agent.tools import compute_wbgt, get_forecast

client = TestClient(app)
LAT, LON = 25.2854, 51.531
DATE = dt.date(2026, 7, 15)


def test_day_curve_has_24_ordered_hours():
    dc = day_curve(LAT, LON, DATE, source="mock")
    assert dc["available"] is True
    pts = dc["points"]
    assert [p["hour"] for p in pts] == list(range(24))
    assert all(15.0 < p["wbgt_c"] < 45.0 for p in pts)


def test_daylight_flag_is_the_working_window():
    dc = day_curve(LAT, LON, DATE, source="mock")
    for p in dc["points"]:
        assert p["is_daylight"] == (5 <= p["hour"] <= 18)


def test_over_threshold_flag_matches_the_value():
    dc = day_curve(LAT, LON, DATE, source="mock")
    for p in dc["points"]:
        assert p["over_threshold"] == (p["wbgt_c"] > 32.1)
    listed = {int(s[:2]) for s in dc["hours_over_threshold"]}
    assert listed == {p["hour"] for p in dc["points"] if p["over_threshold"]}


def test_night_hours_carry_no_solar_term():
    """A night hour's WBGT is unchanged when the shortwave and direct terms
    are forced to zero: the Liljegren globe term is already zero after dark."""
    fc = get_forecast(GetForecastRequest(
        lat=LAT, lon=LON, start_date=DATE, end_date=DATE, source="mock"))
    z = dt.timezone(dt.timedelta(hours=3))  # Asia/Qatar
    night = [h for h in fc.hours if h.time_utc.astimezone(z).hour in (1, 2, 3)]
    assert night
    dark = [h.model_copy(update={"shortwave_wm2": 0.0, "direct_wm2": 0.0})
            for h in night]
    a = compute_wbgt(ComputeWbgtRequest(hours=night, lat=LAT, lon=LON)).hours
    b = compute_wbgt(ComputeWbgtRequest(hours=dark, lat=LAT, lon=LON)).hours
    for x, y in zip(a, b):
        assert abs(x.wbgt_c - y.wbgt_c) < 1e-6


def test_day_curve_endpoint_and_plan_embed():
    r = client.get("/api/day-curve",
                   params={"lat": LAT, "lon": LON, "date": DATE.isoformat()})
    assert r.status_code == 200
    j = r.json()
    assert len(j["points"]) == 24 and "solar_note" in j
    assert j["coolest_window"]["start"] < j["coolest_window"]["end"]

    p = build_plan(PlanRequest(lat=LAT, lon=LON, date=DATE,
                               required_work_hours=8, workload_class="moderate",
                               acclimatised=True), forecast_source="mock")
    assert p.day_curve is not None
    assert len(p.day_curve.points) == 24
    assert p.day_curve.solar_note
