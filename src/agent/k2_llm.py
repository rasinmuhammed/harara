"""
Adapter for K2-Horizon served on the IFM API (OpenAI-compatible chat
completions). This is the integration seam, not a tuned system.

The model supplies claims and verbatim quotes; this module supplies the
character offsets (by locating each quote in the source) and drops any
item whose quote is not a verbatim substring. Everything else is still
enforced downstream: parse.py rejects unsupported fields, rule_store.py
re-checks every citation, brief.py rejects ungrounded numbers. A weak
prompt therefore degrades usefulness, not safety.

Config, from the environment or a .env file at the repo root:
    IFM_API_KEY     required
    IFM_BASE_URL    default https://api.ifm.ai/v1
    IFM_MODEL       default IFM/K2-Horizon-375B-A23B

Not exercised by the offline test suite. Score it with:
    python eval/agent_eval.py --model k2
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import time

import requests

from src.agent.llm import GAZETTEER, LLM, register
from src.agent.schemas import (
    Citation, ClarificationNeeded, DateWindowWithCitation,
    HourWindowWithCitation, Location, ParsedRequest,
    RestRatioWithCitation, RuleConstraintsExtracted, RunSchedulerResponse,
    ValueWithCitation,
)

DEFAULT_BASE_URL = "https://api.ifm.ai/v1"
DEFAULT_MODEL = "IFM/K2-Horizon-375B-A23B"

_EXTRACT_SYS = """\
You extract heat-safety constraints from a rule document into JSON. Output \
ONLY the JSON object, nothing else.

Shape (use exactly these keys):
{
  "banned_hour_windows": [{"start":"HH:MM","end":"HH:MM","quote":"<verbatim substring>"}],
  "wbgt_stop_work_c": {"value": <number>, "quote":"<verbatim substring>"} or null,
  "seasonal_window": {"start":"MM-DD","end":"MM-DD","quote":"<verbatim substring>"} or null,
  "workload_rest_ratios": [{"workload":"light|moderate|heavy|very_heavy","work_fraction":<0..1>,"quote":"<verbatim substring>"}]
}

Every "quote" MUST be copied character-for-character from the document. \
Omit any item you cannot quote. Do not add commentary."""

_PARSE_SYS = """\
Turn the scheduling request into JSON. Output ONLY the JSON object.

If date, required work-hours, workload class, acclimatisation and location \
are ALL stated, return:
{"outcome":"parsed","intent":{"target_local_date":"YYYY-MM-DD",\
"required_work_hours":<float>,"crew":{"workload":"light|moderate|heavy|very_heavy",\
"acclimatised":<bool>,"crew_size":<int>},"location":{"name":"<as written>",\
"lat":<float>,"lon":<float>},"timezone":"Asia/Qatar"}}

If any of those five is missing or ambiguous, return:
{"outcome":"clarification","missing_fields":["..."],"question":"..."}

Never guess a missing value. `today` is supplied; resolve relative dates \
against it. crew_size defaults to 1 only if no size is given."""

_BRIEF_SYS = (
    "You are explaining a finished work/rest plan to a foreman, in two or "
    "three plain sentences. Lead with the headline: the worst retained heat "
    "load under the plan versus the fixed 10:00 to 15:30 calendar ban, and "
    "that the same work-hours are delivered. Then say in words what the day "
    "looks like: full rate in the cool morning, easing or resting through the "
    "forecast peak, picking back up as it cools. Use ONLY numbers that appear "
    "in the scheduler result JSON, and quote at most three of them. Do not "
    "print a table or an hour-by-hour list. No preamble, no lists, no emoji. "
    "Refer to a rule as [rule:<rule_id>#<field>] if you cite one."
)
_ALERT_SYS = (
    "Explain to a supervisor why a re-planned day differs from the plan "
    "last issued. Use only numbers present in the two scheduler-result "
    "JSON objects given. State what changed and that the optimisation "
    "itself is unchanged. No preamble."
)

_ASSISTANT_SYS = """\
You are the assistant for Harara, a forecast-driven work/rest planner for \
outdoor crews in Qatar. Answer the user in plain, direct language, two or \
three short sentences unless they ask for more.

What Harara does: it reads the hourly weather forecast for a site, computes \
WBGT (wet-bulb globe temperature, a heat-stress index that combines heat, \
humidity, sun and wind), and plans the working day so the crew spends less \
time in the worst heat while still delivering the same work-hours. It builds \
on Qatar Ministerial Decision 17/2021, which sets a WBGT stop-work level of \
32.1 and a fixed midday rest window of 10:00 to 15:30 in summer. Harara treats \
32.1 as a hard limit and never plans work above it.

Rules for your reply:
- You may state the published regulatory figures (32.1, the 10:00 to 15:30 \
  window, the season) and any number that appears in the plan JSON you are \
  given. Do NOT invent or estimate any other number: no made-up temperatures, \
  heat loads, percentages, or hours. If you do not have a figure, say to run a \
  plan and it will show the exact numbers.
- If the user is describing a shift they want planned, tell them to send it \
  with the location, the day, the kind of work, the hours, and whether the \
  crew is used to the heat, and it will be planned.
