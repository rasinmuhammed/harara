"""
API contract and golden-snapshot tests for POST /api/plan.

The plan is scored on a hand-built WBGT day (no network), so the snapshot is
deterministic. The test also asserts the API's re-derived plan aggregates
equal what the tool layer's RunSchedulerResponse reports for the same inputs.
"""

import datetime as dt
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np

from api.planning import build_plan
from api.schemas import PlanRequest, PlanResponse
from src.agent.schemas import (
    ComputeWbgtRequest, CrewParams, RuleConstraints, RunSchedulerRequest, WbgtHour,
)
from src.agent.tools import run_scheduler

SNAPSHOT = pathlib.Path(__file__).parent / "data" / "api_plan_snapshot.json"
DATE = dt.date(2026, 7, 15)
LAT, LON = 25.2854, 51.5310

# A plausible Doha mid-summer day: cool at the window edges, WBGT crossing
# 32.1 through the middle. UTC hours; Asia/Qatar is UTC+3, so 02:00Z = 05:00
# local ... 15:00Z = 18:00 local (the scheduler's 05:00-19:00 window).
_LOCAL_WBGT = {
    5: 27.4, 6: 28.1, 7: 29.6, 8: 31.0, 9: 32.2, 10: 33.1, 11: 33.7,
    12: 34.0, 13: 34.1, 14: 33.8, 15: 33.2, 16: 32.3, 17: 30.9, 18: 28.7,
}


def _wbgt_hours() -> list[WbgtHour]:
    out = []
    for local_h, val in _LOCAL_WBGT.items():
        utc = dt.datetime(DATE.year, DATE.month, DATE.day, local_h - 3,
                          tzinfo=dt.timezone.utc)
        out.append(WbgtHour(time_utc=utc, wbgt_c=val))
    return out


def _request() -> PlanRequest:
    return PlanRequest(lat=LAT, lon=LON, date=DATE, required_work_hours=8.0,
                       workload_class="moderate", acclimatised=True)


def _plan() -> PlanResponse:
    return build_plan(_request(), wbgt_hours=_wbgt_hours())


# --------------------------------------------------------------- contract
def test_plan_shape_and_invariants():
    p = _plan()
    assert len(p.hours) == 14
    assert [h.hour for h in p.hours] == list(range(5, 19))
    for h in p.hours:
        assert 0.0 <= h.plan_work_fraction <= 1.0
        assert h.calendar_work_fraction in (0.0, 1.0)
        assert h.plan_state in ("work", "reduced", "stop")
        assert h.over_threshold == (h.wbgt_c > p.summary.threshold_c)
    s = p.summary
    # equal output: both deliver the 8 requested / window-available hours
    assert math.isclose(s.work_hours_delivered_plan, 8.0, abs_tol=1e-6)
    assert math.isclose(s.work_hours_delivered_calendar, 8.0, abs_tol=1e-6)
    assert s.work_shortfall_plan == 0.0
    assert s.stop_hours_calendar == 6            # the 10:00-15:30 clock ban
    # the corrected guarantee: the plan never keeps the crew on site longer,
    # resting in the heat longer, or in more pieces than the calendar rule
    assert s.span_hours_plan <= s.span_hours_calendar + 1e-6
    assert s.onsite_rest_hours_plan <= s.onsite_rest_hours_calendar + 1e-6
    assert s.work_blocks_plan <= s.work_blocks_calendar
    assert set(s.earlier_start_fixed) == {"peak", "tail", "span_hours"}


def test_api_aggregates_match_tool_layer():
    """The re-derived plan peak/tail equal RunSchedulerResponse's own."""
    sched = run_scheduler(RunSchedulerRequest(
        target_local_date=DATE, required_work_hours=8.0,
        crew=CrewParams(workload="moderate", acclimatised=True, crew_size=1),
        constraints=RuleConstraints(), timezone="Asia/Qatar",
        wbgt_hours=_wbgt_hours()))
    p = _plan()
    assert math.isclose(p.summary.peak_plan, sched.plan_peak_strain, abs_tol=1e-3)
    assert math.isclose(p.summary.tail_plan, sched.plan_tail_strain, abs_tol=1e-3)


# --------------------------------------------------------------- golden
def _canonical(p: PlanResponse) -> dict:
    d = p.model_dump(mode="json")
    d["meta"].pop("generated_at", None)          # time-varying
    return d


def test_plan_matches_snapshot():
    got = _canonical(_plan())
    if not SNAPSHOT.exists():                     # first run writes it
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n")
    want = json.loads(SNAPSHOT.read_text())

    assert got["summary"] == want["summary"]
    assert len(got["hours"]) == len(want["hours"])
    for g, w in zip(got["hours"], want["hours"]):
        for k in ("hour", "plan_state", "over_threshold"):
            assert g[k] == w[k], (k, g, w)
        for k in ("wbgt_c", "plan_work_fraction", "calendar_work_fraction",
                  "retained_load_plan", "retained_load_calendar"):
            assert abs(g[k] - w[k]) < 1e-6, (k, g, w)


def test_plan_has_band_reactive_and_cycle():
    p = _plan()
    for h in p.hours:
        assert h.wbgt_lo <= h.wbgt_hi
        assert h.uncertain == (h.wbgt_lo <= p.summary.threshold_c <= h.wbgt_hi)
        assert 0.0 <= h.reactive_work_fraction <= 1.0
        assert h.cycle in {
            "rest in shade", "work the full hour",
            "work about 45 minutes, rest 15 in shade",
            "work about 30 minutes, rest 30 in shade",
            "work about 15 minutes, rest 45 in shade",
        }
    s = p.summary
    assert s.peak_reactive > 0
    # per-hour on_site flag is coherent with the reported span
    on = [h for h in p.hours if h.on_site]
    assert len(on) == s.span_hours_plan or s.solver_status == "no-allowed-hours"
    assert p.meta.lead_days >= 1


def test_rate_limit_falls_back_to_synthetic(monkeypatch):
    """A failed live forecast (e.g. an upstream 429) must still yield a plan,
    labelled honestly, not a 502."""
    import api.planning as P

    real_fetch = P._fetch

    def flaky(source, glat, glon, date):
        if source == "mock":
            return real_fetch(source, glat, glon, date)
        raise RuntimeError("429 Client Error: Too Many Requests")

    monkeypatch.setattr(P, "_fetch", flaky)
    P.forecast_cache.clear()

    req = PlanRequest(
        lat=LAT, lon=LON, date=dt.date.today() + dt.timedelta(days=1),
        required_work_hours=8, workload_class="moderate",
        acclimatised=True, tz="Asia/Qatar",
    )
    p = build_plan(req, forecast_source="open-meteo")
    assert len(p.hours) > 0
    assert p.summary.span_hours_plan <= p.summary.span_hours_calendar + 1e-6
    assert "fallback" in p.meta.forecast_source.lower()
