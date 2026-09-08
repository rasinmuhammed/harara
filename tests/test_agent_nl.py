"""
The natural-language front door (fail-closed parsing), the grounded
briefing generator (numeric and rule guards), and the monitoring
material-change check.
"""

import datetime as dt
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.agent import tools
from src.agent.brief import (
    UngroundedBriefing, generate_briefing, numeric_guard,
)
from src.agent.llm import MockLLM
from src.agent.monitor import material_changes, review_plan
from src.agent.parse import parse_scheduling_request
from src.agent.schemas import (
    ClarificationNeeded, ComputeWbgtRequest, CrewParams, GetForecastRequest,
    ParsedRequest, PlanIntent, RunSchedulerRequest, RuleConstraints,
)

TODAY = dt.date(2026, 7, 14)
DOHA = dict(lat=25.27, lon=51.61)


def _sched(required=8.0, workload="moderate", acclimatised=True):
    d = dt.date(2026, 7, 15)
    fc = tools.get_forecast(GetForecastRequest(**DOHA, start_date=d, end_date=d,
                                               source="mock"))
    wb = tools.compute_wbgt(ComputeWbgtRequest(hours=fc.hours, **DOHA))
    return tools.run_scheduler(RunSchedulerRequest(
        target_local_date=d, required_work_hours=required,
        crew=CrewParams(workload=workload, acclimatised=acclimatised,
                        crew_size=10),
        constraints=RuleConstraints(
            banned_hour_windows=[], wbgt_stop_work_c=32.1),
        wbgt_hours=wb.hours))


# ------------------------------------------------------------------ parsing
def test_parse_full_request():
    out = parse_scheduling_request(
        "plan tomorrow for a heavy unacclimatised crew of 12 needing "
        "8 effective work-hours near Lusail", today=TODAY)
    assert isinstance(out, ParsedRequest)
    i = out.intent
    assert i.target_local_date == dt.date(2026, 7, 15)
    assert i.crew.workload == "heavy"
    assert i.crew.acclimatised is False
    assert i.crew.crew_size == 12
    assert i.required_work_hours == 8.0
    assert i.location.name == "lusail"


@pytest.mark.parametrize("text,field", [
    ("plan tomorrow for an unacclimatised crew needing 8 work-hours at Lusail",
     "workload"),
    ("plan tomorrow for a heavy crew needing 8 work-hours at Lusail",
     "acclimatised"),
    ("plan tomorrow for a heavy unacclimatised crew needing 8 work-hours",
     "location"),
    ("plan for a heavy unacclimatised crew needing 8 work-hours at Lusail",
     "target_local_date"),
    ("plan tomorrow for a heavy unacclimatised crew at Lusail",
     "required_work_hours"),
])
def test_parse_fails_closed_on_missing_safety_field(text, field):
    out = parse_scheduling_request(text, today=TODAY)
    assert isinstance(out, ClarificationNeeded)
    assert field in out.missing_fields


def test_parse_guards_against_unsupported_llm_output():
    """Even if the model returns a full request, a value with no evidence
    in the text is rejected."""
    class Overconfident(MockLLM):
        def parse_request(self, text, *, today):
            return ParsedRequest(intent=PlanIntent(
                target_local_date=today + dt.timedelta(days=1),
                required_work_hours=8.0,
                crew=CrewParams(workload="light", acclimatised=True,
                                crew_size=1),
                location=__import__("src.agent.schemas", fromlist=["Location"])
                .Location(name="doha", lat=25.28, lon=51.53)))

    out = parse_scheduling_request("schedule something for the crew",
                                   today=TODAY, llm=Overconfident())
    assert isinstance(out, ClarificationNeeded)
    assert {"workload", "acclimatised", "location",
            "required_work_hours"} <= set(out.missing_fields)


# ---------------------------------------------------------------- briefing
def test_numeric_guard_flags_foreign_number():
    s = _sched()
    good = MockLLM().write_briefing(s, [], location_name="Lusail")
    assert numeric_guard(good, s) == []
    assert numeric_guard(good + "\nProjected cost 4210 QAR.", s) == ["4210"]


def test_generate_briefing_is_grounded():
    s = _sched()
    b = generate_briefing(s, location_name="Lusail")
    assert b.numeric_ok and b.rules_ok
    assert str(b.plan_peak_strain if False else s.plan_peak_strain) in b.text


def test_generate_briefing_rejects_hallucinated_number():
    s = _sched()

    class Liar(MockLLM):
        def write_briefing(self, sched, rules, *, location_name):
            return super().write_briefing(sched, rules,
                                          location_name=location_name) \
                + "\nHeat index hits 58 today."

    with pytest.raises(UngroundedBriefing):
        generate_briefing(s, location_name="Lusail", llm=Liar())


# --------------------------------------------------------------- monitoring
def test_material_changes_none_when_identical():
    s = _sched()
    assert material_changes(s, s) == []
    assert review_plan(s, s, target_date=dt.date(2026, 7, 15)) is None


def test_material_changes_flags_shortfall_and_hours():
    base = _sched(required=6.0)
    stressed = _sched(required=13.0, workload="heavy", acclimatised=False)
    fired = material_changes(base, stressed)
    assert fired  # a 6h -> 13h heavy unacclimatised swing moves the load
    alert = review_plan(base, stressed, target_date=dt.date(2026, 7, 15))
    assert alert is not None and alert.text
    assert set(alert.fired) == set(fired)
