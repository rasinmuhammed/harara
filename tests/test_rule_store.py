"""
Rule store: citations must resolve to their cited span, tampering is
caught, and the extracted record projects cleanly onto the scheduler's
constraints. Also the MockLLM extractor against the eval documents.
"""

import datetime as dt
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.agent import rule_store
from src.agent.llm import MockLLM
from src.agent.schemas import (
    Citation, DateWindowWithCitation, HourWindowWithCitation,
    RuleConstraintsExtracted, RuleExtractionMeta, RuleRecord, RuleReview,
    RuleSource, ValueWithCitation,
)

EVAL_RULES = pathlib.Path(__file__).resolve().parent.parent / "eval/agent_eval/rules"
SOURCE = "Work is prohibited from 10:00 to 15:30. Stop at 32.1 degrees Celsius."


def _record(constraints, rule_id="unit-rule", base=pathlib.Path("x")):
    now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    return RuleRecord(
        rule_id=rule_id, version=1, title="unit", jurisdiction="test",
        source=RuleSource(type="text", path=str(base / "sources" / f"{rule_id}.txt"),
                          sha256="", retrieved_utc=now),
        extraction=RuleExtractionMeta(model="mock", prompt_version="v1", at_utc=now),
        constraints=constraints,
    )


def _good_constraints():
    span = (SOURCE.index("prohibited from 10:00 to 15:30"),)
    span = (span[0], span[0] + len("prohibited from 10:00 to 15:30"))
    return RuleConstraintsExtracted(
        banned_hour_windows=[HourWindowWithCitation(
            start="10:00", end="15:30",
            citation=Citation(span=span, quote=SOURCE[span[0]:span[1]]))],
        wbgt_stop_work_c=ValueWithCitation(
            value=32.1,
            citation=Citation(
                span=(SOURCE.index("32.1 degrees Celsius"),
                      SOURCE.index("32.1 degrees Celsius") + len("32.1 degrees Celsius")),
                quote="32.1 degrees Celsius")),
    )


def test_save_and_load_roundtrip(tmp_path):
    rec = _record(_good_constraints(), base=tmp_path)
    rule_store.save(rec, SOURCE, tmp_path)
    back = rule_store.load("unit-rule", tmp_path)
    assert back.constraints.wbgt_stop_work_c.value == 32.1
    assert back.source.sha256 == rule_store.sha256_text(SOURCE)


def test_save_refuses_bad_citation(tmp_path):
    bad = RuleConstraintsExtracted(
        wbgt_stop_work_c=ValueWithCitation(
            value=32.1, citation=Citation(span=(0, 5), quote="XXXXX")))
    with pytest.raises(ValueError):
        rule_store.save(_record(bad, base=tmp_path), SOURCE, tmp_path)


def test_load_detects_tampered_source(tmp_path):
    rec = _record(_good_constraints(), base=tmp_path)
    rule_store.save(rec, SOURCE, tmp_path)
    rule_store.source_path(rule_store.load("unit-rule", tmp_path)).write_text(
        SOURCE + " extra")
    with pytest.raises(ValueError):
        rule_store.load("unit-rule", tmp_path)


def test_next_version_increments(tmp_path):
    rec = _record(_good_constraints(), base=tmp_path)
    rule_store.save(rec, SOURCE, tmp_path)
    assert rule_store.next_version("unit-rule", tmp_path) == 2
    assert rule_store.next_version("other", tmp_path) == 1


def test_to_constraints_projection(tmp_path):
    rec = _record(_good_constraints(), base=tmp_path)
    c = rec.to_constraints()
    assert c.rule_ids == ["unit-rule"]
    assert c.wbgt_stop_work_c == 32.1
    assert [(w.start, w.end) for w in c.banned_hour_windows] == [("10:00", "15:30")]


@pytest.mark.parametrize("stem,banned,stop,season,ratios", [
    ("qatar-md-17-2021", 1, 32.1, ("06-01", "09-15"), 0),
    ("acgih-work-rest", 0, None, None, 2),
    ("platform-duty-of-care", 1, 31.0, ("07-01", "08-31"), 0),
    ("site-sop", 1, 30.5, ("05-01", "09-30"), 2),
])
def test_mock_extractor_on_eval_docs(stem, banned, stop, season, ratios):
    text = (EVAL_RULES / f"{stem}.txt").read_text()
    c = MockLLM().extract_rule(text)
    assert len(c.banned_hour_windows) == banned
    assert (c.wbgt_stop_work_c.value if c.wbgt_stop_work_c else None) == stop
    if season is None:
        assert c.seasonal_window is None
    else:
        assert (c.seasonal_window.start, c.seasonal_window.end) == season
    assert len(c.workload_rest_ratios) == ratios
    # every extracted citation resolves to its exact span
    rec = _record(c, rule_id=stem)
    assert rule_store.check_citations(rec, text) == []


def test_mock_extraction_matches_gold():
    """Field values agree with the hand-labelled gold for every eval doc."""
    for gold_path in sorted(EVAL_RULES.glob("*.gold.json")):
        stem = gold_path.name[:-len(".gold.json")]
        text = (EVAL_RULES / f"{stem}.txt").read_text()
        gold = json.loads(gold_path.read_text())
        got = MockLLM().extract_rule(text)

        g_stop = gold["wbgt_stop_work_c"]
        assert (got.wbgt_stop_work_c.value if got.wbgt_stop_work_c else None) == (
            g_stop["value"] if g_stop else None), stem
        g_season = gold["seasonal_window"]
        assert ((got.seasonal_window.start, got.seasonal_window.end)
                if got.seasonal_window else None) == (
            (g_season["start"], g_season["end"]) if g_season else None), stem
        assert sorted((w.start, w.end) for w in got.banned_hour_windows) == sorted(
            (w["start"], w["end"]) for w in gold["banned_hour_windows"]), stem
        assert sorted((r.workload, r.work_fraction)
                      for r in got.workload_rest_ratios) == sorted(
            (r["workload"], r["work_fraction"])
            for r in gold["workload_rest_ratios"]), stem
