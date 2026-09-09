"""
Translate a PlanRequest into a PlanResponse.

Flow: get_forecast -> compute_wbgt -> run_scheduler (the typed tool layer),
then read the per-hour detail back out.

The headline peak/tail numbers in `summary` come straight from
RunSchedulerResponse (`plan_*` and `baseline_*`, the latter being the
`policy_calendar` clock-ban baseline). Only the per-hour retained-load series
for the chart and the calendar baseline's per-hour fraction are re-derived,
with `policy_calendar` and `retained_load_path`, the same functions
schedule_service uses internally, so a third-decimal rounding drift on a chart
point is possible but the summary is authoritative.

The comparison follows technical_report section 8: both policies deliver the
same required work-hours, and neither is given a hard 32.1 C stop. The calendar
baseline is the fixed 10:00-15:30 midday ban (`policy_calendar`); the optimiser
reshapes the day to minimise retained heat load at equal output. Hours where
the plan still schedules work above 32.1 C are reported as `over_threshold` so
the client can flag them; the hard stop is applied on top by the operator.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

from api.cache import forecast_cache
from api.schemas import HourRow, PlanMeta, PlanRequest, PlanResponse, PlanSummary
from src.agent.schemas import (
    ComputeWbgtRequest, CrewParams, GetForecastRequest, RuleConstraints,
    RunSchedulerRequest, RunSchedulerResponse, WbgtHour,
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
    "on the ACGIH TLV work/rest tables and Qatar Decision 17/2021, not "
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


def plan_with_sched(
    req: PlanRequest,
    *,
    forecast_source: str = "open-meteo",
    wbgt_hours: list[WbgtHour] | None = None,
) -> tuple[PlanResponse, RunSchedulerResponse]:
    """The full plan plus the raw RunSchedulerResponse it was built from.
    /api/chat needs the latter to hand to src.agent.brief.generate_briefing."""
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

    # per-hour retained-load series for the chart (re-derived); headline
    # aggregates below come straight from the tool-layer response.
    path_plan = retained_load_path(w_plan, wbgt, phi=PHI_DEFAULT, wbgt_ref=wbgt_ref)
    path_cal = retained_load_path(w_cal, wbgt, phi=PHI_DEFAULT, wbgt_ref=wbgt_ref)

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
        peak_plan=round(float(sched.plan_peak_strain), 3),
        peak_calendar=round(float(sched.baseline_peak_strain), 3),
        tail_plan=round(float(sched.plan_tail_strain), 3),
        tail_calendar=round(float(sched.baseline_tail_strain), 3),
        pct_peak_reduction=round(
            _pct(sched.baseline_peak_strain, sched.plan_peak_strain), 1),
        pct_tail_reduction=round(
            _pct(sched.baseline_tail_strain, sched.plan_tail_strain), 1),
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
    return PlanResponse(hours=hours, summary=summary, meta=meta), sched


def build_plan(req: PlanRequest, *, forecast_source: str = "open-meteo",
               wbgt_hours: list[WbgtHour] | None = None) -> PlanResponse:
    return plan_with_sched(
        req, forecast_source=forecast_source, wbgt_hours=wbgt_hours)[0]


def _pct(base: float, other: float) -> float:
    if base <= 1e-9:
        return 0.0
    return (base - other) / base * 100.0