- No preamble, no lists unless asked, no emoji."""

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def _load_env_file() -> None:
    for parent in [pathlib.Path.cwd(), *pathlib.Path(__file__).resolve().parents]:
        f = parent / ".env"
        if f.is_file():
            for line in f.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return


def _extract_json(text: str) -> dict:
    text = _THINK_RE.sub("", text).strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    depth = 0
    for i in range(start, len(text)) if start != -1 else ():
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError(f"no JSON object in model reply: {text[:200]!r}")


def _cite(source: str, quote: str) -> Citation | None:
    """Locate the quote in the source; None if it is not a verbatim substring."""
    if not quote:
        return None
    i = source.find(quote)
    if i == -1:
        return None
    return Citation(span=(i, i + len(quote)), quote=quote)


def _repair_constraints(raw: dict, source: str) -> RuleConstraintsExtracted:
    banned = []
    for w in raw.get("banned_hour_windows") or []:
        c = _cite(source, w.get("quote", ""))
        if c and _hhmm(w.get("start")) and _hhmm(w.get("end")):
            banned.append(HourWindowWithCitation(
                start=w["start"], end=w["end"], citation=c))

    stop = None
    s = raw.get("wbgt_stop_work_c")
    if isinstance(s, dict):
        c = _cite(source, s.get("quote", ""))
        if c and isinstance(s.get("value"), (int, float)):
            stop = ValueWithCitation(value=float(s["value"]), citation=c)

    season = None
    sw = raw.get("seasonal_window")
    if isinstance(sw, dict):
        c = _cite(source, sw.get("quote", ""))
        if c and _mmdd(sw.get("start")) and _mmdd(sw.get("end")):
            season = DateWindowWithCitation(
                start=sw["start"], end=sw["end"], citation=c)

    ratios = []
    for r in raw.get("workload_rest_ratios") or []:
        c = _cite(source, r.get("quote", ""))
        wl = r.get("workload")
        wf = r.get("work_fraction")
        if (c and wl in ("light", "moderate", "heavy", "very_heavy")
                and isinstance(wf, (int, float)) and 0 < wf <= 1):
            ratios.append(RestRatioWithCitation(
                workload=wl, work_fraction=float(wf), citation=c))

    return RuleConstraintsExtracted(
        banned_hour_windows=banned, wbgt_stop_work_c=stop,
        seasonal_window=season, workload_rest_ratios=ratios)


def _hhmm(v) -> bool:
    return isinstance(v, str) and bool(re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v))


def _mmdd(v) -> bool:
    return isinstance(v, str) and bool(
        re.match(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$", v))


class K2LLM(LLM):
    name = "k2"

    def __init__(self, *, base_url: str | None = None, model: str | None = None,
                 api_key: str | None = None, timeout: float | None = None,
                 max_retries: int | None = None):
        _load_env_file()
        self.base_url = (base_url or os.environ.get("IFM_BASE_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("IFM_MODEL") or DEFAULT_MODEL
        self.api_key = api_key or os.environ.get("IFM_API_KEY")
        if not self.api_key:
            raise RuntimeError("IFM_API_KEY not set (env or .env)")
        # Interactive defaults: keep a slow or down endpoint from hanging a
        # request. Override with IFM_TIMEOUT / IFM_MAX_RETRIES.
        self.timeout = (timeout if timeout is not None
                        else float(os.environ.get("IFM_TIMEOUT", "30")))
        self.max_retries = (max_retries if max_retries is not None
                            else int(os.environ.get("IFM_MAX_RETRIES", "1")))

    # -- transport ----------------------------------------------------
    def _chat(self, system: str, user: str, *, max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }
        last = None
        for attempt in range(self.max_retries):
            try:
                r = requests.post(
                    f"{self.base_url}/chat/completions", json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout)
                r.raise_for_status()
                msg = r.json()["choices"][0]["message"]
                return (msg.get("content") or "").strip()
            except (requests.RequestException, KeyError, ValueError) as e:
                last = e
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"IFM request failed after {self.max_retries} "
                           f"tries: {last}")

    # -- interface --------------------------------------------------
    def extract_rule(self, source_text: str) -> RuleConstraintsExtracted:
        raw = _extract_json(self._chat(_EXTRACT_SYS, source_text,
                                       max_tokens=8000))
        return _repair_constraints(raw, source_text)

    def parse_request(self, text: str, *, today: dt.date):
        raw = _extract_json(self._chat(
            _PARSE_SYS, f"today = {today.isoformat()}\n\n{text}",
            max_tokens=6000))
        if raw.get("outcome") == "clarification":
            return ClarificationNeeded(
                missing_fields=list(raw.get("missing_fields") or []),
                question=raw.get("question")
                or "Please provide the missing details.")
        intent = raw["intent"]
        loc = intent.get("location") or {}
        name = str(loc.get("name", "")).strip()
        key = name.lower()
        if key in GAZETTEER:                     # trust our gazetteer, not the model
            lat, lon = GAZETTEER[key]
            intent["location"] = {"name": key, "lat": lat, "lon": lon}
        return ParsedRequest.model_validate({"intent": intent})

    def write_briefing(self, sched: RunSchedulerResponse, rules, *,
                       location_name: str) -> str:
        payload = {"location": location_name,
                   "scheduler_result": sched.model_dump(mode="json"),
                   "rules": rules}
        return _THINK_RE.sub("", self._chat(
            _BRIEF_SYS, json.dumps(payload, default=str),
            max_tokens=4000)).strip()

    def draft_alert(self, before: RunSchedulerResponse,
                    after: RunSchedulerResponse, fired, *,
                    target_date: dt.date) -> str:
        payload = {"target_date": target_date.isoformat(),
                   "material_changes": list(fired),
                   "issued_plan": before.model_dump(mode="json"),
                   "new_plan": after.model_dump(mode="json")}
        return _THINK_RE.sub("", self._chat(
            _ALERT_SYS, json.dumps(payload, default=str),
            max_tokens=4000)).strip()

    def converse(self, system: str, user: str, *, max_tokens: int = 900) -> str:
        return _THINK_RE.sub("", self._chat(
            system or _ASSISTANT_SYS, user, max_tokens=max_tokens)).strip()


register("k2", K2LLM)
