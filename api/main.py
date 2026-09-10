"""
FastAPI app for the Harara scheduler.

    uvicorn api.main:app --reload            # local, from the repo root

Env:
    ALLOWED_ORIGINS   comma-separated CORS origins (default http://localhost:3000)
    HARARA_FORECAST_SOURCE   "open-meteo" (default) or "mock" for offline demos
    HARARA_LLM   model adapter for /api/chat ("mock" default; "anthropic"/"k2"
                 need their key in the environment, server-side only)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api import __version__
from api.chat import chat_stream
from api.chat_scope import counts as refusal_counts
from api.planning import (
    build_plan, climatology_compare, coolest_window, heat_trend, nowcast,
    weekly_outlook,
)
from api.ratelimit import chat_limiter
from api.schemas import (
    ChatRequest, HealthResponse, ParseClarification, ParseParsed, ParseRequest,
    PlanRequest, PlanResponse,
)
from src.agent.parse import parse_scheduling_request
from src.agent.schemas import ClarificationNeeded

FORECAST_SOURCE = os.environ.get("HARARA_FORECAST_SOURCE", "open-meteo")
FORECAST_HORIZON_DAYS = 15

app = FastAPI(
    title="Harara scheduler API",
    version=__version__,
    summary="Forecast-driven work/rest planning against Qatar Decision 17/2021.",
)

_origins = [o.strip() for o in
            os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Also reports which chat model is actually wired: `llm` is the configured
    adapter, `chat_agent` is true only if it constructs (its key is present)."""
    want = os.environ.get("HARARA_LLM", "mock")
    live = want
    agent = False
    if want != "mock":
        try:
            from src.agent.llm import get_llm
            get_llm(want)
            agent = True
        except Exception:
            live = "mock (fallback)"
    return HealthResponse(version=__version__, llm=live,
                          forecast_source=FORECAST_SOURCE, chat_agent=agent)


@app.post("/api/plan", response_model=PlanResponse)
def plan(req: PlanRequest) -> PlanResponse:
    today = dt.datetime.now(dt.timezone.utc).date()
    if not (today - dt.timedelta(days=1) <= req.date
            <= today + dt.timedelta(days=FORECAST_HORIZON_DAYS)):
        raise HTTPException(
            status_code=400,
            detail=f"date must be within today .. today+{FORECAST_HORIZON_DAYS} days",
        )
    try:
        return build_plan(req, forecast_source=FORECAST_SOURCE, today=today)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - upstream/forecast failure
        raise HTTPException(status_code=502,
                            detail=f"could not build a plan: {exc}") from exc


@app.post("/api/parse", response_model=ParseParsed | ParseClarification)
def parse(req: ParseRequest):
    today = dt.datetime.now(dt.timezone.utc).date()
    out = parse_scheduling_request(req.text, today=today)
    if isinstance(out, ClarificationNeeded):
        return ParseClarification(missing_fields=out.missing_fields,
                                  question=out.question)
    return ParseParsed(intent=out.intent.model_dump(mode="json"))


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    ok, retry_after = chat_limiter.check(ip)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail={"error": "Too many requests. Wait a minute and try again.",
                    "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )
    messages = [m.model_dump() for m in req.messages]
    return StreamingResponse(
        chat_stream(messages, req.context, forecast_source=FORECAST_SOURCE,
                    intent_override=req.intent),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/outlook")
def outlook(lat: float, lon: float, days: int = 7):
    """Daytime peak and mean WBGT per local day for the next `days` days at the
    chosen grid cell. Shares the plan cache and the rate-limit fallback."""
    today = dt.datetime.now(dt.timezone.utc).date()
    days = max(1, min(int(days), 14))
    try:
        return weekly_outlook(lat, lon, today=today, source=FORECAST_SOURCE, days=days)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502,
                            detail=f"could not build an outlook: {exc}") from exc


def _tool(fn, **kw):
    try:
        return fn(**kw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502,
                            detail=f"could not answer: {exc}") from exc


@app.get("/api/nowcast")
def api_nowcast(lat: float, lon: float):
    """Latest forecast hour: WBGT, the ACGIH work/rest band, and the 32.1 flag."""
    today = dt.datetime.now(dt.timezone.utc).date()
    return _tool(nowcast, lat=lat, lon=lon, today=today, source=FORECAST_SOURCE)


@app.get("/api/coolest-window")
def api_coolest_window(lat: float, lon: float, date: dt.date):
    today = dt.datetime.now(dt.timezone.utc).date()
    return _tool(coolest_window, lat=lat, lon=lon, date=date, today=today,
                source=FORECAST_SOURCE)


@app.get("/api/climatology")
def api_climatology(lat: float, lon: float, date: dt.date):
    """The day's forecast peak WBGT against the 16-year distribution for that
    time of year."""
    today = dt.datetime.now(dt.timezone.utc).date()
    return _tool(climatology_compare, lat=lat, lon=lon, date=date, today=today,
                source=FORECAST_SOURCE)


@app.get("/api/heat-trend")
def api_heat_trend(lat: float, lon: float):
    """Warm-season WBGT stop-work hours per year over the Doha record."""
    today = dt.datetime.now(dt.timezone.utc).date()
    return _tool(heat_trend, lat=lat, lon=lon, today=today)


@app.get("/api/chat-refusals")
def api_chat_refusals():
    """Chat intent-bucket counts for this process. Counts only, no message
    content, so misuse volume is visible without storing anything."""
    return {"buckets": refusal_counts()}


@app.get("/api/replay")
def replay_index():
    d = pathlib.Path(__file__).parent / "data" / "replay"
    weeks = []
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        j = json.loads(f.read_text())
        weeks.append({"slug": f.stem, "title": j.get("title", f.stem),
                      "subtitle": j.get("subtitle", "")})
    return {"weeks": weeks}


@app.get("/api/replay/{slug}")
def replay_week(slug: str):
    f = pathlib.Path(__file__).parent / "data" / "replay" / f"{slug}.json"
    if not f.exists() or "/" in slug or ".." in slug:
        raise HTTPException(status_code=404, detail="no such replay")
    return json.loads(f.read_text())
