"""
Model-agnostic interface for the four language tasks in this layer, plus a
deterministic MockLLM used by the tests and the offline pipeline.

The interface is deliberately task-specific: each method has one job, one
eval, and a mock implementation that is plain Python. A real provider
adapter implements the same four methods with prompts. The default model is
chosen last (docs/llm_layer_plan.md, build step 7); nothing else in the
package imports a provider.

None of these methods produce a number that reaches a decision. Rule
extraction returns values that are checked against a cited source span
before anything uses them; request parsing returns fields the scheduler
validates and computes from; briefings and alerts are checked token by
token against tool output (src/agent/brief.py). The MockLLM here is only
the stand-in that lets the rest of the layer and its eval run without a
network.
"""

from __future__ import annotations

import datetime as dt
import re
from abc import ABC, abstractmethod

from src.agent.schemas import (
    Citation, ClarificationNeeded, CrewParams, DateWindowWithCitation,
    HourWindowWithCitation, Location, ParsedRequest, PlanIntent,
    RestRatioWithCitation, RuleConstraintsExtracted, RunSchedulerResponse,
    ValueWithCitation,
)

# Fields the parser must never fill from a default. A request missing any of
# these comes back as a clarification, not a guess.
SAFETY_FIELDS = ("target_local_date", "required_work_hours", "workload",
                 "acclimatised", "location")


class LLM(ABC):
    """Every model adapter implements exactly these four methods."""

    name: str = "abstract"

    @abstractmethod
    def extract_rule(self, source_text: str) -> RuleConstraintsExtracted:
        """Pull structured constraints out of a rule document. Every value
        carries a char-offset citation into `source_text`."""

    @abstractmethod
    def parse_request(
        self, text: str, *, today: dt.date
    ) -> ParsedRequest | ClarificationNeeded:
        """Turn a free-text scheduling request into a PlanIntent, or ask
        back if any safety-relevant field is missing or ambiguous."""

    @abstractmethod
    def write_briefing(
        self, sched: RunSchedulerResponse, rules: list[dict], *,
        location_name: str
    ) -> str:
        """Draft a short foreman briefing from a scheduler result. Numbers
        are copied from `sched`; rule references cite `rules`."""

    @abstractmethod
    def draft_alert(
        self, before: RunSchedulerResponse, after: RunSchedulerResponse,
        fired: list[str], *, target_date: dt.date
    ) -> str:
        """Explain, for a human, why a re-planned day differs materially
        from the plan last issued."""


