"""
Anthropic adapter for the agent interface. This is the integration seam,
not a tuned system: it builds a task prompt, calls the Messages API, and
parses the reply through the same Pydantic schemas the mock uses. Every
safety property is still enforced downstream -- parse.py rejects
unsupported fields, rule_store.py rejects uncited values, brief.py rejects
ungrounded numbers -- so a weak prompt degrades usefulness, not safety.

Not exercised by the offline test suite. Select it with

    python eval/agent_eval.py --model anthropic

with ANTHROPIC_API_KEY set. Model id and prompts are expected to be tuned
against the eval before this is used for anything real.
"""

from __future__ import annotations

import datetime as dt
import json
import os

from src.agent.llm import LLM, register
from src.agent.schemas import (
    ClarificationNeeded, ParsedRequest, RuleConstraintsExtracted,
    RunSchedulerResponse,
)

DEFAULT_MODEL = "claude-sonnet-5"

_EXTRACT_SYS = (
    "You extract heat-safety constraints from a rule document. Return JSON "
    "matching this shape: {banned_hour_windows:[{start,end,citation:"
    "{span:[a,b],quote}}], wbgt_stop_work_c:{value,citation}|null, "
    "seasonal_window:{start,end,citation}|null, workload_rest_ratios:"
    "[{workload,work_fraction,citation}]}. start/end of an hour window are "
    "'HH:MM'; seasonal_window start/end are 'MM-DD'; workload is one of "
    "light|moderate|heavy|very_heavy; work_fraction is a fraction in (0,1]. "
    "Every citation.quote must be a verbatim substring of the document and "
    "citation.span must be its [start,end] character offsets. Emit nothing "
    "you cannot cite."
)
_PARSE_SYS = (
    "You turn a scheduling request into JSON. If every one of date, "
    "required work-hours, workload class, acclimatisation and location is "
    "stated, return {outcome:'parsed', intent:{target_local_date:'YYYY-MM-"
    "DD', required_work_hours:float, crew:{workload,acclimatised:bool,"
    "crew_size:int}, location:{name,lat,lon}, timezone:'Asia/Qatar'}}. If "
    "any of those five is missing or ambiguous, return {outcome:"
    "'clarification', missing_fields:[...], question:'...'}. Never guess a "
    "missing value. `today` is given; resolve relative dates against it."
)
_BRIEF_SYS = (
    "Write a short shift briefing for a foreman from the scheduler result "
    "JSON. Use only numbers that appear in that JSON. Refer to a rule as "
    "[rule:<rule_id>#<field>]. No preamble."
)
_ALERT_SYS = (
    "Explain to a supervisor why a re-planned day differs from the plan "
    "last issued. Use only numbers present in the two scheduler-result "
    "JSON objects given. State what changed and that the optimisation is "
    "unchanged."
)


class AnthropicLLM(LLM):
    name = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL, **kw):
        import anthropic

        self.model = model
        self._client = anthropic.Anthropic(
            api_key=kw.get("api_key") or os.environ["ANTHROPIC_API_KEY"])

    # -- transport ------------------------------------------------------
    def _json(self, system: str, user: str) -> dict:
        msg = self._client.messages.create(
            model=self.model, max_tokens=1500, system=system,
            messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.split("```")[1].removeprefix("json").strip()
        return json.loads(text)

    def _text(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self.model, max_tokens=1200, system=system,
            messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in msg.content if b.type == "text").strip()

    # -- interface -----------------------------------------------------
    def extract_rule(self, source_text: str) -> RuleConstraintsExtracted:
        raw = self._json(_EXTRACT_SYS, source_text)
        return RuleConstraintsExtracted.model_validate(raw)

    def parse_request(self, text: str, *, today: dt.date):
        raw = self._json(_PARSE_SYS, f"today = {today.isoformat()}\n\n{text}")
        if raw.get("outcome") == "clarification":
            return ClarificationNeeded(
                missing_fields=raw.get("missing_fields", []),
                question=raw.get("question", "Please provide the missing "
                                 "details."))
        return ParsedRequest.model_validate({"intent": raw["intent"]})

    def write_briefing(self, sched: RunSchedulerResponse, rules, *,
                       location_name: str) -> str:
        payload = {
            "location": location_name,
            "scheduler_result": sched.model_dump(mode="json"),
            "rules": rules,
        }
        return self._text(_BRIEF_SYS, json.dumps(payload, default=str))

    def draft_alert(self, before: RunSchedulerResponse,
                    after: RunSchedulerResponse, fired, *,
                    target_date: dt.date) -> str:
        payload = {
            "target_date": target_date.isoformat(),
            "material_changes": fired,
            "issued_plan": before.model_dump(mode="json"),
            "new_plan": after.model_dump(mode="json"),
        }
        return self._text(_ALERT_SYS, json.dumps(payload, default=str))


register("anthropic", AnthropicLLM)
