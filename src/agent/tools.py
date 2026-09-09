"""
The typed tool layer. Each function takes a validated request model and
returns a response model, wrapping deterministic code in src/ or the rule
store. No tool contains domain logic of its own.

These are the only entry points the agent is allowed to use to obtain a
number.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from src.agent import rule_store
from src.agent.schedule_service import run_scheduler as _run_scheduler
from src.agent.schemas import (
    ComputeWbgtRequest, ComputeWbgtResponse, GetForecastRequest,
    GetForecastResponse, LookupRuleRequest, LookupRuleResponse,
    RunSchedulerRequest, RunSchedulerResponse, WbgtHour, WeatherHour,
)
from src.solar import cos_solar_zenith_angle
from src.wbgt import wbgt_liljegren_c


# --------------------------------------------------------------------------
def _mock_forecast(req: GetForecastRequest) -> list[WeatherHour]:
    """Deterministic synthetic day: a Doha-summer diurnal cycle. Used for
    tests and offline runs (source='mock')."""
    hours: list[WeatherHour] = []
    d = req.start_date
    while d <= req.end_date:
        for h in range(24):
            t = dt.datetime(d.year, d.month, d.day, h, tzinfo=dt.timezone.utc)
            local_h = (h + 3) % 24                       # Asia/Qatar
            diurnal = np.sin(np.pi * max(0.0, (local_h - 5) / 14.0))
            hours.append(WeatherHour(
                time_utc=t,
                temp_c=round(34.0 + 9.0 * diurnal, 1),
                rh_pct=round(45.0 - 20.0 * diurnal, 1),
                wind_ms=round(3.5 + 1.5 * diurnal, 1),
                shortwave_wm2=round(max(0.0, 950.0 * diurnal), 1),
                direct_wm2=round(max(0.0, 700.0 * diurnal), 1),
                pressure_hpa=1000.0,
            ))
        d += dt.timedelta(days=1)
    return hours


def get_forecast(req: GetForecastRequest) -> GetForecastResponse:
    now = dt.datetime.now(dt.timezone.utc)
    if req.source == "mock":
        return GetForecastResponse(
            lat=req.lat, lon=req.lon, hours=_mock_forecast(req),
            provider="mock", retrieved_utc=now)
    from src.open_meteo import fetch_forecast

    df = fetch_forecast(req.lat, req.lon, req.start_date, req.end_date)
    hours = [
        WeatherHour(
            time_utc=row.time.to_pydatetime(),
            temp_c=float(row.temperature_2m),
            rh_pct=float(row.relative_humidity_2m),
            wind_ms=float(row.wind_speed_10m),
            shortwave_wm2=float(np.nan_to_num(row.shortwave_radiation)),
            direct_wm2=float(np.nan_to_num(row.direct_radiation)),
            pressure_hpa=float(row.surface_pressure),
        )
        for row in df.itertuples()
    ]
    return GetForecastResponse(lat=req.lat, lon=req.lon, hours=hours,
                               provider="open-meteo", retrieved_utc=now)


# --------------------------------------------------------------------------
def compute_wbgt(req: ComputeWbgtRequest) -> ComputeWbgtResponse:
    times = pd.DatetimeIndex([h.time_utc for h in req.hours])
    cz = cos_solar_zenith_angle(times, req.lat, req.lon)
    w = wbgt_liljegren_c(
        temp_c=np.array([h.temp_c for h in req.hours]),
        rh_pct=np.array([h.rh_pct for h in req.hours]),
        pressure_hpa=np.array([h.pressure_hpa for h in req.hours]),
        wind_speed_10m_ms=np.array([h.wind_ms for h in req.hours]),
        shortwave_wm2=np.array([h.shortwave_wm2 for h in req.hours]),
        direct_wm2=np.array([h.direct_wm2 for h in req.hours]),
        cos_zenith=cz,
    )
    return ComputeWbgtResponse(
        hours=[WbgtHour(time_utc=h.time_utc, wbgt_c=round(float(v), 2))
               for h, v in zip(req.hours, w)])


# --------------------------------------------------------------------------
def run_scheduler(req: RunSchedulerRequest) -> RunSchedulerResponse:
    return _run_scheduler(req)


# --------------------------------------------------------------------------
def lookup_rule(req: LookupRuleRequest) -> LookupRuleResponse:
    if req.rule_id:
        try:
            rec = rule_store.load(req.rule_id)
        except FileNotFoundError:
            return LookupRuleResponse(matches=[])
        if rec.status != "confirmed" and not req.include_unconfirmed:
            return LookupRuleResponse(matches=[])
        return LookupRuleResponse(matches=[rec])

    q = req.query.lower().split()
    out = []
    for rec in rule_store.load_all():
        if rec.status != "confirmed" and not req.include_unconfirmed:
            continue
        hay = " ".join([rec.title, rec.jurisdiction, *rec.tags]).lower()
        if all(tok in hay for tok in q):
            out.append(rec)
    return LookupRuleResponse(matches=out)


TOOLS = {
    "get_forecast": (GetForecastRequest, get_forecast),
    "compute_wbgt": (ComputeWbgtRequest, compute_wbgt),
    "run_scheduler": (RunSchedulerRequest, run_scheduler),
    "lookup_rule": (LookupRuleRequest, lookup_rule),
}
