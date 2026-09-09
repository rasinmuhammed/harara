"""
HTTP request/response models. Kept separate from src/agent/schemas.py, which
models the tool layer; these model the wire format a browser consumes. Where a
tool-layer type fits directly (WorkloadClass) it is reused.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.agent.schemas import WorkloadClass

PlanState = Literal["work", "reduced", "stop"]


class PlanRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    date: dt.date
    required_work_hours: float = Field(default=8.0, gt=0, le=14)
    workload_class: WorkloadClass = "moderate"
    acclimatised: bool = True
    tz: str = "Asia/Qatar"


class HourRow(BaseModel):
    local_time: dt.datetime
    hour: int
    wbgt_c: float
    plan_work_fraction: float
    calendar_work_fraction: float
    retained_load_plan: float
    retained_load_calendar: float
    plan_state: PlanState
    over_threshold: bool


class PlanSummary(BaseModel):
    peak_plan: float
    peak_calendar: float
    tail_plan: float
    tail_calendar: float
    pct_peak_reduction: float
    pct_tail_reduction: float
    work_hours_delivered_plan: float
    work_hours_delivered_calendar: float
    work_shortfall_plan: float
    stop_hours_plan: int
    stop_hours_calendar: int
    wbgt_ref_c: float
    threshold_c: float
    solver_status: str


class PlanMeta(BaseModel):
    model: str
    forecast_source: str
    lead_time_note: str
    generated_at: dt.datetime
    date: dt.date
    location: dict
    attribution: str


class PlanResponse(BaseModel):
    hours: list[HourRow]
    summary: PlanSummary
    meta: PlanMeta


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ParseParsed(BaseModel):
    outcome: Literal["parsed"] = "parsed"
    intent: dict


class ParseClarification(BaseModel):
    outcome: Literal["clarification"] = "clarification"
    missing_fields: list[str]
    question: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    context: Optional[dict] = None
