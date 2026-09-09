"""
POST /api/parse must fail closed: an ambiguous request comes back as a
clarification naming the missing safety-relevant fields, never a guess.
"""

import datetime as dt
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

os.environ.setdefault("HARARA_FORECAST_SOURCE", "mock")

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_parse_full_request_returns_intent():
    r = client.post("/api/parse", json={
        "text": "plan tomorrow for a heavy unacclimatised crew of 12 needing "
                "8 effective work-hours near Lusail"})
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == "parsed"
    assert body["intent"]["crew"]["workload"] == "heavy"
    assert body["intent"]["crew"]["acclimatised"] is False
    assert body["intent"]["location"]["name"] == "lusail"


def test_parse_ambiguous_returns_clarification():
    r = client.post("/api/parse", json={
        "text": "plan tomorrow for a crew of 12 near Lusail"})
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == "clarification"
    assert set(body["missing_fields"]) >= {"workload", "acclimatised"}
    assert "?" not in body["question"] or body["question"]  # a real prompt
    assert "guess" not in body


def test_parse_missing_location_asks_back():
    r = client.post("/api/parse", json={
        "text": "plan tomorrow for a heavy acclimatised crew needing 8 work-hours"})
    body = r.json()
    assert body["outcome"] == "clarification"
    assert "location" in body["missing_fields"]


def test_plan_rejects_far_future_date():
    far = (dt.date.today() + dt.timedelta(days=90)).isoformat()
    r = client.post("/api/plan", json={
        "lat": 25.2854, "lon": 51.531, "date": far,
        "required_work_hours": 8, "workload_class": "moderate",
        "acclimatised": True})
    assert r.status_code == 400


def test_plan_rejects_bad_body():
    r = client.post("/api/plan", json={
        "lat": 999, "lon": 51.531, "date": "2026-07-15"})
    assert r.status_code == 422
