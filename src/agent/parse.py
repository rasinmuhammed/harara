"""
Natural-language front door. Wraps LLM.parse_request with a fail-closed
check that holds for any model: a scheduling request is only returned when
every safety-relevant field (date, work-hours, workload, acclimatisation,
location) is both present in the parsed result and supported by evidence
in the request text. Anything missing or unsupported comes back as a
ClarificationNeeded, never a guess.
"""

from __future__ import annotations

import datetime as dt
import re

from src.agent.llm import GAZETTEER, SAFETY_FIELDS, get_llm
from src.agent.schemas import ClarificationNeeded, ParsedRequest

_WORKLOAD_WORDS = {
    "light": r"\blight\b",
    "moderate": r"\bmoderate\b",
    "heavy": r"\bheavy\b",
    "very_heavy": r"\bvery heavy\b",
}
_ACCLIM_CUE = re.compile(
    r"\b(?:un)?acclimati[sz]ed\b|\bnot acclimati[sz]ed\b|"
    r"\bnew(?:ly)?[- ]arrived\b|\bheat[- ]acclimati[sz]ation\b", re.I)
_DATE_CUE = re.compile(
    r"\btoday\b|\btomorrow\b|\bday after tomorrow\b|\b\d{4}-\d{2}-\d{2}\b", re.I)
_HOURS_CUE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:effective\s+)?"
    r"(?:work[- ]?hours?|hours?\s+of\s+work|h\s+of\s+work|productive\s+hours?)",
    re.I)


def _evidence_missing(text: str, intent) -> list[str]:
    s = " ".join(text.lower().split())
    missing: list[str] = []

    if not _DATE_CUE.search(s):
        missing.append("target_local_date")
    if not _HOURS_CUE.search(s):
        missing.append("required_work_hours")

    pat = _WORKLOAD_WORDS.get(intent.crew.workload)
    if not pat or not re.search(pat, s):
        missing.append("workload")
    if not _ACCLIM_CUE.search(s):
        missing.append("acclimatised")
    if intent.location.name.lower() not in s or \
            intent.location.name.lower() not in GAZETTEER:
        missing.append("location")
    return missing


def _question(missing: list[str]) -> str:
    human = {
        "target_local_date": "which date to plan for",
        "required_work_hours": "how many effective work-hours are needed",
        "workload": "the workload class (light, moderate, heavy or very heavy)",
        "acclimatised": "whether the crew is heat-acclimatised",
        "location": "the site (name a known location)",
    }
    order = [f for f in SAFETY_FIELDS if f in missing]
    return "Please specify " + "; ".join(human[f] for f in order) + "."


def parse_scheduling_request(
    text: str, *, today: dt.date, llm=None
) -> ParsedRequest | ClarificationNeeded:
    llm = llm or get_llm()
    out = llm.parse_request(text, today=today)
    if isinstance(out, ClarificationNeeded):
        return out

    missing = sorted(set(_evidence_missing(text, out.intent)),
                     key=SAFETY_FIELDS.index)
    if missing:
        return ClarificationNeeded(missing_fields=missing,
                                   question=_question(missing))
    return out
