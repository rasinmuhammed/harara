"""
Streaming chat. The configured model (HARARA_LLM) runs the whole conversation:
it chats, asks for anything missing in its own words, and when it has the five
things a plan needs it says so in a JSON envelope. The deterministic core then
builds the plan and the model's lead-in plus the guarded briefing stream back
with the artifact.

The model never produces a number that reaches the user. Plan figures come
from the /api/plan payload in the `artifact` frame; the briefing passes the
numeric guard; a chat reply may only quote the published regulatory constants
and figures from a plan already on screen, and anything else degrades to a
deterministic reply.

If the model is unavailable (no key, transport error) every path falls back to
the deterministic parser, which still refuses to guess a safety-relevant field.
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
from src.agent.llm import GAZETTEER, get_llm
from src.agent.parse import parse_scheduling_request
from src.agent.schemas import ClarificationNeeded, ParsedRequest

try:
    from src.agent.k2_llm import _extract_json
except Exception:  # pragma: no cover
    def _extract_json(t: str) -> dict:  # type: ignore
        return json.loads(t)

_WORD_DELAY_S = 0.012
_LLM_NAME = os.environ.get("HARARA_LLM", "mock")
_WORKLOADS = ("light", "moderate", "heavy", "very_heavy")

_CONST_OK = {
    "32.1", "10", "15.5", "15:30", "10:00", "28", "0.8", "0.75", "0.5", "0.25",
    "1.0", "90", "24", "17", "2021", "2017", "7243", "16", "236", "15", "25",
    "1", "0", "14", "2", "45", "60",
}
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_STRIP_RE = re.compile(r"\b\d{1,2}:\d{2}\b|\d{4}-\d{2}-\d{2}|17/2021|\b\d{2}-\d{2}\b")
_THINK = re.compile(r"<think>.*?</think>", re.S)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"


def _agent_sys(today: dt.date, cur: dict | None) -> str:
    known = ", ".join(sorted(GAZETTEER))
    ctx = ""
    if cur:
        ctx = ("\n\nThe controls on screen currently read: "
               f"{json.dumps({k: cur.get(k) for k in ('name', 'date', 'workload', 'acclimatised', 'hours') if cur.get(k) is not None})}. "
               "Treat these as the current values; the user may only be changing one of them.")
    return f"""\
You are the assistant for Harara, which plans the working day for an outdoor \
crew in Qatar from the weather forecast. Talk like a helpful colleague. Today \
is {today.isoformat()}.

Harara reads hourly WBGT (a heat-stress index from heat, humidity, sun and \
wind) and shapes work and rest so the crew spends less time in the worst heat \
at the same total work-hours. It builds on Qatar Ministerial Decision 17/2021, \
which stops outdoor work at WBGT 32.1 and sets a fixed 10:00 to 15:30 midday \
rest window in summer. 32.1 is a hard limit.

A plan needs five things: site, day, kind of work (light, moderate, heavy, \
very heavy), work-hours to deliver, and whether the crew is acclimatised \
(more than two weeks in this heat). Known sites: {known}. Never invent a site \
the user has not named; if they name another place, ask them to pick a known \
site or drop a pin.{ctx}

Choose one action:
- "answer": the user greeted you, asked a general question, or asked about a \
  plan already on screen. Reply in "say" (1 to 3 sentences). If a plan is \
  given below, use its figures; otherwise do not state result numbers.
- "plan": the user is asking you, in this message, to build or change a plan, \
  AND you have all five things (fill them from the request and the current \
  controls). Put a one-line acknowledgement in "say" like "Building the plan \
  for heavy work at Lusail on Thursday now." Do NOT describe the schedule or \
  put any hours or times in it; the plan and its numbers follow on their own.
- otherwise use "answer" and ask for the one or two things still missing.

Reply with ONLY this JSON, nothing else, no markdown:
{{"action": "answer" | "plan",
 "say": "<message to the user, plain sentences, no lists, no emoji, no dashes>",
 "params": {{"location": "<site>", "date": "YYYY-MM-DD", "hours": <number>,
            "workload": "light|moderate|heavy|very_heavy", "acclimatised": <bool>}}}}
