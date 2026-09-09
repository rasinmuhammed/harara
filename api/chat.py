"""
Streaming chat: a normal request in, an explanation and a result artifact out.

The language model never produces a number that reaches the user. It only
turns the request into a validated PlanIntent (src.agent.parse, fail-closed)
and turns the deterministic plan into sentences (src.agent.brief, with the
numeric and rule guards in force). Every figure the client renders comes from
the /api/plan payload streamed in the `artifact` frame.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from collections.abc import Iterator

from api.planning import plan_with_sched
from api.schemas import PlanRequest
from src.agent.brief import UngroundedBriefing, generate_briefing
from src.agent.llm import get_llm
from src.agent.parse import parse_scheduling_request
from src.agent.schemas import ClarificationNeeded, ParsedRequest

_WORD_DELAY_S = 0.012
_LLM_NAME = os.environ.get("HARARA_LLM", "mock")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"


def _last_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content", "").strip():
            return m["content"].strip()
    return ""


def _prev_user(messages: list[dict], skip_last: bool = True) -> str:
    seen = 0
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content", "").strip():
            seen += 1
            if seen == (2 if skip_last else 1):
                return m["content"].strip()
    return ""


def _intent_to_request(intent, tz_default: str = "Asia/Qatar") -> PlanRequest:
    return PlanRequest(
        lat=intent.location.lat,
        lon=intent.location.lon,
        date=intent.target_local_date,
        required_work_hours=intent.required_work_hours,
        workload_class=intent.crew.workload,
        acclimatised=intent.crew.acclimatised,
        tz=intent.timezone or tz_default,
    )


def _fallback_sentences(plan, location_name: str) -> str:
    s = plan.summary
    m = plan.meta
    date = plan.meta.date.isoformat()
    parts = [
        f"For {location_name} on {date}, the plan delivers "
        f"{s.work_hours_delivered_plan} of {s.work_hours_delivered_plan} "
        f"work-hours.",
        f"The worst retained heat load is {s.peak_plan} under the plan and "
        f"{s.peak_calendar} under the fixed 10:00 to 15:30 ban, for the same "
        f"hours worked.",
    ]
    if s.stop_hours_plan:
        parts.append(f"{s.stop_hours_plan} hours are at rest.")
    parts.append(f"Forecast source: {m.forecast_source}.")
    return " ".join(parts)


def chat_stream(
    messages: list[dict],
    context: dict | None = None,
    *,
    forecast_source: str = "open-meteo",
) -> Iterator[str]:
    context = context or {}
    today = (dt.date.fromisoformat(context["today"])
             if context.get("today") else dt.date.today())
    llm = get_llm(_LLM_NAME)

    text = _last_user(messages)
    if not text:
        yield _sse({"type": "error", "message": "Say what you need planned."})
        yield _sse({"type": "done"})
        return

    yield _sse({"type": "status", "state": "parsing"})
    parsed = parse_scheduling_request(text, today=today, llm=llm)

    if isinstance(parsed, ClarificationNeeded):
        # a follow-up like "8 hours" may complete an earlier request
        prev = _prev_user(messages)
        if prev:
            retry = parse_scheduling_request(
                f"{prev}\n{text}", today=today, llm=llm)
            if isinstance(retry, ParsedRequest):
                parsed = retry
        if isinstance(parsed, ClarificationNeeded):
            yield _sse({"type": "clarification",
                        "question": parsed.question,
                        "missing_fields": parsed.missing_fields})
            yield _sse({"type": "done"})
            return

    intent = parsed.intent
    location_name = intent.location.name.title()

    try:
        yield _sse({"type": "status", "state": "forecasting"})
        req = _intent_to_request(intent)
        yield _sse({"type": "status", "state": "planning"})
        plan, sched = plan_with_sched(req, forecast_source=forecast_source)
    except Exception as exc:  # noqa: BLE001 - forecast upstream or solver
        yield _sse({"type": "error",
                    "message": "The forecast service did not respond. "
                               "Try again in a moment."})
        yield _sse({"type": "done"})
        return

    yield _sse({"type": "status", "state": "writing"})
    try:
        explanation = generate_briefing(
            sched, location_name=location_name, llm=llm).text
    except UngroundedBriefing:
        explanation = _fallback_sentences(plan, location_name)

    for word in explanation.split():
        yield _sse({"type": "text", "delta": word + " "})
        time.sleep(_WORD_DELAY_S)

    yield _sse({"type": "artifact", "plan": plan.model_dump(mode="json")})
    yield _sse({"type": "done"})