# =========================================================================
# MockLLM
# =========================================================================
_MONTHS = {m: i for i, m in enumerate(
    ["", "january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}
_MONTH_LAST = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
               7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

# A small Doha-area gazetteer for the NL parser. Unknown place names fall
# through to a clarification rather than a default location.
GAZETTEER: dict[str, tuple[float, float]] = {
    "doha": (25.2854, 51.5310),
    "lusail": (25.4300, 51.4900),
    "industrial area": (25.1900, 51.4400),
    "al wakrah": (25.1710, 51.6030),
    "wakrah": (25.1710, 51.6030),
    "mesaieed": (24.9900, 51.5500),
    "hamad port": (25.0250, 51.6100),
    "al rayyan": (25.2900, 51.4200),
    "rayyan": (25.2900, 51.4200),
    "west bay": (25.3200, 51.5300),
    "education city": (25.3150, 51.4400),
}


class MockLLM(LLM):
    """Deterministic regex/keyword stand-in. It is not a language model; it
    exists so the layer and its eval run offline and identically every
    time. The source documents under eval/agent_eval/rules/ are written in
    canonical phrasing this can parse."""

    name = "mock"

    # ---- (b) rule extraction --------------------------------------------
    def extract_rule(self, t: str) -> RuleConstraintsExtracted:
        return RuleConstraintsExtracted(
            banned_hour_windows=_extract_banned_windows(t),
            wbgt_stop_work_c=_extract_stop_work(t),
            seasonal_window=_extract_season(t),
            workload_rest_ratios=_extract_rest_ratios(t),
        )

    # ---- (a) natural-language request parsing --------------------------
    def parse_request(self, text: str, *, today: dt.date):
        s = " ".join(text.lower().split())
        missing: list[str] = []

        date = _parse_date(s, today)
        if date is None:
            missing.append("target_local_date")

        workload = _parse_workload(s)
        if workload is None:
            missing.append("workload")

        acclimatised = _parse_acclimatised(s)
        if acclimatised is None:
            missing.append("acclimatised")

        hours = _parse_work_hours(s)
        if hours is None:
            missing.append("required_work_hours")

        loc = _parse_location(s)
        if loc is None:
            missing.append("location")

        if missing:
            return ClarificationNeeded(
                missing_fields=sorted(missing),
                question=_clarify_question(sorted(missing)),
            )

        return ParsedRequest(intent=PlanIntent(
            target_local_date=date,
            required_work_hours=hours,
            crew=CrewParams(workload=workload, acclimatised=acclimatised,
                            crew_size=_parse_crew_size(s)),
            location=loc,
        ))

    # ---- (c) grounded briefing ----------------------------------------
    def write_briefing(self, sched, rules, *, location_name):
        delta = sched.baseline_peak_strain - sched.plan_peak_strain
        worked = [f"{p.local_time:%H:%M} ({p.work_fraction})"
                  for p in sched.plan if p.work_fraction >= 0.05]
        schedule = ", ".join(worked) or "no hours"
        lines = [
            f"Shift plan - {location_name}, "
            f"{sched.plan[0].local_time.date().isoformat()}",
            "",
            f"Deliver {sched.work_hours_delivered} of "
            f"{sched.work_hours_required} required work-hours.",
            f"Work fraction by hour: {schedule}.",
        ]
        if sched.stop_work_hours:
            lines.append(
                "Do not work (forecast WBGT over the stop-work threshold): "
                + ", ".join(sched.stop_work_hours) + ".")
        if sched.work_shortfall > 0:
            lines.append(
                f"{sched.work_shortfall} work-hours cannot be placed safely "
                f"today; carry them or add a crew.")
        lines += [
            "",
            f"Peak retained heat load under this plan: "
            f"{sched.plan_peak_strain} "
            f"(fixed midday-ban baseline: {sched.baseline_peak_strain}, "
            f"{delta:+.2f}).",
            f"Continuous-work WBGT limit for this crew: {sched.wbgt_ref_c} C.",
        ]
        if sched.applied_rule_ids:
            lines.append("Rules applied: " + ", ".join(
                f"[rule:{r}#banned_hour_windows]"
                for r in sched.applied_rule_ids) + ".")
        return "\n".join(lines)

    # ---- (d) monitoring alert ---------------------------------------
    def draft_alert(self, before, after, fired, *, target_date):
        lines = [f"Plan change - {target_date.isoformat()} - review needed",
                 "", "What moved:"]
        for cond in fired:
            if cond == "allowed_hours_changed":
                lines.append(f"- Working hours allowed: {before.allowed_hours} "
                             f"-> {after.allowed_hours}")
            elif cond == "peak_strain":
                lines.append(f"- Plan peak retained load: "
                             f"{before.plan_peak_strain} -> "
                             f"{after.plan_peak_strain}")
            elif cond == "tail_strain":
                lines.append(f"- Plan tail retained load: "
                             f"{before.plan_tail_strain} -> "
                             f"{after.plan_tail_strain}")
            elif cond == "stop_work_count":
                lines.append(f"- Stop-work hours: {before.stop_work_hours} -> "
                             f"{after.stop_work_hours}")
            elif cond == "shortfall_appeared":
                lines.append(f"- Work shortfall: {before.work_shortfall} -> "
                             f"{after.work_shortfall} work-hours")
        lines += ["",
                  "The optimisation is unchanged. The forecast the plan is "
                  "built on has moved."]
        return "\n".join(lines)


# =========================================================================
# extraction helpers (module-level, so the eval can test them in isolation)
# =========================================================================
def _cit(t: str, m: re.Match) -> Citation:
    return Citation(span=(m.start(), m.end()), quote=t[m.start():m.end()])


def _pad(hhmm: str) -> str:
    h, mm = hhmm.split(":")
    return f"{int(h):02d}:{mm}"


_BANNED_RE = re.compile(
    r"(?:is\s+prohibited\s+from|no\s+(?:outdoor\s+)?work\s+is\s+carried\s+out\s+"
    r"between|no\s+delivery\s+jobs\s+are\s+dispatched\s+between|"
    r"no\s+work\s+is\s+permitted\s+between)\s+"
    r"(\d{1,2}:\d{2})\s+(?:to|and)\s+(\d{1,2}:\d{2})",
    re.I)


def _extract_banned_windows(t: str) -> list[HourWindowWithCitation]:
    out = []
    for m in _BANNED_RE.finditer(t):
        out.append(HourWindowWithCitation(
            start=_pad(m.group(1)), end=_pad(m.group(2)), citation=_cit(t, m)))
    return out


_STOP_RE = re.compile(
    r"(?:work\s+must\s+stop\s+whenever[^.]*?reaches|"
    r"stood\s+down\s+when[^.]*?reaches|"
    r"stops?\s+when[^.]*?reads|"
    r"activity\s+stops\s+when[^.]*?reads)\s+"
    r"(\d{1,2}(?:\.\d)?)\s+degrees\s+Celsius",
    re.I)


def _extract_stop_work(t: str) -> ValueWithCitation | None:
    m = _STOP_RE.search(t)
    if not m:
        return None
    return ValueWithCitation(value=float(m.group(1)), citation=_cit(t, m))


_SEASON_DMY_RE = re.compile(
    r"from\s+(\d{1,2})\s+([A-Za-z]+)\s+to\s+(\d{1,2})\s+([A-Za-z]+)", re.I)
_SEASON_TWO_MONTHS_RE = re.compile(r"in\s+([A-Za-z]+)\s+and\s+([A-Za-z]+)", re.I)
_SEASON_THROUGH_RE = re.compile(
    r"from\s+([A-Za-z]+)\s+(?:through|to)\s+([A-Za-z]+)", re.I)


def _extract_season(t: str) -> DateWindowWithCitation | None:
    m = _SEASON_DMY_RE.search(t)
    if m and m.group(2).lower() in _MONTHS and m.group(4).lower() in _MONTHS:
        return DateWindowWithCitation(
            start=f"{_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}",
            end=f"{_MONTHS[m.group(4).lower()]:02d}-{int(m.group(3)):02d}",
            citation=_cit(t, m))
    for rx in (_SEASON_TWO_MONTHS_RE, _SEASON_THROUGH_RE):
        m = rx.search(t)
        if m and m.group(1).lower() in _MONTHS and m.group(2).lower() in _MONTHS:
            a, b = _MONTHS[m.group(1).lower()], _MONTHS[m.group(2).lower()]
            return DateWindowWithCitation(
                start=f"{a:02d}-01", end=f"{b:02d}-{_MONTH_LAST[b]:02d}",
                citation=_cit(t, m))
    return None


_RATIO_DIRECT_RE = re.compile(
    r"(light|moderate|heavy|very heavy)\s+(?:work|tasks?)\s+(?:are\s+)?"
    r"(?:limited\s+to\s+)?a?\s*(\d{2,3})\s+percent\s+work\s+fraction", re.I)
_RATIO_ACGIH_RE = re.compile(
    r"a\s+(\d{2,3})\s+percent\s+work\s+fraction[^.]*?applies\s+once\s+WBGT\s+"
    r"exceeds\s+\d{1,2}(?:\.\d)?\s*C", re.I)


def _extract_rest_ratios(t: str) -> list[RestRatioWithCitation]:
    out: list[RestRatioWithCitation] = []
    seen: set[tuple[str, float]] = set()

    def add(wl: str, frac: float, m: re.Match) -> None:
        key = (wl, frac)
        if key in seen:
            return
        seen.add(key)
        out.append(RestRatioWithCitation(
            workload=wl, work_fraction=frac, citation=_cit(t, m)))

    for m in _RATIO_DIRECT_RE.finditer(t):
        add(m.group(1).lower().replace(" ", "_"), int(m.group(2)) / 100.0, m)
    for m in _RATIO_ACGIH_RE.finditer(t):
        head = t[max(0, m.start() - 60):m.start()].lower()
        wl = next((w for w in ("very heavy", "heavy", "moderate", "light")
                   if w in head), None)
        if wl is not None:
            add(wl.replace(" ", "_"), int(m.group(1)) / 100.0, m)
    return out


# =========================================================================
# request-parsing helpers
# =========================================================================
def _parse_date(s: str, today: dt.date) -> dt.date | None:
    if "day after tomorrow" in s:
        return today + dt.timedelta(days=2)
    if "tomorrow" in s:
        return today + dt.timedelta(days=1)
    if "today" in s:
        return today
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", s)
    if m:
        try:
            return dt.date.fromisoformat(m.group(1))
        except ValueError:
            return None
    return None


def _parse_workload(s: str) -> str | None:
    for w in ("very heavy", "heavy", "moderate", "light"):
        if re.search(rf"\b{w}\b", s):
            return w.replace(" ", "_")
    return None


def _parse_acclimatised(s: str) -> bool | None:
    if re.search(r"\bunacclimati[sz]ed\b|\bnot\s+acclimati[sz]ed\b|"
                 r"\bnew(?:ly)?[- ]arrived\b|\bno\s+heat\s+acclimati[sz]ation\b",
                 s):
        return False
    if re.search(r"\bacclimati[sz]ed\b|\bheat[- ]acclimati[sz]ed\b", s):
        return True
    return None


def _parse_work_hours(s: str) -> float | None:
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:effective\s+)?"
        r"(?:work[- ]?hours?|hours?\s+of\s+work|h\s+of\s+work|productive\s+hours?)",
        s)
    return float(m.group(1)) if m else None


def _parse_crew_size(s: str) -> int:
    m = re.search(r"crew\s+of\s+(\d+)|team\s+of\s+(\d+)|(\d+)[- ]person|"
                  r"(\d+)\s+workers?|(\d+)\s+labou?rers?", s)
    if m:
        return int(next(g for g in m.groups() if g))
    return 1


def _parse_location(s: str) -> Location | None:
    for name, (lat, lon) in GAZETTEER.items():
        if name in s:
            return Location(name=name, lat=lat, lon=lon)
    return None


def _clarify_question(missing: list[str]) -> str:
    human = {
        "target_local_date": "which date to plan for",
        "required_work_hours": "how many effective work-hours are needed",
        "workload": "the workload class (light, moderate, heavy or very heavy)",
        "acclimatised": "whether the crew is heat-acclimatised",
        "location": "the site (name a known location)",
    }
    return "Please specify " + "; ".join(human[m] for m in missing) + "."


# =========================================================================
# registry
# =========================================================================
_REGISTRY: dict[str, type[LLM]] = {"mock": MockLLM}


def register(name: str, cls: type[LLM]) -> None:
    _REGISTRY[name] = cls


def get_llm(name: str = "mock", **kwargs) -> LLM:
    if name not in _REGISTRY:
        raise ValueError(f"unknown LLM {name!r}; have {sorted(_REGISTRY)}")
    return _REGISTRY[name](**kwargs)
