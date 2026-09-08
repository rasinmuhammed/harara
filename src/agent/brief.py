"""
Grounded briefing generation. The model drafts prose; this module then
checks it and will not return a briefing that fails either check:

  numeric guard  every number in the briefing matches a value in the
                 scheduler response (or a rounding of one).
  rule guard     every [rule:<id>#<field>] reference resolves to a
                 confirmed record and a real constraint field.

A draft that fails is retried once, then rejected.
"""

from __future__ import annotations

import re

from src.agent.llm import get_llm
from src.agent.schemas import RuleRecord, RunSchedulerResponse

_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_STRIP = re.compile(r"\d{4}-\d{2}-\d{2}|\b\d{1,2}:\d{2}\b|\[rule:[^\]]*\]")
_RULE_REF = re.compile(r"\[rule:([^#\]]+)#([^\]]+)\]")
_RULE_FIELDS = {"banned_hour_windows", "wbgt_stop_work_c", "seasonal_window",
                "workload_rest_ratios"}
_TOL = 0.01


class UngroundedBriefing(RuntimeError):
    """Raised when a draft still fails a check after one retry."""


def allowed_numbers(sched: RunSchedulerResponse) -> set[float]:
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
    return vals


def numeric_guard(text: str, sched: RunSchedulerResponse) -> list[str]:
    allowed = allowed_numbers(sched)
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
        self.numeric_ok = not numeric_guard(text, sched)
        self.rules_ok = not rule_guard(text, records)

    def __str__(self) -> str:
        return self.text


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
    rule_dicts = [r.model_dump(mode="json") for r in records]

    last_bad: list[str] = []
    for _ in range(retries + 1):
        text = llm.write_briefing(sched, rule_dicts, location_name=location_name)
        bad_num = numeric_guard(text, sched)
        bad_rule = rule_guard(text, records)
        if not bad_num and not bad_rule:
            return Briefing(text, sched, records)
        last_bad = [f"number {b!r} not in tool output" for b in bad_num] + \
                   [f"unresolved {b}" for b in bad_rule]

    raise UngroundedBriefing("; ".join(last_bad))
