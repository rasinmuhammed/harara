"""
GET /api/site-heat serves the precomputed satellite surface-heat layer, the
same "committed static data" pattern as /api/replay. These endpoints must
never appear anywhere near the WBGT or scheduler response shape.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_site_heat_index_always_200_even_if_empty():
    r = client.get("/api/site-heat")
    assert r.status_code == 200
    assert "sites" in r.json()


def test_site_heat_summary_matches_index_when_present():
    sites = client.get("/api/site-heat").json()["sites"]
    if not sites:
        return  # nothing precomputed in this environment yet; index shape is covered above
    slug = sites[0]["slug"]
    r = client.get(f"/api/site-heat/{slug}")
    assert r.status_code == 200
    j = r.json()
    for k in ("cv_rmse_c", "zones", "caveats", "lat", "lon"):
        assert k in j
    assert any("climatolog" in c.lower() for c in j["caveats"])
    assert any("does not feed" in c.lower() or "never" in c.lower() for c in j["caveats"])
    assert "wbgt" not in json_str(j).lower() or "does not feed" in json_str(j).lower()

    img = client.get(f"/api/site-heat/{slug}/image")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"


def json_str(j) -> str:
    import json
    return json.dumps(j)


def test_site_heat_unknown_slug_404():
    assert client.get("/api/site-heat/nope").status_code == 404
    assert client.get("/api/site-heat/nope/image").status_code == 404
    assert client.get("/api/site-heat/..%2Fmain").status_code in (404, 400)
