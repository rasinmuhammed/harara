"""
Streaming chat, scope-locked. Every message is classified by
`api.chat_scope.classify` before any model call into one of: plan_request,
weather_question, heat_safety_question, rules_question, about_harara,
emergency, out_of_scope. Only those buckets go further.

- out_of_scope (including prompt-injection attempts): one fixed reply, no
  model call.
- emergency: a fixed KB-grounded first-response block with a banner, no model.
- heat_safety_question / about_harara: the curated KB entry's own text with
  its source shown; the model does not paraphrase it.
- rules_question: the Qatar rule from the rule store, or a KB summary for the
  UAE and Saudi Arabia, each cited.
- weather_question: a deterministic sentence off one of the forecast tools
  (nowcast, coolest_window, climatology_compare, heat_trend, weekly_outlook),
  with its source; the model may phrase a multi-day comparison, checked by the
  numeric guard and the output scope guard first.
- plan_request: the model turns the conversation into a validated tool call,
  or the deterministic parser does; the plan and every number come from
  /api/plan.

The model never produces a number that reaches the user, and no model reply
reaches the user without passing the numeric guard and the output scope guard.
Refusals are counted by bucket only, never by content.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from collections.abc import Iterator

from api import kb
from api.chat_scope import (
    NO_MATCH_REPLY, OUT_OF_SCOPE_REPLY, classify, emergency_reply,
)
from api.chat_scope import _PLAN_ASK  # noqa: PLC2701  (shared plan-intent regex)
from api.chat_scope import counts as refusal_counts  # noqa: F401  (re-exported)
from api.chat_scope import note as _note_bucket
from api.chat_scope import output_in_scope
from api.planning import (
    climatology_compare, coolest_window, heat_trend, nowcast, plan_with_sched,
    weekly_outlook,
)
from api.schemas import PlanRequest
from src.agent import rule_store
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
_WEATHER_Q = re.compile(
    r"\b(weather|forecast|outlook|hotter|cooler|cool(?:est|er)|hott?est|"
    r"this week|next (?:few )?days|coming days|rest of the week|compared? to the "
    r"week|wbgt (?:this|next|over)|which day|worst day|best day|how hot)\b", re.I)


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
- "answer": the user greeted you, asked a general question, asked about a plan \
  already on screen, or asked about the weather or the week ahead. Reply in \
  "say" (1 to 3 sentences). If a plan or a 7-day WBGT outlook is given below, \
  use its figures; otherwise do not state result numbers.
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


# ------------------------------------------------------- grounded answers
def _emit_answer(text: str, source: str, detail: str = "") -> Iterator[str]:
    yield from _stream_words(_clean(text))
    yield _sse({"type": "source", "label": source, "detail": detail})
    yield _sse({"type": "done"})


def _handle_emergency() -> Iterator[str]:
    banner, body, src = emergency_reply()
    yield _sse({"type": "emergency", "banner": banner})
    yield from _stream_words(body)
    yield _sse({"type": "source", "label": src})
    yield _sse({"type": "done"})


def _handle_kb(text: str) -> Iterator[str]:
    a = kb.answer(text)
    if not a:
        yield _sse({"type": "notice", "kind": "no_match"})
        yield from _stream_words(NO_MATCH_REPLY)
        yield _sse({"type": "done"})
        return
    yield from _emit_answer(a["text"], a["source"], a["title"])


def _handle_about(text: str) -> Iterator[str]:
    """A 'what is Harara / who are you / your limits' message, or a greeting.
    Falls back to the 'what Harara is' entry when nothing more specific hits."""
    a = kb.answer(text)
    if not a or a["id"] not in ("about-harara", "harara-limitations"):
        e = kb.get("about-harara")
        a = {"text": e["text"], "source": e["source"], "title": e["title"]}
    yield from _emit_answer(a["text"], a["source"], a["title"])


_UAE = re.compile(r"\b(uae|u\.a\.e|emirat|dubai|abu dhabi|sharjah|ajman|"
                  r"ras al khaimah|fujairah)\b", re.I)
_SAUDI = re.compile(r"\b(saudi|k\.s\.a|ksa|riyadh|jeddah|jiddah|dammam|mecca|"
                    r"makkah|medina)\b", re.I)
_OTHER_GULF = re.compile(r"\b(bahrain|manama|kuwait|oman|muscat|iraq|jordan)\b", re.I)


def _handle_rules(text: str) -> Iterator[str]:
    if _UAE.search(text):
        e = kb.get("uae-midday-break")
        yield from _emit_answer(e["text"], e["source"], e["title"])
        return
    if _SAUDI.search(text):
        e = kb.get("saudi-midday-ban")
        yield from _emit_answer(e["text"], e["source"], e["title"])
        return
    if _OTHER_GULF.search(text):
        yield _sse({"type": "notice", "kind": "no_match"})
        yield from _stream_words(
            "I have Qatar's rule in full, plus summaries for the UAE and Saudi "
            "Arabia. I don't have a confirmed rule for that country. Check the "
            "local labour authority.")
        yield _sse({"type": "done"})
        return
    # default: Qatar. Prefer the rule store record for the citation.
    e = kb.get("qatar-rule")
    src = e["source"]
    try:
        rec = rule_store.load("qatar-md-17-2021")
        src = f"Rule store: {rec.rule_id} ({rec.title})"
    except Exception:
        pass
    yield from _emit_answer(e["text"], src, e["title"])


def _say_nowcast(nc: dict, name: str) -> str:
    if not nc.get("available"):
        return (f"I could not get a current forecast hour for {name}. "
                "Try again shortly.")
    over = nc["over_threshold"]
    line = (f"At {name}, the {nc['as_of_local']} forecast WBGT is "
            f"{nc['wbgt']:g}. ")
    if over:
        line += ("That is above the 32.1 stop-work line, so outdoor work "
                 "should be stopped. ")
    else:
        line += "That is below the 32.1 stop-work line. "
    line += (f"For moderate work the screening band is: "
             f"{nc['acgih_band_acclimatised']} if the crew is acclimatised, "
             f"{nc['acgih_band_unacclimatised']} if not.")
    return line


def _say_coolest(cw: dict, name: str) -> str:
    if not cw.get("available"):
        return f"I could not get the forecast for {name} on that day."
    line = (f"For {name} on {cw['date']}, the coolest working stretch is about "
            f"{cw['coolest_start']} to {cw['coolest_end']}, mean WBGT "
            f"{cw['coolest_mean_wbgt']:g}. ")
    if cw["crosses_32_1_up"]:
        line += f"Forecast WBGT crosses 32.1 upward around {cw['crosses_32_1_up']}"
        line += (f" and drops back below around {cw['crosses_32_1_down']}."
                 if cw["crosses_32_1_down"] else " and stays above it into the evening.")
    else:
        line += "Forecast WBGT stays below 32.1 all day."
    return line


def _say_climo(cc: dict, name: str) -> str:
    if not cc.get("available"):
        return f"I could not get the forecast for {name} on that day."
    if not cc.get("comparable"):
        return (f"The forecast peak WBGT for {name} on {cc['date']} is "
                f"{cc['forecast_peak_wbgt']:g}. I do not have enough record for "
                "that time of year to say whether that is unusual.")
    return (f"The forecast peak WBGT for {name} on {cc['date']} is "
            f"{cc['forecast_peak_wbgt']:g}. Over {cc['record_years']} years the "
            f"typical peak around this date is {cc['climatology_median_peak']:g}, "
            f"with the hot tenth of days above {cc['climatology_p90_peak']:g}. "
            f"This day sits near the {cc['percentile']:g}th percentile, "
            f"{cc['verdict']}.")


def _say_trend(tr: dict, name: str) -> str:
    return (f"At the Doha station, WBGT stop-work hours in June to September ran "
            f"about {tr['early_years_mean']:g} per year in "
            f"{tr['first_year']} to {tr['first_year'] + 2}, and about "
            f"{tr['recent_years_mean']:g} per year in the last three full years. "
            f"The trend over {tr['first_year']} to {tr['last_year']} is "
            f"{tr['direction']}, near {tr['slope_hours_per_year']:g} hours more "
            f"per year. The record does not resolve {name} on its own.")


def _say_outlook(ol: dict, name: str) -> str:
    days = ol.get("days") or []
    if not days:
        return f"I could not get a multi-day forecast for {name}."
    hot = max(days, key=lambda d: d["peak_wbgt"])
    cool = min(days, key=lambda d: d["peak_wbgt"])
    n = len(days)
    if hot["peak_wbgt"] - cool["peak_wbgt"] < 0.3:
        line = (f"Over the next {n} days at {name}, peak WBGT holds near "
                f"{hot['peak_wbgt']:g} each day. ")
    else:
        line = (f"Over the next {n} days at {name}, peak WBGT runs from about "
                f"{cool['peak_wbgt']:g} on {cool['date']} (the mildest) to about "
                f"{hot['peak_wbgt']:g} on {hot['date']} (the hottest). ")
    over = [d["date"] for d in days if d["over_threshold"]]
    line += (f"{len(over)} of the {n} days cross 32.1 at their peak."
             if over else "None of those days cross 32.1 at their peak.")
    return line


def _handle_weather(text: str, cur: dict | None, today: dt.date,
                    forecast_source: str, llm, llm_name: str) -> Iterator[str]:
    if not (cur and cur.get("lat") is not None):
        yield _sse({"type": "notice", "kind": "no_match"})
        yield from _stream_words(
            "Tell me the site first, set it on the map or name a known one, and "
            "I will check the forecast.")
        yield _sse({"type": "done"})
        return
    lat, lon = float(cur["lat"]), float(cur["lon"])
    name = str(cur.get("name") or "the site")
    low = text.lower()
    if "day after tomorrow" in low:
        cur_date = today + dt.timedelta(days=2)
    elif "tomorrow" in low:
        cur_date = today + dt.timedelta(days=1)
    elif "today" in low or "right now" in low or "tonight" in low:
        cur_date = today
    else:
        try:
            cur_date = (dt.date.fromisoformat(str(cur.get("date")))
                        if cur.get("date") else today)
        except ValueError:
            cur_date = today

    try:
        if re.search(r"right now|at the moment|currently|safe to work|how hot is it"
                     r"|conditions?\s+(now|today|outside)|can (we|they|i) work (now|today)",
                     low):
            nc = nowcast(lat, lon, today=today, source=forecast_source)
            yield from _emit_answer(_say_nowcast(nc, name), "Forecast nowcast tool",
                                    nc.get("source", ""))
            return
        if re.search(r"coolest|when (does|will) it (cool|get cooler)"
                     r"|when (does|will) wbgt|cross(es)? 32", low):
            cw = coolest_window(lat, lon, cur_date, today=today, source=forecast_source)
            yield from _emit_answer(_say_coolest(cw, name), "coolest_window tool",
                                    cw.get("source", ""))
            return
        if re.search(r"unusual|typical|normal for|record|compared to (normal|average|history)"
                     r"|for this time of year|climatolog", low):
            cc = climatology_compare(lat, lon, cur_date, today=today,
                                     source=forecast_source)
            yield from _emit_answer(_say_climo(cc, name), "climatology_compare tool",
                                    cc.get("source", ""))
            return
        if re.search(r"trend|increasing|been (getting )?hotter|getting hotter"
                     r"|over the years|climate|warming|rising", low):
            tr = heat_trend(lat, lon, today=today)
            yield from _emit_answer(_say_trend(tr, name), tr["source"])
            return
        ol = weekly_outlook(lat, lon, today=today, source=forecast_source)
    except Exception:
        yield _sse({"type": "error",
                    "message": "The forecast service did not respond. Try again "
                               "in a moment."})
        yield _sse({"type": "done"})
        return

    # multi-day comparison: let the model phrase it from the outlook JSON,
    # checked by the numeric guard and the output scope guard first.
    said = ""
    if llm_name != "mock":
        try:
            convo = (f"user: {text}\n\n[7-day WBGT outlook for {name}, daytime "
                     f"peak and mean per local day, quote figures from here only]\n"
                     + json.dumps(ol, default=str))
            raw = llm.converse(_agent_sys(today, cur), convo, max_tokens=500)
            cand = _clean(str(_extract_json(_THINK.sub("", raw or "")).get("say") or "")) \
                if raw and raw.strip().startswith("{") else _clean(raw or "")
            allowed = _CONST_OK | _plan_numbers(ol)
            if cand and _numbers_ok(cand, allowed) and output_in_scope(cand):
                said = cand
        except Exception:
            said = ""
    yield from _emit_answer(said or _say_outlook(ol, name),
                            "weekly_outlook tool", ol.get("source", ""))


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

    # ---- scope lock: classify before any model call ------------------
    _mock = get_llm("mock")
    parsed_peek = parse_scheduling_request(text, today=today, llm=_mock)
    # a strong plan signal only: a complete parse, an in-progress gather, or an
    # explicit "plan / schedule / re-plan this" verb. A lone date word or the
    # word "crew" is not enough (it appears in weather and heat-safety asks).
    schedule_hint = (isinstance(parsed_peek, ParsedRequest)
                     or _prev_was_clarification(messages)
                     or bool(_PLAN_ASK.search(text)))
    gathering = bool(context.get("gathering"))
    intent = classify(text, schedule_hint=schedule_hint, gathering=gathering)
    _note_bucket(intent)

    if intent == "emergency":
        yield from _handle_emergency()
        return
    if intent == "out_of_scope":
        yield _sse({"type": "notice", "kind": "out_of_scope"})
        yield from _stream_words(OUT_OF_SCOPE_REPLY)
        yield _sse({"type": "done"})
        return
    if intent == "about_harara":
        yield from _handle_about(text)
        return
    if intent == "heat_safety_question":
        yield from _handle_kb(text)
        return
    if intent == "rules_question":
        yield from _handle_rules(text)
        return
    if intent == "weather_question":
        yield from _handle_weather(text, cur, today, forecast_source, llm, llm_name)
        return

    # intent == "plan_request" from here
    yield from _handle_plan(messages, text, cur, plan_ctx, llm, llm_name,
                            forecast_source, today, parsed_peek)


def _handle_plan(
    messages: list[dict], text: str, cur: dict | None, plan_ctx: dict | None,
    llm, llm_name: str, forecast_source: str, today: dt.date, parsed_peek,
) -> Iterator[str]:
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
                ok = bool(say) and _numbers_ok(say, allowed) and output_in_scope(say)
                yield from _stream_words(say if ok else _DET_ANSWER)
                yield _sse({"type": "done"})
                return
            built = _build_request(obj["params"], cur, today)
            if isinstance(built, str):  # a field is still missing
                clean_say = say if (say and output_in_scope(say)
                                    and _numbers_ok(say, _CONST_OK)) else built
                yield from _stream_words(clean_say)
                yield _sse({"type": "done"})
                return
            req, name = built
            yield from _run_request(req, name, llm, llm_name, forecast_source,
                                    today, lead_in=say if output_in_scope(say) else "")
            return
        # obj is None: fall through to the deterministic path

    # ---- deterministic fallback (no live model) -------------------
    yield _sse({"type": "status", "state": "parsing"})
    _mock = get_llm("mock")
    parsed = parsed_peek

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
