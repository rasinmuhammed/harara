"""
The agent eval harness runs and its hard safety targets hold for the
mock model: no ungrounded numbers in briefings, the numeric guard catches
every injected number, ambiguous requests always ask back, and every rule
reference resolves.
"""

import importlib.util
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "agent_eval",
    pathlib.Path(__file__).resolve().parent.parent / "eval" / "agent_eval.py")
agent_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent_eval)


def test_rule_extraction_matches_gold():
    r = agent_eval.eval_rule_extraction("mock")
    for field, s in r["per_field"].items():
        assert s["recall"] == 1.0 and s["precision"] == 1.0, field
    assert r["citation_validity"] == 1.0


def test_tool_calls_all_correct_and_fail_closed():
    r = agent_eval.eval_tool_calls("mock")
    assert r["outcome_exact_match"] == 1.0
    assert r["parsed_field_accuracy"] == 1.0
    assert r["ambiguous_asked_back"] == 1.0
    assert r["clarification_field_exact"] == 1.0


def test_briefings_have_no_ungrounded_numbers():
    r = agent_eval.eval_briefings("mock")
    assert r["ungrounded_numbers"] == 0
    assert r["hallucination_rate"] == 0.0
    assert r["guard_recall"] == 1.0
    assert r["failures"] == []


def test_every_rule_reference_resolves():
    r = agent_eval.eval_groundedness("mock")
    assert r["unresolved_references"] == []
    assert r["briefing_rules_ok"] is True
