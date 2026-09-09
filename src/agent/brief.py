"""
Grounded briefing generation. The model drafts prose; this module then
checks it and will not return a briefing that fails either check:

  numeric guard  every number in the briefing matches a value in a tool
                 output -- the scheduler response, or a cited value from
                 an applied rule record (both come from tools).
  rule guard     every [rule:<id>#<field>] reference resolves to a
                 supplied record and a real constraint field.

A draft that fails is retried once, then rejected.
"""

from __future__ import annotations

import re

from src.agent.llm import get_llm
from src.agent.schemas import RuleRecord, RunSchedulerResponse

_NUM = re.compile(r"-?\d+(?:\.\d+)?")
# Remove tokens that carry digits but are not quantities before scanning:
# ISO dates, MM-DD windows, clock times, [rule:...] refs, and kebab-case
# identifiers such as a rule id (qatar-md-17-2021).
_STRIP = re.compile(
    r"\d{4}-\d{2}-\d{2}"
    r"|\b\d{2}-\d{2}\b"
    r"|\b\d{1,2}:\d{2}\b"
    r"|\[rule:[^\]]*\]"
    r"|\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b"
)
_RULE_REF = re.compile(r"\[rule:([^#\]]+)#([^\]]+)\]")
_RULE_FIELDS = {"banned_hour_windows", "wbgt_stop_work_c", "seasonal_window",
                "workload_rest_ratios"}
_TOL = 0.01


class UngroundedBriefing(RuntimeError):
    """Raised when a draft still fails a check after one retry."""


def allowed_numbers(
    sched: RunSchedulerResponse,
    rule_records: list[RuleRecord] | None = None,
) -> set[float]:
    vals: set[float] = {0.0, 1.0}
    for x in (sched.plan_peak_strain, sched.plan_tail_strain,
              sched.baseline_peak_strain, sched.baseline_tail_strain,
              sched.work_hours_delivered, sched.work_hours_required,
              sched.work_shortfall, sched.wbgt_ref_c):
        vals.add(round(float(x), 3))
        vals.add(round(float(x), 2))
    for hp in sched.plan:
        vals.add(round(float(hp.wbgt_c), 3))
        vals.add(round(float(hp.wbgt_c), 2))
        vals.add(round(float(hp.work_fraction), 3))
    # differences the briefing is allowed to state
    for a, b in ((sched.baseline_peak_strain, sched.plan_peak_strain),
                 (sched.baseline_tail_strain, sched.plan_tail_strain)):
        vals.add(round(float(a) - float(b), 2))
        vals.add(round(float(b) - float(a), 2))
    # cited values from applied rule records (these come from lookup_rule)
    for rec in rule_records or []:
        c = rec.constraints
        if c.wbgt_stop_work_c is not None:
            vals.add(round(float(c.wbgt_stop_work_c.value), 2))
            vals.add(round(float(c.wbgt_stop_work_c.value), 3))
        for r in c.workload_rest_ratios:
            vals.add(round(float(r.work_fraction), 3))
        for w in c.banned_hour_windows:
            for edge in (w.start, w.end):
                vals.add(float(int(edge[:2])))
    return vals


def numeric_guard(
    text: str,
    sched: RunSchedulerResponse,
    rule_records: list[RuleRecord] | None = None,
) -> list[str]:
    allowed = allowed_numbers(sched, rule_records)
    bad: list[str] = []
    for tok in _NUM.findall(_STRIP.sub(" ", text)):
        v = float(tok)
        if not any(abs(v - a) <= _TOL for a in allowed):
            bad.append(tok)
    return bad


def rule_guard(text: str, records: list[RuleRecord]) -> list[str]:
    by_id = {r.rule_id: r for r in records}
    bad: list[str] = []
    for rid, field in _RULE_REF.findall(text):
        if rid not in by_id or field not in _RULE_FIELDS:
            bad.append(f"[rule:{rid}#{field}]")
    return bad


class Briefing:
    def __init__(self, text: str, sched: RunSchedulerResponse,
                 records: list[RuleRecord]):
        self.text = text
        self.numeric_ok = not numeric_guard(text, sched, records)
        self.rules_ok = not rule_guard(text, records)

    def __str__(self) -> str:
        return self.text


def _slim_rules(records: list[RuleRecord]) -> list[dict]:
    """What the model is allowed to see about a rule: its id and the
    fields it may reference. Not the threshold values -- those must come
    to the prose only through the scheduler result."""
    return [{"rule_id": r.rule_id,
             "referenceable_fields": sorted(
                 f for f in _RULE_FIELDS
                 if getattr(r.constraints, f, None) not in (None, [], ()))}
            for r in records]


def generate_briefing(
    sched: RunSchedulerResponse,
    *,
    location_name: str,
    rule_records: list[RuleRecord] | None = None,
    llm=None,
    retries: int = 1,
) -> Briefing:
    llm = llm or get_llm()
    records = rule_records or []
    slim = _slim_rules(records)

    last_bad: list[str] = []
    for _ in range(retries + 1):
        text = llm.write_briefing(sched, slim, location_name=location_name)
        bad_num = numeric_guard(text, sched, records)
        bad_rule = rule_guard(text, records)
        if not bad_num and not bad_rule:
            return Briefing(text, sched, records)
        last_bad = [f"number {b!r} not in tool output" for b in bad_num] + \
                   [f"unresolved {b}" for b in bad_rule]

    raise UngroundedBriefing("; ".join(last_bad))
