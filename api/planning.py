"""
Translate a PlanRequest into a PlanResponse.

Flow: get_forecast -> compute_wbgt -> run_scheduler (the typed tool layer),
then read the per-hour detail back out.

Headline peak/tail numbers in `summary` come straight from
RunSchedulerResponse (`plan_*` and `baseline_*`, the latter being the
`policy_calendar` clock-ban baseline). Per-hour retained-load series, the
calendar baseline's hourly fraction, and the stop-when-hot reactive series are
re-derived with `policy_calendar`, `policy_reactive` and `retained_load_path`,
the same functions schedule_service uses internally.

The comparison follows technical_report section 8: the plan, the fixed calendar
ban, and the reactive rule all deliver the same required work-hours, and none
is given a hard 32.1 C stop. The plan minimises retained heat load; hours where
it still schedules work above 32.1 C are reported as `over_threshold`.

Each hour also carries a p10 to p90 forecast band from
`api/data/wbgt_residuals.json` (built once by scripts/build_residual_table.py).
The plan stays on the point forecast (section 15); the band only marks which
hours are borderline across plausible forecasts.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import numpy as np

from api.cache import forecast_cache
from api.schemas import HourRow, PlanMeta, PlanRequest, PlanResponse, PlanSummary
from src.agent.schemas import (
    ComputeWbgtRequest, CrewParams, GetForecastRequest, RuleConstraints,
    RunSchedulerRequest, RunSchedulerResponse, WbgtHour,
)
from src.agent.tools import compute_wbgt, get_forecast, run_scheduler
from src.scheduler import (
    PHI_DEFAULT, _work_blocks, _worked_span, cumulative_exposure,
    policy_calendar, policy_reactive, retained_load_path,
)
from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C

THRESHOLD_C = QATAR_WBGT_STOP_WORK_THRESHOLD_C
TAIL_PCT = 90.0
_FULL_WORK = 0.95

_RESID = json.loads(
    (pathlib.Path(__file__).parent / "data" / "wbgt_residuals.json").read_text()
)

_LEAD_NOTE = (
    "Single-point forecast for the chosen grid cell. Screening decision-support "
    "built on the ACGIH TLV work/rest tables and Qatar Decision 17/2021, not "
    "medical advice, and not a substitute for on-site physiological monitoring."
)
_UNCERTAINTY_NOTE = (
    "The band on each hour is the p10 to p90 of past forecast error at this "
    "lead. Where it crosses 32.1 C the hour is borderline."
)
_DRY_HOT_NOTE = (
    "This day looks dry and hot. WBGT can under-read the strain when the air "
    "is very dry, so water and rest still matter even if the number looks "
    "lower."
)


def _snap(x: float) -> float:
    """Nearest 0.25 degree, the forecast grid. Collapses nearby requests onto
    one upstream call and one cache entry."""
    return round(x * 4.0) / 4.0


def _fetch(source: str, glat: float, glon: float, date: dt.date):
    return get_forecast(GetForecastRequest(
        lat=glat, lon=glon,
        start_date=date - dt.timedelta(days=1),
        end_date=date + dt.timedelta(days=1),
        source=source,
    ))


def _forecast(req: PlanRequest, source: str):
    """Returns (forecast, source_actually_used). On an upstream failure such as
    a rate limit, serve the last good value for this grid cell if we have one,
    otherwise the deterministic synthetic day, so the demo still answers."""
    glat, glon = _snap(req.lat), _snap(req.lon)
    key = (source, glat, glon, req.date.isoformat())

    used = {"source": source}

    def produce():
        try:
            return _fetch(source, glat, glon, req.date)
        except Exception:
            if source == "mock":
                raise
            stale = forecast_cache.peek(key)
            if stale is not None:
                used["source"] = f"{source}-stale"
                return stale
            used["source"] = "mock-fallback"
            return _fetch("mock", glat, glon, req.date)

    fc = forecast_cache.get_or_set(key, produce)
    return fc, used["source"]


def weekly_outlook(lat: float, lon: float, *, today: dt.date | None = None,
                   tz: str = "Asia/Qatar", source: str = "open-meteo",
                   days: int = 7) -> dict:
    """Daily peak and mean WBGT for the next `days` local days at one grid cell.
    Shares the plan's cache and the same rate-limit fallback. Used by the
    assistant to answer 'how does tomorrow compare to the week'."""
    import zoneinfo

    today = today or dt.date.today()
    glat, glon = _snap(lat), _snap(lon)
    key = ("outlook", source, glat, glon, today.isoformat(), days)

    def produce():
        end = today + dt.timedelta(days=days)
        try:
            fc = get_forecast(GetForecastRequest(
                lat=glat, lon=glon, start_date=today, end_date=end, source=source))
            used = source
        except Exception:
            if source == "mock":
                raise
            fc = get_forecast(GetForecastRequest(
                lat=glat, lon=glon, start_date=today, end_date=end, source="mock"))
            used = "synthetic fallback (live forecast was rate-limited)"
        wb = compute_wbgt(ComputeWbgtRequest(hours=fc.hours, lat=glat, lon=glon))
        z = zoneinfo.ZoneInfo(tz)
        by_day: dict[str, list[float]] = {}
        for h in wb.hours:
            loc = h.time_utc.astimezone(z)
            if 5 <= loc.hour <= 19:
                by_day.setdefault(loc.date().isoformat(), []).append(float(h.wbgt_c))
        rows = [
            {"date": d, "peak_wbgt": round(max(v), 1), "mean_wbgt": round(sum(v) / len(v), 1),
             "over_threshold": bool(max(v) > THRESHOLD_C)}
            for d, v in sorted(by_day.items()) if v
        ][:days + 1]
        return {"grid": {"lat": glat, "lon": glon}, "source": used, "days": rows}

    return forecast_cache.get_or_set(key, produce)


def _day_wbgt(lat: float, lon: float, date: dt.date, *, source: str,
              tz: str = "Asia/Qatar") -> tuple[dict[int, float], str]:
    """{local_hour: WBGT} for local daytime hours 5..19 on `date`, plus the
    source actually used. Shares the plan cache and the rate-limit fallback."""
    import zoneinfo

    glat, glon = _snap(lat), _snap(lon)
    key = ("daywbgt", source, glat, glon, date.isoformat())

    def produce():
        try:
            fc = get_forecast(GetForecastRequest(
                lat=glat, lon=glon, start_date=date - dt.timedelta(days=1),
                end_date=date + dt.timedelta(days=1), source=source))
            used = source
        except Exception:
            if source == "mock":
                raise
            fc = get_forecast(GetForecastRequest(
                lat=glat, lon=glon, start_date=date - dt.timedelta(days=1),
                end_date=date + dt.timedelta(days=1), source="mock"))
            used = "synthetic fallback (live forecast was rate-limited)"
        wb = compute_wbgt(ComputeWbgtRequest(hours=fc.hours, lat=glat, lon=glon))
        z = zoneinfo.ZoneInfo(tz)
        out: dict[str, float] = {}
        for h in wb.hours:
            loc = h.time_utc.astimezone(z)
            if loc.date() == date and 5 <= loc.hour <= 19:
                out[str(loc.hour)] = round(float(h.wbgt_c), 2)
        return {"hours": out, "source": used}

    got = forecast_cache.get_or_set(key, produce)
    return {int(k): v for k, v in got["hours"].items()}, got["source"]


_ACGIH_BAND = {
    1.0: "continuous work is within the screening limit",
    0.75: "about 45 minutes work, 15 minutes rest each hour",
    0.5: "about 30 minutes work, 30 minutes rest each hour",
    0.25: "about 15 minutes work, 45 minutes rest each hour",
    0.0: "no safe work cycle, stop work",
}


def nowcast(lat: float, lon: float, *, today: dt.date | None = None,
            source: str = "open-meteo", tz: str = "Asia/Qatar") -> dict:
    """Latest forecast hour for a site: its WBGT, the ACGIH work/rest band for
    moderate work, and whether it is over the 32.1 C stop-work line. Answers
    'is it safe to work outside right now'."""
    import zoneinfo

    from src.heat_stress import allowable_work_fraction

    today = today or dt.date.today()
    z = zoneinfo.ZoneInfo(tz)
    now_local = dt.datetime.now(z)
    hours, used = _day_wbgt(lat, lon, today, source=source, tz=tz)
    if not hours:
        return {"grid": {"lat": _snap(lat), "lon": _snap(lon)}, "source": used,
                "available": False,
                "note": "No forecast hour is available for this site right now."}
    cur_h = now_local.hour if now_local.date() == today else max(hours)
    pick = max((h for h in hours if h <= cur_h), default=min(hours))
    wbgt = hours[pick]
    import numpy as _np
    frac_acc = float(allowable_work_fraction(_np.array([wbgt]), "moderate", True)[0])
    frac_un = float(allowable_work_fraction(_np.array([wbgt]), "moderate", False)[0])
    return {
        "grid": {"lat": _snap(lat), "lon": _snap(lon)},
        "source": used,
        "available": True,
        "as_of_local": f"{pick:02d}:00",
        "wbgt": round(wbgt, 1),
        "over_threshold": bool(wbgt > THRESHOLD_C),
        "acgih_band_acclimatised": _ACGIH_BAND[frac_acc],
        "acgih_band_unacclimatised": _ACGIH_BAND[frac_un],
        "note": ("Screening band for moderate work. The 32.1 C stop-work line "
                 "is a hard limit whatever the band."),
    }


def coolest_window(lat: float, lon: float, date: dt.date, *,
                   today: dt.date | None = None, source: str = "open-meteo",
                   tz: str = "Asia/Qatar", block: int = 3) -> dict:
    """The coolest run of working hours on `date`, and when WBGT crosses 32.1 C.
    From the forecast only."""
    hours, used = _day_wbgt(lat, lon, date, source=source, tz=tz)
    if not hours:
        return {"grid": {"lat": _snap(lat), "lon": _snap(lon)}, "source": used,
                "available": False, "note": "No forecast for this day."}
    order = sorted(hours)
    up = next((h for h in order if hours[h] > THRESHOLD_C), None)
    down = next((h for h in order if up is not None and h > up
                 and hours[h] <= THRESHOLD_C), None)
    best_lo, best_mean = order[0], float("inf")
    for i in range(len(order) - block + 1):
        run = order[i:i + block]
        if run[-1] - run[0] != block - 1:
            continue
        m = sum(hours[h] for h in run) / block
        if m < best_mean:
            best_mean, best_lo = m, run[0]
    over = [f"{h:02d}:00" for h in order if hours[h] > THRESHOLD_C]
    return {
        "grid": {"lat": _snap(lat), "lon": _snap(lon)},
        "source": used,
        "available": True,
        "date": date.isoformat(),
        "coolest_start": f"{best_lo:02d}:00",
        "coolest_end": f"{best_lo + block:02d}:00",
        "coolest_mean_wbgt": round(best_mean, 1),
        "crosses_32_1_up": f"{up:02d}:00" if up is not None else None,
        "crosses_32_1_down": f"{down:02d}:00" if down is not None else None,
        "hours_over_threshold": over,
    }


_DAYLIGHT_LO, _DAYLIGHT_HI = 5, 18            # the plan's working window
_SOLAR_NOTE = ("Night WBGT carries no solar load: the Liljegren globe term is "
               "zero when the sun is down.")


def day_curve(lat: float, lon: float, date: dt.date, *,
              today: dt.date | None = None, source: str = "open-meteo",
              tz: str = "Asia/Qatar") -> dict:
    """The full local 24-hour WBGT series for `date` at one grid cell, a
    research context view separate from the daylight-scoped plan. Shares the
    plan cache and the rate-limit fallback. Deterministic, no model."""
    import zoneinfo

    glat, glon = _snap(lat), _snap(lon)
    key = ("daycurve", source, glat, glon, date.isoformat())

    def produce():
        try:
            fc = get_forecast(GetForecastRequest(
                lat=glat, lon=glon, start_date=date - dt.timedelta(days=1),
                end_date=date + dt.timedelta(days=1), source=source))
            used = source
        except Exception:
            if source == "mock":
                raise
            fc = get_forecast(GetForecastRequest(
                lat=glat, lon=glon, start_date=date - dt.timedelta(days=1),
                end_date=date + dt.timedelta(days=1), source="mock"))
            used = "synthetic fallback (live forecast was rate-limited)"
        wb = compute_wbgt(ComputeWbgtRequest(hours=fc.hours, lat=glat, lon=glon))
        z = zoneinfo.ZoneInfo(tz)
        by_hour: dict[int, float] = {}
        for h in wb.hours:
            loc = h.time_utc.astimezone(z)
            if loc.date() == date:
                by_hour[loc.hour] = round(float(h.wbgt_c), 2)
        if len(by_hour) < 24:
            return {"available": False, "source": used,
                    "note": "The forecast does not cover the full local day."}

        points = [
            {"hour": hh, "wbgt_c": by_hour[hh],
             "over_threshold": bool(by_hour[hh] > THRESHOLD_C),
             "is_daylight": _DAYLIGHT_LO <= hh <= _DAYLIGHT_HI}
            for hh in range(24)
        ]
        work = list(range(_DAYLIGHT_LO, _DAYLIGHT_HI + 1))
        best_lo, best_mean = work[0], float("inf")
        for i in range(len(work) - 2):
            run = work[i:i + 3]
            m = sum(by_hour[h] for h in run) / 3.0
            if m < best_mean:
                best_mean, best_lo = m, run[0]
        over = [f"{hh:02d}:00" for hh in range(24) if by_hour[hh] > THRESHOLD_C]
        night = [by_hour[hh] for hh in (*range(19, 24), *range(0, 6))]
        night_min = round(min(night), 1)
        return {
            "available": True,
            "grid": {"lat": glat, "lon": glon},
            "source": used,
            "date": date.isoformat(),
            "points": points,
            "coolest_window": {
                "start": f"{best_lo:02d}:00", "end": f"{best_lo + 3:02d}:00",
                "mean_wbgt": round(best_mean, 1),
            },
            "hours_over_threshold": over,
            "overnight_min_wbgt": night_min,
            "stays_hot_overnight": bool(night_min > 30.0),
            "solar_note": _SOLAR_NOTE,
        }

    return forecast_cache.get_or_set(key, produce)


_CLIMO_PATH = pathlib.Path(__file__).parent / "data" / "climatology.json"
_climo_cache: dict = {}


def _climo_data() -> dict:
    """The distilled 16-year Doha WBGT record climatology_compare and
    heat_trend need: daily daylight peaks binned by day-of-year, and the
    warm-season stop-work-hour count per year. Cached for the process.

    This is built by scripts/build_climatology_table.py from the full
    OTHH-station record (data/doha_wbgt_16yr.csv) and shipped under
    api/data/, unlike that source file: api/data/ is what both Dockerfiles
    COPY and what git tracks (data/** in .gitignore does not reach the
    nested api/data/), so this is what is actually present in a deployed
    container. Reading the source CSV directly here was a real production
    bug - see the module docstring of build_climatology_table.py."""
    if "data" not in _climo_cache:
        import numpy as _np

        raw = json.loads(_CLIMO_PATH.read_text())
        peaks = raw["daily_peaks"]
        _climo_cache["doy"] = _np.array([p["doy"] for p in peaks])
        _climo_cache["peak"] = _np.array([p["peak_wbgt_c"] for p in peaks])
        _climo_cache["n_years"] = len({p["year"] for p in peaks})
        _climo_cache["annual_stop_work_hours"] = {
            int(y): v for y, v in raw["annual_stop_work_hours"].items()}
        _climo_cache["last_date"] = dt.date.fromisoformat(raw["last_date"])
    return _climo_cache


def climatology_compare(lat: float, lon: float, date: dt.date, *,
                        today: dt.date | None = None,
                        source: str = "open-meteo", window_days: int = 7) -> dict:
    """The forecast peak WBGT for `date` against the 16-year distribution of
    daily peak WBGT for that time of year. Answers 'is this heat unusual'."""
    hours, used = _day_wbgt(lat, lon, date, source=source)
    if not hours:
        return {"available": False, "source": used,
                "note": "No forecast for this day."}
    fc_peak = round(max(hours.values()), 1)

    import numpy as _np

    data = _climo_data()
    doy = date.timetuple().tm_yday
    lo, hi = doy - window_days, doy + window_days
    mask = (data["doy"] >= lo) & (data["doy"] <= hi)
    peaks = data["peak"][mask]
    if len(peaks) < 30:
        return {"available": True, "source": used, "date": date.isoformat(),
                "forecast_peak_wbgt": fc_peak, "comparable": False,
                "note": "Not enough record for this time of year to compare."}
    pct = float((peaks < fc_peak).mean() * 100.0)
    med = float(_np.median(peaks))
    p90 = float(_np.percentile(peaks, 90))
    p10 = float(_np.percentile(peaks, 10))
    if fc_peak >= p90:
        verdict = "unusually hot for the time of year"
    elif fc_peak <= p10:
        verdict = "unusually mild for the time of year"
    else:
        verdict = "about typical for the time of year"
    return {
        "available": True,
        "comparable": True,
        "source": used,
        "date": date.isoformat(),
        "forecast_peak_wbgt": fc_peak,
        "climatology_median_peak": round(med, 1),
        "climatology_p90_peak": round(p90, 1),
        "percentile": round(pct),
        "verdict": verdict,
        "record_years": data["n_years"],
        "window_days": window_days,
        "note": ("Distribution is the Doha OTHH station record; it does not "
                 "resolve individual sites."),
    }


def heat_trend(lat: float, lon: float, *, today: dt.date | None = None) -> dict:
    """Warm-season (June to September) WBGT stop-work-hour count per year over
    the 16-year Doha record, and the direction of the trend. Answers 'has heat
    been increasing here'."""
    import numpy as _np

    data = _climo_data()
    per_year = data["annual_stop_work_hours"]
    last_date = data["last_date"]
    partial_tail = (last_date.month, last_date.day) < (9, 30)
    years_sorted = sorted(per_year)
    if partial_tail and len(years_sorted) > 3:
        years_sorted = years_sorted[:-1]
    yrs = _np.array(years_sorted, dtype=float)
    vals = _np.array([per_year[y] for y in years_sorted], dtype=float)
    slope = float(_np.polyfit(yrs, vals, 1)[0]) if len(yrs) >= 3 else 0.0
    return {
        "source": "Harara technical report section 4.1; 16-year Doha WBGT record",
        "first_year": int(yrs[0]),
        "last_year": int(yrs[-1]),
        "stop_work_hours_per_year": {int(y): int(v) for y, v in zip(yrs, vals)},
        "early_years_mean": round(float(vals[:3].mean())),
        "recent_years_mean": round(float(vals[-3:].mean())),
        "slope_hours_per_year": round(slope, 1),
        "direction": "rising" if slope > 3 else "falling" if slope < -3 else "flat",
        "note": ("Counts hours with WBGT over 32.1 C, June to September, 06:00 "
                 "to 18:00 local, at the Doha OTHH station. Not resolved to "
                 "other sites."),
    }


def _cycle(frac: float) -> str:
    if frac <= 1e-9:
        return "rest in shade"
    if frac >= _FULL_WORK:
        return "work the full hour"
    if frac >= 0.625:
        return "work about 45 minutes, rest 15 in shade"
    if frac >= 0.375:
        return "work about 30 minutes, rest 30 in shade"
    return "work about 15 minutes, rest 45 in shade"


def _band(hour: int, lead: int, wbgt: float) -> tuple[float, float, bool]:
    q = _RESID["leads"].get(str(min(3, max(1, lead))), {}).get(str(hour))
    if not q:
        lo, hi = wbgt - 1.5, wbgt + 1.0
    else:
        widen = 1.0 if lead <= 3 else 1.0 + 0.15 * (lead - 3)
        lo = wbgt + q["p10"] * widen
        hi = wbgt + q["p90"] * widen
    lo, hi = min(lo, hi), max(lo, hi)
    lo, hi = round(lo, 1), round(hi, 1)
    # Compare on the rounded band, not the raw one: a raw hi of 32.099 rounds
    # to 32.1 and reports "uncertain" to the caller either way, so the flag
    # has to agree with what is actually shown, not with the unrounded value.
    return lo, hi, bool(lo <= THRESHOLD_C <= hi)


def _dry_hot(fc_hours, target_date: dt.date, tz: str, wbgt_by_hour: dict) -> bool:
    import zoneinfo

    z = zoneinfo.ZoneInfo(tz)
    rows = []
    for h in fc_hours:
        loc = h.time_utc.astimezone(z)
        if loc.date() == target_date and 10 <= loc.hour <= 16:
            rows.append((loc.hour, h.temp_c, h.rh_pct))
    if len(rows) < 4 or target_date.month not in (4, 5, 6, 7, 8, 9, 10):
        return False
    mean_t = float(np.mean([r[1] for r in rows]))
    mean_rh = float(np.mean([r[2] for r in rows]))
    mean_w = float(np.mean([wbgt_by_hour.get(r[0], mean_t) for r in rows]))
    return mean_rh < 25.0 and mean_t > 40.0 and (mean_t - mean_w) > 12.0


def plan_with_sched(
    req: PlanRequest,
    *,
    forecast_source: str = "open-meteo",
    wbgt_hours: list[WbgtHour] | None = None,
    today: dt.date | None = None,
) -> tuple[PlanResponse, RunSchedulerResponse]:
    today = today or dt.date.today()
    lead_days = max(1, (req.date - today).days)

    fc = None
    source_used = forecast_source
    if wbgt_hours is None:
        fc, source_used = _forecast(req, forecast_source)
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
        max_span_hours=req.max_span_hours,
        rest_allowance_hours=req.rest_allowance_hours,
        earlier_start=req.earlier_start,
    ))

    plan = sched.plan
    local_hours = np.array([hp.local_time.hour for hp in plan], dtype=float)
    wbgt = np.array([hp.wbgt_c for hp in plan], dtype=float)
    w_plan = np.array([hp.work_fraction for hp in plan], dtype=float)
    wbgt_ref = sched.wbgt_ref_c
    ones = np.ones(len(plan), dtype=bool)

    w_cal = policy_calendar(local_hours, ones)
    w_react = policy_reactive(wbgt, ones, req.required_work_hours)
    w_ear = np.array([hp.earlier_start_work_fraction for hp in plan], dtype=float)

    path_plan = retained_load_path(w_plan, wbgt, phi=PHI_DEFAULT, wbgt_ref=wbgt_ref)
    path_cal = retained_load_path(w_cal, wbgt, phi=PHI_DEFAULT, wbgt_ref=wbgt_ref)
    path_react = retained_load_path(w_react, wbgt, phi=PHI_DEFAULT, wbgt_ref=wbgt_ref)
    path_ear = retained_load_path(w_ear, wbgt, phi=PHI_DEFAULT, wbgt_ref=wbgt_ref)

    cal_span = float(_worked_span(w_cal))
    cal_rest = max(0.0, cal_span - float(w_cal.sum()))
    cal_blocks = len(_work_blocks(w_cal))
    dose_plan = cumulative_exposure(w_plan, wbgt, wbgt_ref)
    dose_cal = cumulative_exposure(w_cal, wbgt, wbgt_ref)

    peak_plan = float(sched.plan_peak_strain)
    peak_cal = float(sched.baseline_peak_strain)
    peak_react = float(path_react.max())
    tail_plan = float(sched.plan_tail_strain)
    tail_cal = float(sched.baseline_tail_strain)
    tail_react = float(np.percentile(path_react, TAIL_PCT))

    def _state(frac: float) -> str:
        if frac <= 1e-9:
            return "stop"
        return "work" if frac >= _FULL_WORK else "reduced"

    wbgt_by_hour = {int(h): float(v) for h, v in zip(local_hours, wbgt)}
    any_wide = lead_days > 3
    hours = []
    for i, hp in enumerate(plan):
        lo, hi, unc = _band(int(local_hours[i]), lead_days, float(wbgt[i]))
        hours.append(HourRow(
            local_time=hp.local_time,
            hour=int(hp.local_time.hour),
            wbgt_c=round(float(hp.wbgt_c), 1),
            wbgt_lo=lo, wbgt_hi=hi, uncertain=unc,
            plan_work_fraction=round(float(w_plan[i]), 3),
            calendar_work_fraction=round(float(w_cal[i]), 3),
            reactive_work_fraction=round(float(w_react[i]), 3),
            earlier_start_work_fraction=round(float(w_ear[i]), 3),
            retained_load_plan=round(float(path_plan[i]), 3),
            retained_load_calendar=round(float(path_cal[i]), 3),
            retained_load_reactive=round(float(path_react[i]), 3),
            retained_load_earlier=round(float(path_ear[i]), 3),
            plan_state=_state(float(w_plan[i])),
            over_threshold=bool(wbgt[i] > THRESHOLD_C),
            on_site=bool(plan[i].on_site),
            cycle=_cycle(float(w_plan[i])),
        ))

    summary = PlanSummary(
        peak_plan=round(peak_plan, 3),
        peak_calendar=round(peak_cal, 3),
        peak_reactive=round(peak_react, 3),
        tail_plan=round(tail_plan, 3),
        tail_calendar=round(tail_cal, 3),
        tail_reactive=round(tail_react, 3),
        pct_peak_reduction=round(_pct(peak_cal, peak_plan), 1),
        pct_tail_reduction=round(_pct(tail_cal, tail_plan), 1),
        pct_peak_reduction_vs_reactive=round(_pct(peak_react, peak_plan), 1),
        work_hours_delivered_plan=round(float(sched.work_hours_delivered), 2),
        work_hours_delivered_calendar=round(float(w_cal.sum()), 2),
        work_shortfall_plan=round(float(sched.work_shortfall), 2),
        stop_hours_plan=int((w_plan <= 1e-9).sum()),
        stop_hours_calendar=int((w_cal <= 1e-9).sum()),
        wbgt_ref_c=round(float(wbgt_ref), 1),
        threshold_c=THRESHOLD_C,
        solver_status=sched.solver_status,
        span_hours_plan=round(float(sched.plan_span_hours), 2),
        span_hours_calendar=round(cal_span, 2),
        onsite_rest_hours_plan=round(float(sched.plan_onsite_rest_hours), 2),
        onsite_rest_hours_calendar=round(cal_rest, 2),
        cumulative_exposure_plan=round(dose_plan, 2),
        cumulative_exposure_calendar=round(dose_cal, 2),
        work_blocks_plan=int(sched.plan_work_blocks),
        work_blocks_calendar=int(cal_blocks),
        earlier_start_fixed={
            "peak": round(float(sched.earlier_start_peak_strain), 3),
            "tail": round(float(sched.earlier_start_tail_strain), 3),
            "span_hours": round(float(sched.earlier_start_span_hours), 2),
        },
    )

    dry_hot = bool(fc is not None and _dry_hot(fc.hours, req.date, req.tz,
                                               wbgt_by_hour))
    _src_label = {
        "mock": "synthetic (deterministic mock)",
        "mock-fallback": "synthetic fallback (live forecast was rate-limited)",
        "open-meteo": "Open-Meteo forecast API (ERA5-blend NWP)",
        "open-meteo-stale": "Open-Meteo forecast API (cached, last good run)",
    }
    meta = PlanMeta(
        model="liljegren-thermofeel / cvar-lp",
        forecast_source=_src_label.get(
            source_used, "Open-Meteo forecast API (ERA5-blend NWP)"),
        forecast_run=("synthetic" if source_used.startswith("mock")
                      else "cached run" if source_used.endswith("stale")
                      else "latest available model run"),
        lead_days=int(lead_days),
        lead_time_note=_LEAD_NOTE,
        uncertainty_note=_UNCERTAINTY_NOTE,
        wide_band=any_wide,
        dry_hot_day=dry_hot,
        dry_hot_note=_DRY_HOT_NOTE if dry_hot else "",
        generated_at=dt.datetime.now(dt.timezone.utc),
        date=req.date,
        location={"lat": round(fc_lat, 4), "lon": round(fc_lon, 4),
                  "grid_note": "nearest forecast grid cell, about 25 km across"},
        request={"lat": req.lat, "lon": req.lon, "date": req.date.isoformat(),
                 "required_work_hours": req.required_work_hours,
                 "workload_class": req.workload_class,
                 "acclimatised": req.acclimatised, "tz": req.tz},
        attribution="Weather data by Open-Meteo.com, CC BY 4.0",
    )

    # 24-hour context view, only when we fetched a forecast ourselves (the
    # wbgt_hours override path carries only the working window).
    curve = None
    if fc is not None:
        try:
            dc = day_curve(req.lat, req.lon, req.date,
                           today=today, source=forecast_source, tz=req.tz)
            curve = dc if dc.get("available") else None
        except Exception:
            curve = None

    return PlanResponse(hours=hours, summary=summary, meta=meta,
                        day_curve=curve), sched


def build_plan(req: PlanRequest, *, forecast_source: str = "open-meteo",
               wbgt_hours: list[WbgtHour] | None = None,
               today: dt.date | None = None) -> PlanResponse:
    return plan_with_sched(req, forecast_source=forecast_source,
                           wbgt_hours=wbgt_hours, today=today)[0]


def _pct(base: float, other: float) -> float:
    if base <= 1e-9:
        return 0.0
    return (base - other) / base * 100.0
