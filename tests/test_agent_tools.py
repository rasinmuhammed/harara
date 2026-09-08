"""
The typed tool layer: schema validation, and that each tool wraps the
deterministic core without adding numbers of its own.
"""

import datetime as dt
import pathlib
import sys

import numpy as np
import pytest
from pydantic import ValidationError

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.agent import tools
from src.agent.schemas import (
    ComputeWbgtRequest, CrewParams, GetForecastRequest, HourWindow,
    LookupRuleRequest, RuleConstraints, RunSchedulerRequest, DateWindow,
)
from src.heat_stress import continuous_work_limit_c


DOHA = dict(lat=25.27, lon=51.61)


def _mock_day(date="2026-07-15"):
    d = dt.date.fromisoformat(date)
    fc = tools.get_forecast(GetForecastRequest(
        **DOHA, start_date=d, end_date=d, source="mock"))
    wb = tools.compute_wbgt(ComputeWbgtRequest(hours=fc.hours, **DOHA))
    return d, fc, wb


# --------------------------------------------------------------- schemas
def test_hour_window_format():
    HourWindow(start="10:00", end="15:30")
    with pytest.raises(ValidationError):
        HourWindow(start="25:00", end="15:30")
    with pytest.raises(ValidationError):
        HourWindow(start="1000", end="15:30")


def test_date_window_contains():
    w = DateWindow(start="06-01", end="09-15")
    assert w.contains(dt.date(2026, 7, 1))
    assert not w.contains(dt.date(2026, 10, 1))


def test_run_scheduler_request_rejects_bad_input():
    with pytest.raises(ValidationError):
        RunSchedulerRequest(
            target_local_date=dt.date(2026, 7, 15),
            required_work_hours=0,                      # must be > 0
            crew=CrewParams(workload="heavy", acclimatised=False, crew_size=12),
            constraints=RuleConstraints())
    with pytest.raises(ValidationError):
        RunSchedulerRequest(                            # no wbgt_hours, no forecast
            target_local_date=dt.date(2026, 7, 15),
            required_work_hours=8,
            crew=CrewParams(workload="heavy", acclimatised=False, crew_size=12),
            constraints=RuleConstraints())


# --------------------------------------------------------------- get_forecast
def test_get_forecast_mock_shape_and_ranges():
    d, fc, _ = _mock_day()
    assert fc.provider == "mock"
    assert len(fc.hours) == 24
    assert all(0 <= h.rh_pct <= 100 and h.wind_ms >= 0 for h in fc.hours)


# --------------------------------------------------------------- compute_wbgt
def test_compute_wbgt_peaks_midday():
    _, _, wb = _mock_day()
    vals = np.array([h.wbgt_c for h in wb.hours])
    # local noon is 09:00 UTC -> index 9; WBGT should peak in the afternoon
    peak_hour_utc = int(np.argmax(vals))
    assert 8 <= peak_hour_utc <= 13
    assert 20 < vals.max() < 45


# --------------------------------------------------------------- run_scheduler
def test_run_scheduler_applies_constraints_and_beats_baseline():
    d, fc, wb = _mock_day()
    req = RunSchedulerRequest(
        target_local_date=d, required_work_hours=8.0,
        crew=CrewParams(workload="moderate", acclimatised=True, crew_size=10),
        constraints=RuleConstraints(
            banned_hour_windows=[HourWindow(start="10:00", end="15:30")],
            wbgt_stop_work_c=32.1,
            working_window=HourWindow(start="05:00", end="19:00")),
        wbgt_hours=wb.hours)
    res = tools.run_scheduler(req)

    assert res.wbgt_ref_c == continuous_work_limit_c("moderate", True)
    banned = {p.local_time.hour for p in res.plan if p.reason_not_allowed == "calendar-ban"}
    assert banned == {10, 11, 12, 13, 14, 15}
    for p in res.plan:
        if not p.allowed:
            assert p.work_fraction == 0.0
            assert p.reason_not_allowed in {
                "calendar-ban", "wbgt-stop-work", "off-season"}
    # optimiser is never worse than the calendar-ban baseline on peak strain
    assert res.plan_peak_strain <= res.baseline_peak_strain + 1e-6
    assert res.work_hours_delivered <= 8.0 + 1e-6


def test_run_scheduler_off_season_blocks_everything():
    d = dt.date(2026, 1, 15)
    fc = tools.get_forecast(GetForecastRequest(**DOHA, start_date=d, end_date=d,
                                               source="mock"))
    wb = tools.compute_wbgt(ComputeWbgtRequest(hours=fc.hours, **DOHA))
    res = tools.run_scheduler(RunSchedulerRequest(
        target_local_date=d, required_work_hours=8.0,
        crew=CrewParams(workload="heavy", acclimatised=False, crew_size=5),
        constraints=RuleConstraints(
            seasonal_window=DateWindow(start="06-01", end="09-15")),
        wbgt_hours=wb.hours))
    assert res.work_hours_delivered == 0.0
    assert res.work_shortfall == 8.0
    assert all(p.reason_not_allowed == "off-season" for p in res.plan)


# --------------------------------------------------------------- lookup_rule
def test_lookup_rule_missing_returns_empty():
    assert tools.lookup_rule(LookupRuleRequest(rule_id="does-not-exist")).matches == []


def test_lookup_rule_requires_id_or_query():
    with pytest.raises(ValidationError):
        LookupRuleRequest()
