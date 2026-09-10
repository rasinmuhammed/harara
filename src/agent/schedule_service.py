"""
Typed, deterministic entry point to the scheduler. Wraps src.scheduler and
src.heat_stress; adds no domain logic beyond translating the request into
the arrays those functions expect and reading the results back out.

The LLM never calls src.scheduler directly. It calls run_scheduler with a
validated RunSchedulerRequest, and everything numeric here is computed by
the tested deterministic core.
"""

from __future__ import annotations

import datetime as dt
import zoneinfo

import numpy as np

from src.agent.schemas import (
    HourPlan, RunSchedulerRequest, RunSchedulerResponse, WbgtHour,
)
from src.heat_stress import continuous_work_limit_c
from src.scheduler import (
    _worked_span, cumulative_exposure, policy_calendar, policy_earlier_start,
    retained_load_path, schedule_windowed,
)
from src.solar import cos_solar_zenith_angle
from src.wbgt import wbgt_liljegren_c

TAIL_PCT = 90.0


def _wbgt_from_forecast(fc, lat: float, lon: float) -> list[WbgtHour]:
    import pandas as pd

    times = pd.DatetimeIndex([h.time_utc for h in fc.hours])
    cz = cos_solar_zenith_angle(times, lat, lon)
    w = wbgt_liljegren_c(
        temp_c=np.array([h.temp_c for h in fc.hours]),
        rh_pct=np.array([h.rh_pct for h in fc.hours]),
        pressure_hpa=np.array([h.pressure_hpa for h in fc.hours]),
        wind_speed_10m_ms=np.array([h.wind_ms for h in fc.hours]),
        shortwave_wm2=np.array([h.shortwave_wm2 for h in fc.hours]),
        direct_wm2=np.array([h.direct_wm2 for h in fc.hours]),
        cos_zenith=cz,
    )
    return [WbgtHour(time_utc=h.time_utc, wbgt_c=float(v))
            for h, v in zip(fc.hours, w)]


