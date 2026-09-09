"""
Translate a PlanRequest into a PlanResponse.

Flow: get_forecast -> compute_wbgt -> run_scheduler (the typed tool layer),
then read the per-hour detail back out. RunSchedulerResponse exposes the
plan's hourly work fraction and the aggregate peak/tail only, so the two
per-hour retained-load paths and the calendar baseline's hourly fraction are
re-derived here with the same two functions schedule_service uses internally --
`policy_calendar` and `retained_load_path` -- applied to the response's own
hours. No physics is added; the re-derived plan aggregates equal
The headline peak/tail numbers in `summary` are taken straight from
RunSchedulerResponse (`plan_*` and `baseline_*`, which is itself the
`policy_calendar` clock-ban baseline). Only the per-hour retained-load series
for the chart and the calendar baseline's per-hour fraction are re-derived,
with `policy_calendar` and `retained_load_path` -- the same functions
schedule_service uses -- so a 3rd-decimal rounding drift on a chart point is
possible but the summary is authoritative.

The comparison follows the walk-forward study in technical_report section 8:
both policies deliver the SAME required work-hours, and neither is given a hard
32.1 C stop. The calendar baseline is the fixed 10:00-15:30 midday ban
(`policy_calendar`); the optimiser reshapes the day to minimise retained heat
load at equal output. The 32.1 C stop-work line (Decision 17/2021) is reported
per hour as `over_threshold` so the client can flag it -- the plan is the
load-optimal shape, and the hard stop is applied on top by the operator.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

from api.cache import forecast_cache
from api.schemas import HourRow, PlanMeta, PlanRequest, PlanResponse, PlanSummary
from src.agent.schemas import (
    ComputeWbgtRequest, CrewParams, GetForecastRequest, RuleConstraints,
    RunSchedulerRequest, WbgtHour,
)
from src.agent.tools import compute_wbgt, get_forecast, run_scheduler
from src.scheduler import PHI_DEFAULT, policy_calendar, retained_load_path
from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C

THRESHOLD_C = QATAR_WBGT_STOP_WORK_THRESHOLD_C
TAIL_PCT = 90.0
_FULL_WORK = 0.95   # plan fractions at/above this read as "work", below as "reduced"

_LEAD_NOTE = (
    "Single-point forecast for the chosen grid cell; nominal lead is the "
    "gap between today and the target date. Screening decision-support built "
    "on the ACGIH TLV work/rest tables and Qatar Decision 17/2021 -- not "
    "medical advice, and not a substitute for on-site physiological "
    "monitoring."
)


def _forecast(req: PlanRequest, source: str):
    key = (source, round(req.lat, 2), round(req.lon, 2), req.date.isoformat())

    def produce():
        return get_forecast(GetForecastRequest(
            lat=req.lat, lon=req.lon,
            start_date=req.date - dt.timedelta(days=1),
            end_date=req.date + dt.timedelta(days=1),
            source=source,
        ))

    return forecast_cache.get_or_set(key, produce)


def build_plan(req: PlanRequest, *, forecast_source: str = "open-meteo",
               wbgt_hours: list[WbgtHour] | None = None) -> PlanResponse:
    if wbgt_hours is None:
        fc = _forecast(req, forecast_source)
        wb = compute_wbgt(ComputeWbgtRequest(
            hours=fc.hours, lat=req.lat, lon=req.lon))
        wbgt_hours = wb.hours
        fc_lat, fc_lon = fc.lat, fc.lon
    else:
        fc_lat, fc_lon = req.lat, req.lon

    sched = run_scheduler(RunSchedulerRequest(
        target_local_date=req.date,
        required_work_hours=req.required_work_hours,
        crew=CrewParams(workload=req.workload_class,
                        acclimatised=req.acclimatised, crew_size=1),
        constraints=RuleConstraints(),
        timezone=req.tz,
        wbgt_hours=wbgt_hours,
    ))

    plan = sched.plan
    local_hours = np.array([hp.local_time.hour for hp in plan], dtype=float)
    wbgt = np.array([hp.wbgt_c for hp in plan], dtype=float)
    w_plan = np.array([hp.work_fraction for hp in plan], dtype=float)
    wbgt_ref = sched.wbgt_ref_c

    # Decision 17/2021 baseline: the fixed 10:00-15:30 midday clock ban
    w_cal = policy_calendar(local_hours, np.ones(len(plan), dtype=bool))

    # per-hour retained-load series for the chart (re-derived); the headline
    # aggregates below come straight from the tool-layer response.
    path_plan = retained_load_path(w_plan, wbgt, phi=PHI_DEFAULT, wbgt_ref=wbgt_ref)
    path_cal = retained_load_path(w_cal, wbgt, phi=PHI_DEFAULT, wbgt_ref=wbgt_ref)

    peak_plan = float(sched.plan_peak_strain)
    peak_cal = float(sched.baseline_peak_strain)
    tail_plan = float(sched.plan_tail_strain)
    tail_cal = float(sched.baseline_tail_strain)

    def _state(frac: float) -> str:
        if frac <= 1e-9:
            return "stop"
        return "work" if frac >= _FULL_WORK else "reduced"

    hours = [
        HourRow(
            local_time=hp.local_time,
            hour=int(hp.local_time.hour),
            wbgt_c=round(float(hp.wbgt_c), 1),
            plan_work_fraction=round(float(w_plan[i]), 3),
            calendar_work_fraction=round(float(w_cal[i]), 3),
            retained_load_plan=round(float(path_plan[i]), 3),
            retained_load_calendar=round(float(path_cal[i]), 3),
            plan_state=_state(float(w_plan[i])),
            over_threshold=bool(wbgt[i] > THRESHOLD_C),
        )
        for i, hp in enumerate(plan)
    ]

    summary = PlanSummary(
        peak_plan=round(peak_plan, 3),
        peak_calendar=round(peak_cal, 3),
        tail_plan=round(tail_plan, 3),
        tail_calendar=round(tail_cal, 3),
        pct_peak_reduction=round(_pct(peak_cal, peak_plan), 1),
        pct_tail_reduction=round(_pct(tail_cal, tail_plan), 1),
        work_hours_delivered_plan=round(float(sched.work_hours_delivered), 2),
        work_hours_delivered_calendar=round(float(w_cal.sum()), 2),
        work_shortfall_plan=round(float(sched.work_shortfall), 2),
        stop_hours_plan=int((w_plan <= 1e-9).sum()),
        stop_hours_calendar=int((w_cal <= 1e-9).sum()),
        wbgt_ref_c=round(float(wbgt_ref), 1),
        threshold_c=THRESHOLD_C,
        solver_status=sched.solver_status,
    )

    meta = PlanMeta(
        model="liljegren-thermofeel / cvar-lp",
        forecast_source=("synthetic (deterministic mock)"
                         if forecast_source == "mock"
                         else "Open-Meteo forecast API (ERA5-blend NWP)"),
        lead_time_note=_LEAD_NOTE,
        generated_at=dt.datetime.now(dt.timezone.utc),
        date=req.date,
        location={"lat": round(fc_lat, 4), "lon": round(fc_lon, 4),
                  "grid_note": "nearest forecast grid cell"},
        attribution="Weather data by Open-Meteo.com, CC BY 4.0",
    )
    return PlanResponse(hours=hours, summary=summary, meta=meta)


def _pct(base: float, other: float) -> float:
    if base <= 1e-9:
        return 0.0
    return (base - other) / base * 100.0
