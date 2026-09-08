"""
Glue that turns a PlanIntent into a scheduler result: fetch a forecast for
the intent's location, compute WBGT, merge any confirmed rule records into
one constraint set, and call the deterministic scheduler. Used by the NL
front door and by the monitoring loop.
"""

from __future__ import annotations

import datetime as dt

from src.agent.schemas import (
    ComputeWbgtRequest, GetForecastRequest, PlanIntent, RuleConstraints,
    RuleRecord, RunSchedulerResponse,
)
from src.agent.tools import compute_wbgt, get_forecast, run_scheduler


def merge_rules(records: list[RuleRecord]) -> RuleConstraints:
    """Combine rule records into one constraint set: union of banned hour
    windows, the strictest (lowest) stop-work threshold, and the seasonal
    window from a statutory record if there is one, else the first given."""
    if not records:
        return RuleConstraints()

    banned, stops, season = [], [], None
    for rec in records:
        c = rec.to_constraints()
        banned.extend(c.banned_hour_windows)
        if c.wbgt_stop_work_c is not None:
            stops.append(c.wbgt_stop_work_c)
        if c.seasonal_window is not None:
            statutory = "statutory" in rec.tags
            if season is None or statutory:
                season = c.seasonal_window
    return RuleConstraints(
        rule_ids=[r.rule_id for r in records],
        banned_hour_windows=banned,
        wbgt_stop_work_c=min(stops) if stops else None,
        seasonal_window=season,
    )


def plan_for_intent(
    intent: PlanIntent,
    *,
    rules: list[RuleRecord] | None = None,
    forecast_source: str = "open-meteo",
    seed: int = 0,
) -> RunSchedulerResponse:
    d = intent.target_local_date
    fc = get_forecast(GetForecastRequest(
        lat=intent.location.lat, lon=intent.location.lon,
        start_date=d - dt.timedelta(days=1),
        end_date=d + dt.timedelta(days=1),
        source=forecast_source))
    wb = compute_wbgt(ComputeWbgtRequest(
        hours=fc.hours, lat=intent.location.lat, lon=intent.location.lon))
    req = intent.to_request(
        wbgt_hours=wb.hours, constraints=merge_rules(rules or []), seed=seed)
    return run_scheduler(req)