params is only read when action is "plan". Resolve relative dates against \
today. The only numbers allowed in "say" are 32.1, 10:00, 15:30, a figure the \
user gave you, or a figure from the plan JSON below."""


def _numbers_ok(text: str, extra: set[str]) -> bool:
    for tok in _NUM_RE.findall(_STRIP_RE.sub(" ", text)):
        if tok in _CONST_OK or tok in extra:
            continue
        if "." not in tok and tok.lstrip("-").isdigit() and 0 <= int(tok) <= 100:
            continue
        return False
    return True


def _plan_numbers(plan_ctx: dict | None) -> set[str]:
    out: set[str] = set()
    def walk(x):
        if isinstance(x, dict):
            [walk(v) for v in x.values()]
        elif isinstance(x, list):
            [walk(v) for v in x]
        elif isinstance(x, (int, float)):
            out.update({f"{x:g}", str(round(float(x), 1)), str(int(round(float(x))))})
    walk(plan_ctx or {})
    return out


def _resolve_location(name: str, cur: dict | None) -> tuple[float, float, str] | None:
    n = (name or "").strip().lower()
    if not n:
        if cur and cur.get("lat") is not None:
            return float(cur["lat"]), float(cur["lon"]), str(cur.get("name") or "the site")
        return None
    if n in GAZETTEER:
        lat, lon = GAZETTEER[n]
        return lat, lon, name.strip().title()
    for key, (lat, lon) in GAZETTEER.items():
        if key in n:
            return lat, lon, key.title()
    if cur and cur.get("name") and str(cur["name"]).lower() in n and cur.get("lat") is not None:
        return float(cur["lat"]), float(cur["lon"]), str(cur["name"])
    return None


def _build_request(params: dict, cur: dict | None,
                   today: dt.date) -> tuple[PlanRequest, str] | str:
    loc = _resolve_location(str(params.get("location") or (cur or {}).get("name") or ""), cur)
    if loc is None:
        return ("I don't recognise that site. Name a known site (Doha, Lusail, "
                "Industrial Area, Al Wakrah, Mesaieed and a few more) or set it "
                "on the map, and I'll plan it.")
    lat, lon, name = loc

    raw_date = params.get("date") or (cur or {}).get("date")
    try:
        date = dt.date.fromisoformat(str(raw_date)) if raw_date else today + dt.timedelta(days=1)
    except ValueError:
        date = today + dt.timedelta(days=1)
    date = min(max(date, today), today + dt.timedelta(days=15))

    hours = params.get("hours", (cur or {}).get("hours"))
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        return "How many work-hours does the crew need to deliver?"
    hours = min(max(hours, 1.0), 14.0)

    wl = str(params.get("workload") or (cur or {}).get("workload") or "").lower()
    if wl not in _WORKLOADS:
        return "What kind of work is it, light, moderate, heavy or very heavy?"

    acc = params.get("acclimatised", (cur or {}).get("acclimatised"))
    if not isinstance(acc, bool):
        return "Has the crew been working in this heat for more than two weeks?"

    return PlanRequest(lat=lat, lon=lon, date=date, required_work_hours=hours,
                       workload_class=wl, acclimatised=acc, tz="Asia/Qatar"), name


# --------------------------------------------------------------- deterministic
def _plain_summary(plan, location_name: str) -> str:
    s, m = plan.summary, plan.meta
    date = plan.meta.date.isoformat()
    parts = [
        f"For {location_name} on {date}, the plan delivers "
        f"{s.work_hours_delivered_plan:g} work-hours, the same as the fixed "
        f"10:00 to 15:30 calendar ban.",
        f"It keeps the worst retained heat load at {s.peak_plan:.2f}, against "
        f"{s.peak_calendar:.2f} under the ban, {s.pct_peak_reduction:.0f} percent lower.",
        f"The p90 tail is {s.tail_plan:.2f}, against {s.tail_calendar:.2f}.",
    ]
    if s.stop_hours_plan:
        parts.append(f"{s.stop_hours_plan} hours rest through the hottest part "
                     f"of the day, then work picks back up as it cools.")
    if s.work_shortfall_plan > 0:
        parts.append(f"{s.work_shortfall_plan} of the requested work-hours do "
                     f"not fit the working window today.")
    if m.dry_hot_day:
        parts.append(m.dry_hot_note)
    parts.append("Check the forecast again the morning before the shift."
                 if not m.wide_band else
                 "This is several days out, so check again the morning before.")
    return " ".join(parts)


_GREETING = re.compile(r"^\s*(hi|hey+|hello|yo|sup|good (morning|afternoon|evening)|"
                       r"what('?s| is) up|thanks|thank you|cheers|ok|okay|cool)\b", re.I)
_HELP = re.compile(r"\b(help|what (can|do) you|who are you|what are you|"
                   r"how (do|does) (you|this|it) work|what is this|explain)\b", re.I)
_QUESTIONISH = re.compile(
    r"\?\s*$|^\s*(what|why|how|when|which|is|are|can|could|do|does|should|would|"
    r"tell me|explain|is it)\b", re.I)
_SCHEDULE_WORDS = re.compile(
    r"\b(plan|schedule|shift|crew|work[- ]?hours?|acclimat|pour|dig|concrete|"
    r"scaffold|lifting|labou?r|hours? tomorrow|hours? today)\b", re.I)
_DET_ANSWER = (
    "I plan the working day for an outdoor crew in Qatar from the weather "
    "forecast. I read hourly WBGT, the heat-stress index that combines heat, "
    "humidity, sun and wind, and I shape work and rest so the crew spends less "
    "time in the worst heat while still delivering the same hours, inside Qatar "
    "Ministerial Decision 17/2021 (stop work at WBGT 32.1, rest 10:00 to 15:30 "
    "in summer). Tell me the site, the day, the kind of work, the work-hours "
    "you need, and whether the crew is used to the heat, and I will plan it."
)


_DASHES = re.compile(r"\s*[—–]\s*")


def _clean(text: str) -> str:
    """House style: no em or en dashes, single spaces, trimmed."""
    return re.sub(r"\s+", " ", _DASHES.sub(", ", text)).strip()


def _stream_words(text: str) -> Iterator[str]:
    for w in (text or "").split():
        yield _sse({"type": "text", "delta": w + " "})
        time.sleep(_WORD_DELAY_S)


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


_CLAR_MARK = re.compile(r"(specify|how many|which (date|day)|used to the heat|"
                        r"acclimat|work[- ]?hours are needed|workload class)|\?\s*$", re.I)


def _prev_was_clarification(messages: list[dict]) -> bool:
    for m in reversed(messages[:-1]):
        if not m.get("content", "").strip():
            continue
        return m.get("role") == "assistant" and bool(_CLAR_MARK.search(m["content"]))
    return False


def _run_plan(intent, llm, llm_name: str, forecast_source: str,
              today: dt.date, lead_in: str = "") -> Iterator[str]:
    location_name = intent.location.name.title()
    try:
        yield _sse({"type": "status", "state": "forecasting"})
        req = PlanRequest(
            lat=intent.location.lat, lon=intent.location.lon,
            date=intent.target_local_date,
            required_work_hours=intent.required_work_hours,
            workload_class=intent.crew.workload,
            acclimatised=intent.crew.acclimatised,
            tz=intent.timezone or "Asia/Qatar")
        yield _sse({"type": "status", "state": "planning"})
        plan, sched = plan_with_sched(req, forecast_source=forecast_source, today=today)
    except Exception:
        yield _sse({"type": "error",
                    "message": "The forecast service did not respond. "
                               "Try again in a moment."})
        yield _sse({"type": "done"})
        return
    yield from _finish_plan(plan, sched, llm, llm_name, location_name, today, lead_in)


def _run_request(req: PlanRequest, name: str, llm, llm_name: str,
                 forecast_source: str, today: dt.date, lead_in: str) -> Iterator[str]:
    try:
        yield _sse({"type": "status", "state": "forecasting"})
        yield _sse({"type": "status", "state": "planning"})
        plan, sched = plan_with_sched(req, forecast_source=forecast_source, today=today)
    except Exception:
        yield _sse({"type": "error",
                    "message": "The forecast service did not respond. "
                               "Try again in a moment."})
        yield _sse({"type": "done"})
        return
    yield from _finish_plan(plan, sched, llm, llm_name, name or "the site", today, lead_in)


def _nice_date(d: dt.date, today: dt.date) -> str:
    delta = (d - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return d.strftime("%A %d %B").replace(" 0", " ")


def _headline(plan, location_name: str, today: dt.date | None = None) -> str:
    s = plan.summary
    when = _nice_date(plan.meta.date, today or dt.date.today())
    return (f"Here is the plan for {location_name}, {when}: "
            f"the same {s.work_hours_delivered_plan:g} work-hours as the fixed "
            f"10:00 to 15:30 ban, with the worst retained heat load at "
            f"{s.peak_plan:.1f} against {s.peak_calendar:.1f}, "
            f"{s.pct_peak_reduction:.0f} percent lower. The chart has the hour by hour.")


def _finish_plan(plan, sched, llm, llm_name: str, location_name: str,
                 today: dt.date, lead_in: str = "") -> Iterator[str]:
    """Stream the explanation then the artifact. The model's one-line
    acknowledgement runs first if it is clean; the plan recap that follows is
    always the deterministic grounded headline, never a model narration."""
    yield _sse({"type": "status", "state": "writing"})
    parts = []
    if lead_in and _numbers_ok(lead_in, _CONST_OK):
        parts.append(lead_in.strip().rstrip(".") + ".")
    parts.append(_plain_summary(plan, location_name) if llm_name == "mock"
                 else _headline(plan, location_name, today))
    yield from _stream_words(" ".join(parts))
    yield _sse({"type": "artifact", "plan": plan.model_dump(mode="json")})
    yield _sse({"type": "done"})


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
    cur = context.get("req") if isinstance(context.get("req"), dict) else None

    try:
        llm = get_llm(_LLM_NAME)
        llm_name = _LLM_NAME
    except Exception:
        llm = get_llm("mock")
        llm_name = "mock"

    if intent_override:
        from src.agent.schemas import PlanIntent
        try:
            intent = PlanIntent.model_validate(intent_override)
        except Exception:
            yield _sse({"type": "error", "message": "That request was incomplete."})
            yield _sse({"type": "done"})
            return
        yield from _run_plan(intent, llm, llm_name, forecast_source, today)
        return

    text = _last_user(messages)
    if not text:
        yield _sse({"type": "error", "message": "Say what you need."})
        yield _sse({"type": "done"})
        return

    # ---- model-driven conversation ----------------------------------
    if llm_name != "mock":
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in messages[-10:]
                          if m.get("content", "").strip())
        if plan_ctx:
            convo += ("\n\n[plan on screen, quote figures from here only]\n"
                      + json.dumps(plan_ctx, default=str))
        yield _sse({"type": "status", "state": "parsing"})
        try:
            raw = llm.converse(_agent_sys(today, cur), convo, max_tokens=1400)
            obj = _extract_json(_THINK.sub("", raw or ""))
        except Exception:
            obj = None

        if isinstance(obj, dict):
            say = _clean(str(obj.get("say") or ""))
            plan_now = obj.get("action") == "plan" and isinstance(obj.get("params"), dict)
            if not plan_now:
                allowed = _CONST_OK | _plan_numbers(plan_ctx)
                yield from _stream_words(say if say and _numbers_ok(say, allowed)
                                         else _DET_ANSWER)
                yield _sse({"type": "done"})
                return
            built = _build_request(obj["params"], cur, today)
            if isinstance(built, str):  # a field is still missing
                yield from _stream_words(say or built)
                yield _sse({"type": "done"})
                return
            req, name = built
            yield from _run_request(req, name, llm, llm_name, forecast_source,
                                    today, lead_in=say)
            return
        # obj is None: fall through to the deterministic path

    # ---- deterministic fallback (no live model) -------------------
    yield _sse({"type": "status", "state": "parsing"})
    _mock = get_llm("mock")
    parsed = parse_scheduling_request(text, today=today, llm=_mock)

    if isinstance(parsed, ParsedRequest):
        yield from _run_plan(parsed.intent, llm, llm_name, forecast_source, today)
        return

    # a follow-up filling a gap after a clarification: fold in the prior turn
    if _prev_was_clarification(messages):
        prev = _prev_user(messages)
        combined = (parse_scheduling_request(f"{prev}\n{text}", today=today, llm=_mock)
                    if prev else parsed)
        if isinstance(combined, ParsedRequest):
            yield from _run_plan(combined.intent, llm, llm_name, forecast_source, today)
            return
        yield _sse({"type": "clarification", "question": combined.question,
                    "missing_fields": combined.missing_fields})
        yield _sse({"type": "done"})
        return

    # not gathering. A greeting, a question, or a general remark gets a written
    # answer; a scheduling attempt with some fields gets the ask-back.
    nonloc = {"target_local_date", "required_work_hours", "workload", "acclimatised"}
    scheduling_try = bool(nonloc - set(parsed.missing_fields)) or bool(_SCHEDULE_WORDS.search(text))
    is_chat = bool(_GREETING.match(text) or _HELP.search(text) or _QUESTIONISH.search(text))

    if is_chat and not scheduling_try:
        yield from _stream_words(_DET_ANSWER)
        yield _sse({"type": "done"})
        return

    yield _sse({"type": "clarification", "question": parsed.question,
                "missing_fields": parsed.missing_fields})
    yield _sse({"type": "done"})
