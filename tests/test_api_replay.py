"""GET /api/replay serves a curated past week from committed data."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_replay_index_lists_at_least_one_week():
    r = client.get("/api/replay")
    assert r.status_code == 200
    weeks = r.json()["weeks"]
    assert len(weeks) >= 1
    assert weeks[0]["slug"] and weeks[0]["title"]


def test_replay_week_has_seven_days_and_three_policies():
    slug = client.get("/api/replay").json()["weeks"][0]["slug"]
    r = client.get(f"/api/replay/{slug}")
    assert r.status_code == 200
    j = r.json()
    assert len(j["days"]) == 7
    d0 = j["days"][0]
    for k in ("plan_peak", "calendar_peak", "reactive_peak", "wbgt_c"):
        assert k in d0
    assert j["pct_peak_reduction"] > 0


def test_replay_unknown_slug_404():
    assert client.get("/api/replay/nope").status_code == 404
    assert client.get("/api/replay/..%2Fmain").status_code in (404, 400)
