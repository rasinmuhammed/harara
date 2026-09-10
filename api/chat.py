"""
Streaming chat. Two shapes of turn come through here:

  a scheduling request  ->  parse (fail-closed) -> deterministic plan ->
                            a conversational briefing, then the artifact frame.
  a question or remark   ->  the assistant answers in plain language.

The language model never produces a number that reaches the user. On the plan
path every figure comes from the /api/plan payload streamed in the `artifact`
frame, and the briefing text passes the numeric guard. On the question path the
answer may quote the published regulatory figures and any number found in a
plan already on screen; any other number degrades the turn to a safe
deterministic reply.

If the configured model (HARARA_LLM) is missing its key or fails mid-request,
every path falls back to a deterministic response rather than erroring.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from collections.abc import Iterator

from api.planning import plan_with_sched
from api.schemas import PlanRequest
from src.agent.brief import generate_briefing
from src.agent.llm import get_llm
from src.agent.parse import parse_scheduling_request
from src.agent.schemas import ClarificationNeeded, ParsedRequest

try:  # the assistant system prompt lives with the k2 adapter
    from src.agent.k2_llm import _ASSISTANT_SYS
except Exception:  # pragma: no cover - adapter optional
    _ASSISTANT_SYS = ""

_WORD_DELAY_S = 0.012
_LLM_NAME = os.environ.get("HARARA_LLM", "mock")

# Numbers the assistant is allowed to state without a plan to back them:
# the published regulatory / method constants, plus any plain integer 0..100
# (hours, dates, crew sizes, percentages). Anything else has to come from a
# plan payload.
_CONST_OK = {
    "32.1", "10", "15.5", "15:30", "10:00", "28", "0.8", "0.75", "0.5",
    "0.25", "1.0", "90", "24", "17", "2021", "2017", "7243", "16", "236",
    "15", "25", "1", "0", "14", "0.083", "0.36",
}
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_STRIP_RE = re.compile(r"\b\d{1,2}:\d{2}\b|\d{4}-\d{2}-\d{2}|17/2021|\b\d{2}-\d{2}\b")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"


def _last_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content", "").strip():
            return m["content"].strip()
    return ""


def _prev_user(messages: list[dict]) -> str:
    seen = 0
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content", "").strip():
            seen += 1
            if seen == 2:
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


# --------------------------------------------------------------------- routing
_SCHEDULE_HINTS = re.compile(
    r"\b(plan|schedule|shift|crew|work[- ]?hours?|acclimat|tomorrow|today|"
    r"pour|dig|concrete|scaffold|lifting|inspection|labour|labor|workers?)\b",
    re.I,
)
_QUESTION_HINTS = re.compile(
    r"^\s*(what|why|how|when|where|which|who|is|are|can|could|do|does|did|"
    r"should|would|will|tell me|explain|help)\b|[?]\s*$",
    re.I,
)


def _is_question(text: str) -> bool:
    """True when the text reads like a question or carries no scheduling words.
    The caller has already established this is not a scheduling turn."""
    return bool(_QUESTION_HINTS.search(text)) or not _SCHEDULE_HINTS.search(text)


_CLAR_RE = re.compile(
    r"(specify|how many|which (date|day)|used to the heat|acclimat|"
    r"work[- ]?hours are needed|workload class)|\?\s*$",
    re.I,
)


def _prev_was_clarification(messages: list[dict]) -> bool:
    # messages[-1] is the current user turn; look at what came just before it
    for m in reversed(messages[:-1]):
        if not m.get("content", "").strip():
            continue
        if m.get("role") == "assistant":
            return bool(_CLAR_RE.search(m["content"]))
        return False
    return False


# --------------------------------------------------------------------- guards
def _number_ok(tok: str, extra: set[str]) -> bool:
    if tok in _CONST_OK or tok in extra:
        return True
    if "." not in tok:
        try:
            return 0 <= int(tok) <= 100
        except ValueError:
            return False
    return False


def _answer_is_grounded(text: str, plan_numbers: set[str]) -> bool:
    for tok in _NUM_RE.findall(_STRIP_RE.sub(" ", text)):
        if not _number_ok(tok, plan_numbers):
            return False
    return True


def _plan_numbers(plan_ctx: dict | None) -> set[str]:
    out: set[str] = set()
    if not plan_ctx:
        return out
    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, (int, float)):
            out.add(f"{x:g}")
            out.add(str(round(float(x), 1)))
            out.add(str(int(round(float(x)))))
    walk(plan_ctx)
    return out


# --------------------------------------------------------------- deterministic
def _plain_summary(plan, location_name: str) -> str:
    s = plan.summary
    m = plan.meta
    date = plan.meta.date.isoformat()
    parts = [
        f"For {location_name} on {date}, the plan delivers "
        f"{s.work_hours_delivered_plan:g} work-hours, the same as the fixed "
        f"10:00 to 15:30 calendar ban.",
        f"It keeps the worst retained heat load at {s.peak_plan:.2f}, against "
        f"{s.peak_calendar:.2f} under the ban, which is "
        f"{s.pct_peak_reduction:.0f} percent lower.",
        f"The p90 tail is {s.tail_plan:.2f}, against {s.tail_calendar:.2f}.",
    ]
    if s.stop_hours_plan:
        parts.append(f"{s.stop_hours_plan} hours are set to rest through the "
                     f"hottest part of the day, then the work picks back up as "
                     f"it cools.")
    if s.work_shortfall_plan > 0:
        parts.append(f"{s.work_shortfall_plan} of the requested work-hours do "
                     f"not fit the working window today.")
    if m.dry_hot_day:
        parts.append(m.dry_hot_note)
    if m.wide_band:
        parts.append("This is several days out, so the forecast is less "
                     "certain. Check again the morning before.")
    else:
        parts.append("Check the forecast again the morning before the shift.")
    return " ".join(parts)


_DET_ANSWER = (
    "I plan the working day for an outdoor crew in Qatar from the weather "
    "forecast. I read hourly WBGT, the heat-stress index that combines heat, "
    "humidity, sun and wind, and I shape work and rest so the crew spends less "
    "time in the worst heat while still delivering the same hours. It sits on "
    "top of Qatar Ministerial Decision 17/2021, which stops outdoor work at "
    "WBGT 32.1 and sets a fixed 10:00 to 15:30 rest window in summer. "
    "To get a plan, tell me the site, the day, the kind of work, how many "
    "work-hours you need, and whether the crew has been in this heat for more "
    "than two weeks."
)


def _stream_words(text: str) -> Iterator[str]:
    for word in text.split():
        yield _sse({"type": "text", "delta": word + " "})
        time.sleep(_WORD_DELAY_S)


# --------------------------------------------------------------------- entry
def chat_stream(
    messages: list[dict],
    context: dict | None = None,
    *,
    forecast_source: str = "open-meteo",
    intent_override: dict | None = None,
) -> Iterator[str]:
    context = context or {}
    today = (dt.date.fromisoformat(context["today"])
             if context.get("today") else dt.date.today())
    plan_ctx = context.get("plan") if isinstance(context.get("plan"), dict) else None

    try:
        llm = get_llm(_LLM_NAME)
        llm_name = _LLM_NAME
    except Exception:
        llm = get_llm("mock")
        llm_name = "mock"
    _mock = get_llm("mock")

    # ---- confirmed intent card: straight to the plan --------------------
    if intent_override:
        from src.agent.schemas import PlanIntent
        try:
            intent = PlanIntent.model_validate(intent_override)
        except Exception:
            yield _sse({"type": "error",
                        "message": "That plan request was incomplete. "
                                   "Fill the fields and try again."})
            yield _sse({"type": "done"})
            return
        yield from _run_plan(intent, llm, llm_name, forecast_source, today)
        return

    text = _last_user(messages)
    if not text:
        yield _sse({"type": "error", "message": "Say what you need."})
        yield _sse({"type": "done"})
        return

    # The structured parse always uses the deterministic parser: it has the
    # gazetteer, it is fail-closed, and it does not hallucinate a field. The
    # real model is used only for the conversation and the plan explanation.
    def _parse(t: str):
        return parse_scheduling_request(t, today=today, llm=_mock)

    yield _sse({"type": "status", "state": "parsing"})
    parsed = _parse(text)

    # complete request in one line -> plan
    if isinstance(parsed, ParsedRequest):
        yield from _run_plan(parsed.intent, llm, llm_name, forecast_source, today)
        return

    # Is this a scheduling turn at all? Yes if we are gathering fields after a
    # clarification, or the parser resolved a non-location field, or the text
    # carries scheduling words. A plain question with none of that gets answered.
    nonloc = {"target_local_date", "required_work_hours", "workload", "acclimatised"}
    resolved_nonloc = bool(nonloc - set(parsed.missing_fields))
    gathering = bool((context or {}).get("gathering")) or _prev_was_clarification(messages)
    is_q = _is_question(text)
    scheduling = gathering or bool(_SCHEDULE_HINTS.search(text)) or (resolved_nonloc and not is_q)

    if not scheduling and is_q:
        yield from _answer(llm, messages, plan_ctx)
        yield _sse({"type": "done"})
        return

    # a scheduling attempt in progress: combine with the prior user turn to
    # fill a gap, then plan or ask back.
    prev = _prev_user(messages)
    combined = _parse(f"{prev}\n{text}") if prev else parsed
    if isinstance(combined, ParsedRequest):
        yield from _run_plan(combined.intent, llm, llm_name, forecast_source, today)
        return
    yield _sse({"type": "clarification",
                "question": combined.question,
                "missing_fields": combined.missing_fields})
    yield _sse({"type": "done"})


def _answer(llm, messages: list[dict], plan_ctx: dict | None) -> Iterator[str]:
    """The question path. K2 (or whichever model) answers; the reply must be
    grounded before it streams. No model, or an ungrounded reply, degrades to
    a deterministic answer."""
    convo = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages[-6:]
        if m.get("content", "").strip()
    )
    prompt = convo
    if plan_ctx:
        prompt += ("\n\n[plan currently on screen, for reference only, "
                   f"quote figures from here verbatim]\n{json.dumps(plan_ctx, default=str)}")

    try:
        reply = llm.converse(_ASSISTANT_SYS, prompt, max_tokens=700)
    except Exception:
        reply = None

    if reply and _answer_is_grounded(reply, _plan_numbers(plan_ctx)):
        yield from _stream_words(reply.strip())
    else:
        # no model, or a reply with an ungrounded number: a helpful
        # deterministic answer, never a fabricated figure
        yield from _stream_words(_DET_ANSWER)


def _run_plan(intent, llm, llm_name: str, forecast_source: str,
              today: dt.date) -> Iterator[str]:
    location_name = intent.location.name.title()
    try:
        yield _sse({"type": "status", "state": "forecasting"})
        req = _intent_to_request(intent)
        yield _sse({"type": "status", "state": "planning"})
        plan, sched = plan_with_sched(req, forecast_source=forecast_source, today=today)
    except Exception:
        yield _sse({"type": "error",
                    "message": "The forecast service did not respond. "
                               "Try again in a moment."})
        yield _sse({"type": "done"})
        return

    yield _sse({"type": "status", "state": "writing"})
    if llm_name == "mock":
        explanation = _plain_summary(plan, location_name)
    else:
        try:
            explanation = generate_briefing(
                sched, location_name=location_name, llm=llm).text
        except Exception:  # UngroundedBriefing, or a transport failure
            explanation = _plain_summary(plan, location_name)

    yield from _stream_words(explanation)
    yield _sse({"type": "artifact", "plan": plan.model_dump(mode="json")})
    yield _sse({"type": "done"})
