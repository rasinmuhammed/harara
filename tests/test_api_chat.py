"""
Streaming /api/chat: a clarification streams a question and no artifact; a
complete request streams text then an artifact whose numbers match a direct
plan call; the endpoint is rate-limited per IP.
"""

import datetime as dt
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

os.environ.setdefault("HARARA_FORECAST_SOURCE", "mock")
os.environ.setdefault("HARARA_LLM", "mock")

from fastapi.testclient import TestClient

from api.main import app
from api.planning import plan_with_sched
from api.ratelimit import chat_limiter
from api.schemas import PlanRequest

client = TestClient(app)
TODAY = dt.date(2026, 7, 14)


def _frames(user_text: str) -> list[dict]:
    chat_limiter.reset()
    out: list[dict] = []
    with client.stream(
        "POST", "/api/chat",
        json={"messages": [{"role": "user", "content": user_text}],
              "context": {"today": TODAY.isoformat()}},
    ) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line and line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


def test_clarification_streams_question_and_no_artifact():
    frames = _frames("plan a shift for tomorrow")
    types = [f["type"] for f in frames]
    assert "clarification" in types
    assert "artifact" not in types
    clar = next(f for f in frames if f["type"] == "clarification")
    assert clar["question"]
    assert {"workload", "acclimatised", "required_work_hours", "location"} <= set(
        clar["missing_fields"])
    assert frames[-1]["type"] == "done"


def test_full_plan_streams_text_then_artifact_matching_a_direct_call():
    frames = _frames(
        "plan tomorrow for a heavy unacclimatised crew of 12 needing "
        "8 work-hours near Lusail")
    types = [f["type"] for f in frames]
    assert "text" in types and "artifact" in types
    assert types.index("text") < types.index("artifact")
    assert frames[-1]["type"] == "done"

    got = next(f for f in frames if f["type"] == "artifact")["plan"]["summary"]

    ref, _ = plan_with_sched(
        PlanRequest(lat=25.43, lon=51.49,
                    date=TODAY + dt.timedelta(days=1),
                    required_work_hours=8.0, workload_class="heavy",
                    acclimatised=False),
        forecast_source="mock")
    assert got == ref.model_dump(mode="json")["summary"]


def _stream_types(msgs: list[dict]) -> list[str]:
    chat_limiter.reset()
    with client.stream("POST", "/api/chat",
                       json={"messages": msgs,
                             "context": {"today": TODAY.isoformat()}}) as r:
        return [json.loads(l[6:])["type"] for l in r.iter_lines()
                if l and l.startswith("data: ")]


def test_follow_up_completes_an_earlier_request():
    msgs = [
        {"role": "user", "content": "plan tomorrow for a heavy acclimatised "
                                    "crew near Lusail"},
        {"role": "assistant", "content": "How many work-hours are needed?"},
        {"role": "user", "content": "we need 8 work-hours"},
    ]
    assert "artifact" in _stream_types(msgs)


def test_vague_follow_up_still_asks_back():
    msgs = [
        {"role": "user", "content": "plan tomorrow for a heavy acclimatised "
                                    "crew near Lusail"},
        {"role": "assistant", "content": "How many work-hours are needed?"},
        {"role": "user", "content": "not sure yet"},
    ]
    types = _stream_types(msgs)
    assert "clarification" in types and "artifact" not in types


def test_rate_limited_per_ip():
    chat_limiter.reset()
    body = {"messages": [{"role": "user", "content": "plan tomorrow"}],
            "context": {"today": TODAY.isoformat()}}
    codes = []
    for _ in range(chat_limiter.limit + 1):
        r = client.post("/api/chat", json=body)
        codes.append(r.status_code)
    assert codes[-1] == 429
    assert codes.count(200) == chat_limiter.limit
    err = r.json()["detail"]
    assert err["retry_after"] >= 1
    chat_limiter.reset()


def test_intent_override_skips_parsing():
    chat_limiter.reset()
    body = {
        "messages": [{"role": "user", "content": "use the fields below"}],
        "context": {"today": TODAY.isoformat()},
        "intent": {
            "target_local_date": (TODAY + dt.timedelta(days=1)).isoformat(),
            "required_work_hours": 8.0,
            "crew": {"workload": "moderate", "acclimatised": True, "crew_size": 10},
            "location": {"name": "doha", "lat": 25.2854, "lon": 51.531},
            "timezone": "Asia/Qatar",
        },
    }
    with client.stream("POST", "/api/chat", json=body) as r:
        types = [json.loads(l[6:])["type"] for l in r.iter_lines()
                 if l and l.startswith("data: ")]
    assert "parsing" not in [t for t in types]  # no parse status frame
    assert "artifact" in types and "clarification" not in types


def test_intent_override_incomplete_errors_closed():
    chat_limiter.reset()
    body = {
        "messages": [{"role": "user", "content": "x"}],
        "context": {"today": TODAY.isoformat()},
        "intent": {"required_work_hours": 8.0},  # missing crew, location, date
    }
    with client.stream("POST", "/api/chat", json=body) as r:
        types = [json.loads(l[6:])["type"] for l in r.iter_lines()
                 if l and l.startswith("data: ")]
    assert "error" in types and "artifact" not in types
