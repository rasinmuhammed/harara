"""
Monitoring loop. The scheduler does the optimisation; this module only
decides whether a freshly re-optimised plan differs enough from the one
last issued that a human should look, and drafts the explanation.

"Material" is fixed here, not left to the model: a new plan is material if
any working hour changes allowed/blocked state, or peak or tail retained
load moves by more than MATERIAL_STRAIN_FRAC, or the number of stop-work
hours changes, or a work shortfall appears where there was none.
"""

from __future__ import annotations

import datetime as dt

from src.agent.brief import allowed_numbers
from src.agent.llm import get_llm
from src.agent.schemas import PlanIntent, RunSchedulerResponse

MATERIAL_STRAIN_FRAC = 0.15


class UngroundedAlert(RuntimeError):
    """The drafted alert cited a number not present in either plan."""


def _rel_move(a: float, b: float) -> float:
    return abs(float(a) - float(b)) / max(abs(float(b)), 1e-6)


def material_changes(issued: RunSchedulerResponse,
                     new: RunSchedulerResponse) -> list[str]:
    fired: list[str] = []

    issued_allowed = {p.local_time.hour: p.allowed for p in issued.plan}
    new_allowed = {p.local_time.hour: p.allowed for p in new.plan}
    if issued_allowed != new_allowed:
        fired.append("allowed_hours_changed")

    if _rel_move(new.plan_peak_strain, issued.plan_peak_strain) > MATERIAL_STRAIN_FRAC:
        fired.append("peak_strain")
    if _rel_move(new.plan_tail_strain, issued.plan_tail_strain) > MATERIAL_STRAIN_FRAC:
        fired.append("tail_strain")
    if len(new.stop_work_hours) != len(issued.stop_work_hours):
        fired.append("stop_work_count")
    if new.work_shortfall > 0 and issued.work_shortfall == 0:
        fired.append("shortfall_appeared")
    return fired


def _alert_numeric_guard(text: str, *plans: RunSchedulerResponse) -> list[str]:
    from src.agent.brief import _NUM, _STRIP, _TOL

    allowed: set[float] = set()
    for p in plans:
        allowed |= allowed_numbers(p)
    bad = []
    for tok in _NUM.findall(_STRIP.sub(" ", text)):
        if not any(abs(float(tok) - a) <= _TOL for a in allowed):
            bad.append(tok)
    return bad


class Alert:
    def __init__(self, target_date: dt.date, fired: list[str], text: str):
        self.target_date = target_date
        self.fired = fired
        self.text = text

    def __str__(self) -> str:
        return self.text


def review_plan(
    issued: RunSchedulerResponse,
    new: RunSchedulerResponse,
    *,
    target_date: dt.date,
    llm=None,
) -> Alert | None:
    """Return an Alert if the change is material, else None."""
    fired = material_changes(issued, new)
    if not fired:
        return None
    llm = llm or get_llm()
    text = llm.draft_alert(issued, new, fired, target_date=target_date)
    bad = _alert_numeric_guard(text, issued, new)
    if bad:
        raise UngroundedAlert(f"alert cites numbers not in either plan: {bad}")
    return Alert(target_date, fired, text)


def monitor_intent(
    intent: PlanIntent,
    issued: RunSchedulerResponse,
    *,
    rules=None,
    forecast_source: str = "open-meteo",
    llm=None,
) -> Alert | None:
    """Re-plan `intent` against the current forecast and compare with the
    plan last issued for it."""
    from src.agent.service import plan_for_intent

    fresh = plan_for_intent(intent, rules=rules, forecast_source=forecast_source)
    return review_plan(issued, fresh, target_date=intent.target_local_date,
                       llm=llm)
