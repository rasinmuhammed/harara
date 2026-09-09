"""
FastAPI app for the Harara scheduler MVP.

    uvicorn api.main:app --reload            # local, from the repo root

Env:
    ALLOWED_ORIGINS   comma-separated CORS origins (default http://localhost:3000)
    HARARA_FORECAST_SOURCE   "open-meteo" (default) or "mock" for offline demos
"""

from __future__ import annotations

import datetime as dt
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api import __version__
from api.planning import build_plan
from api.schemas import (
    HealthResponse, ParseClarification, ParseParsed, ParseRequest, PlanRequest,
    PlanResponse,
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
    return HealthResponse(version=__version__)


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
        return build_plan(req, forecast_source=FORECAST_SOURCE)
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