def run_scheduler(req: RunSchedulerRequest) -> RunSchedulerResponse:
    tz = zoneinfo.ZoneInfo(req.timezone)
    notes: list[str] = []

    wbgt_hours = req.wbgt_hours
    if wbgt_hours is None:
        wbgt_hours = _wbgt_from_forecast(
            req.forecast, req.forecast.lat, req.forecast.lon)

    # local-hour grid for the target date, restricted to the working window
    lo = int(req.constraints.working_window.start[:2])
    hi = int(req.constraints.working_window.end[:2])
    grid_hours = list(range(lo, hi))

    by_hour: dict[int, float] = {}
    for wh in wbgt_hours:
        loc = wh.time_utc.astimezone(tz)
        if loc.date() == req.target_local_date:
            by_hour[loc.hour] = wh.wbgt_c
    missing = [h for h in grid_hours if h not in by_hour]
    if missing:
        raise ValueError(
            f"WBGT not available for local hours {missing} on "
            f"{req.target_local_date}; provide a forecast that covers the "
            f"working window")

    H = len(grid_hours)
    wbgt = np.array([by_hour[h] for h in grid_hours], dtype=float)
    local_hour_f = np.array(grid_hours, dtype=float)

    stop_thr = req.constraints.wbgt_stop_work_c
    in_season = (req.constraints.seasonal_window is None
                 or req.constraints.seasonal_window.contains(req.target_local_date))

    allowed = np.ones(H, dtype=bool)
    reasons: list[str | None] = [None] * H
    for i, hf in enumerate(local_hour_f):
        if not in_season:
            allowed[i] = False
            reasons[i] = "off-season"
            continue
        if any(w.contains_hour(hf) for w in req.constraints.banned_hour_windows):
            allowed[i] = False
            reasons[i] = "calendar-ban"
            continue
        if stop_thr is not None and wbgt[i] > stop_thr:
            allowed[i] = False
            reasons[i] = "wbgt-stop-work"

    wbgt_ref = continuous_work_limit_c(req.crew.workload, req.crew.acclimatised)

    span_cap_h = req.max_span_hours
    if span_cap_h is None:
        span_cap_h = req.required_work_hours + req.rest_allowance_hours

    w_ear = (policy_earlier_start(wbgt, allowed, req.required_work_hours)
             if req.earlier_start else np.zeros(H))

    if allowed.any():
        wr = schedule_windowed(
            wbgt[None, :], allowed, req.required_work_hours,
            wbgt_point=wbgt, beta=req.beta, wbgt_ref=wbgt_ref,
            span_cap_h=span_cap_h, rest_allowance_h=req.rest_allowance_hours,
            w_ref=(w_ear if req.earlier_start else None))
        w_plan = wr.w
        status = wr.status
        t_in, t_out = int(wr.t_in), int(wr.t_out)
        span_hours = float(wr.span_hours)
        onsite_rest = float(wr.onsite_rest_hours)
        n_blocks = int(wr.n_blocks)
    else:
        w_plan = np.zeros(H)
        status = "no-allowed-hours"
        t_in, t_out = 0, H - 1
        span_hours = onsite_rest = 0.0
        n_blocks = 0
        notes.append("Every working hour is banned or over the stop-work "
                     "threshold; no work can be scheduled.")

    on_site = [bool(t_in <= i <= t_out) for i in range(H)]

    calendar_local = np.array([
        dt.datetime.combine(req.target_local_date, dt.time(int(h)), tzinfo=tz)
        for h in grid_hours])
    w_base = policy_calendar(local_hour_f, np.ones(H, dtype=bool))

    path_plan = retained_load_path(w_plan, wbgt, wbgt_ref=wbgt_ref)
    path_base = retained_load_path(w_base, wbgt, wbgt_ref=wbgt_ref)
    path_ear = retained_load_path(w_ear, wbgt, wbgt_ref=wbgt_ref)

    delivered = float(w_plan.sum())
    plan_rows = [
        HourPlan(local_time=calendar_local[i], wbgt_c=float(wbgt[i]),
                 work_fraction=round(float(w_plan[i]), 3),
                 allowed=bool(allowed[i]), reason_not_allowed=reasons[i],
                 on_site=on_site[i],
                 earlier_start_work_fraction=round(float(w_ear[i]), 3))
        for i in range(H)]

    return RunSchedulerResponse(
        plan=plan_rows,
        plan_peak_strain=round(float(path_plan.max()), 3),
        plan_tail_strain=round(float(np.percentile(path_plan, TAIL_PCT)), 3),
        baseline_peak_strain=round(float(path_base.max()), 3),
        baseline_tail_strain=round(float(np.percentile(path_base, TAIL_PCT)), 3),
        work_hours_delivered=round(delivered, 3),
        work_hours_required=req.required_work_hours,
        work_shortfall=round(max(0.0, req.required_work_hours - delivered), 3),
        wbgt_ref_c=wbgt_ref,
        allowed_hours=[f"{h:02d}:00" for i, h in enumerate(grid_hours) if allowed[i]],
        stop_work_hours=[f"{h:02d}:00" for i, h in enumerate(grid_hours)
                        if reasons[i] == "wbgt-stop-work"],
        applied_rule_ids=list(req.constraints.rule_ids),
        solver_status=status,
        notes=notes,
        plan_window=([f"{grid_hours[t_in]:02d}:00", f"{grid_hours[t_out]:02d}:00"]
                     if allowed.any() else None),
        plan_span_hours=round(span_hours, 2),
        plan_onsite_rest_hours=round(onsite_rest, 2),
        plan_work_blocks=n_blocks,
        earlier_start_peak_strain=round(float(path_ear.max()), 3),
        earlier_start_tail_strain=round(float(np.percentile(path_ear, TAIL_PCT)), 3),
        earlier_start_span_hours=round(float(_worked_span(w_ear)), 2),
    )
