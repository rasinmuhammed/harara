"""
Request and response schemas for the agent tool layer (docs/llm_layer_plan.md
section 1). Pydantic v2 models: construction validates, so an invalid tool
call fails before any computation runs.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

WorkloadClass = Literal["light", "moderate", "heavy", "very_heavy"]
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_MMDD = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


class HourWindow(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not _HHMM.match(v):
            raise ValueError(f"expected HH:MM, got {v!r}")
        return v

    def contains_hour(self, hour_float: float) -> bool:
        s = int(self.start[:2]) + int(self.start[3:]) / 60.0
        e = int(self.end[:2]) + int(self.end[3:]) / 60.0
        return s <= hour_float < e


class DateWindow(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _mmdd(cls, v: str) -> str:
        if not _MMDD.match(v):
            raise ValueError(f"expected MM-DD, got {v!r}")
        return v

    def contains(self, d: dt.date) -> bool:
        md = (d.month, d.day)
        s = (int(self.start[:2]), int(self.start[3:]))
        e = (int(self.end[:2]), int(self.end[3:]))
        return s <= md <= e if s <= e else (md >= s or md <= e)


# --------------------------------------------------------------------------
# get_forecast
# --------------------------------------------------------------------------
class GetForecastRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    start_date: dt.date
    end_date: dt.date
    source: Literal["open-meteo", "mock"] = "open-meteo"

    @model_validator(mode="after")
    def _range(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date before start_date")
        if (self.end_date - self.start_date).days > 16:
            raise ValueError("forecast range limited to 16 days")
        return self


class WeatherHour(BaseModel):
    time_utc: dt.datetime
    temp_c: float
    rh_pct: float = Field(ge=0, le=100)
    wind_ms: float = Field(ge=0)
    shortwave_wm2: float = Field(ge=0)
    direct_wm2: float = Field(ge=0)
    pressure_hpa: float = Field(gt=0)


class GetForecastResponse(BaseModel):
    lat: float
    lon: float
    timezone: str = "UTC"
    hours: list[WeatherHour]
    provider: str
    retrieved_utc: dt.datetime


# --------------------------------------------------------------------------
# compute_wbgt
# --------------------------------------------------------------------------
class ComputeWbgtRequest(BaseModel):
    hours: list[WeatherHour]
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class WbgtHour(BaseModel):
    time_utc: dt.datetime
    wbgt_c: float


class ComputeWbgtResponse(BaseModel):
    hours: list[WbgtHour]
    method: Literal["liljegren-thermofeel"] = "liljegren-thermofeel"


# --------------------------------------------------------------------------
# run_scheduler
# --------------------------------------------------------------------------
class CrewParams(BaseModel):
    workload: WorkloadClass
    acclimatised: bool
    crew_size: int = Field(ge=1)


class RuleConstraints(BaseModel):
    rule_ids: list[str] = Field(default_factory=list)
    banned_hour_windows: list[HourWindow] = Field(default_factory=list)
    wbgt_stop_work_c: Optional[float] = None
    seasonal_window: Optional[DateWindow] = None
    working_window: HourWindow = HourWindow(start="05:00", end="19:00")


class RunSchedulerRequest(BaseModel):
    target_local_date: dt.date
    required_work_hours: float = Field(gt=0, le=14)
    crew: CrewParams
    constraints: RuleConstraints
    timezone: str = "Asia/Qatar"
    wbgt_hours: Optional[list[WbgtHour]] = None
    forecast: Optional[GetForecastResponse] = None
    beta: float = Field(default=0.90, gt=0, lt=1)
    seed: int = 0
    # worker-time constraints (docs/scheduler_worker_time_plan.md)
    max_span_hours: Optional[float] = Field(default=None, gt=0, le=24)
    rest_allowance_hours: float = Field(default=2.0, ge=0, le=12)
    earlier_start: bool = True

    @model_validator(mode="after")
    def _has_input(self):
        if not self.wbgt_hours and not self.forecast:
            raise ValueError("provide wbgt_hours or forecast")
        return self


class HourPlan(BaseModel):
    local_time: dt.datetime
    wbgt_c: float
    work_fraction: float
    allowed: bool
    reason_not_allowed: Optional[str] = None
    on_site: bool = True                       # inside the plan's on-site window
    earlier_start_work_fraction: float = 0.0   # the earlier-start baseline


class RunSchedulerResponse(BaseModel):
    plan: list[HourPlan]
    plan_peak_strain: float
    plan_tail_strain: float
    baseline_peak_strain: float
    baseline_tail_strain: float
    work_hours_delivered: float
    work_hours_required: float
    work_shortfall: float
    wbgt_ref_c: float
    allowed_hours: list[str]
    stop_work_hours: list[str]
    applied_rule_ids: list[str]
    solver_status: str
    notes: list[str] = Field(default_factory=list)
    # worker-time (docs/scheduler_worker_time_plan.md)
    plan_window: Optional[list[str]] = None    # ["HH:00", "HH:00"] on-site window
    plan_span_hours: float = 0.0
    plan_onsite_rest_hours: float = 0.0
    plan_work_blocks: int = 0
    earlier_start_peak_strain: float = 0.0
    earlier_start_tail_strain: float = 0.0
    earlier_start_span_hours: float = 0.0


# --------------------------------------------------------------------------
# lookup_rule
# --------------------------------------------------------------------------
class Citation(BaseModel):
    span: tuple[int, int]
    quote: str


class ValueWithCitation(BaseModel):
    value: float
    citation: Citation


class HourWindowWithCitation(HourWindow):
    citation: Citation


class DateWindowWithCitation(DateWindow):
    citation: Citation


class RestRatioWithCitation(BaseModel):
    workload: WorkloadClass
    work_fraction: float = Field(gt=0, le=1)
    citation: Citation


class RuleConstraintsExtracted(BaseModel):
    banned_hour_windows: list[HourWindowWithCitation] = Field(default_factory=list)
    wbgt_stop_work_c: Optional[ValueWithCitation] = None
    seasonal_window: Optional[DateWindowWithCitation] = None
    workload_rest_ratios: list[RestRatioWithCitation] = Field(default_factory=list)


class RuleSource(BaseModel):
    type: Literal["text", "pdf"]
    path: str
    sha256: str
    retrieved_utc: dt.datetime
    note: Optional[str] = None


class RuleReview(BaseModel):
    by: Optional[str] = None
    at: Optional[dt.datetime] = None


class RuleExtractionMeta(BaseModel):
    model: str
    prompt_version: str
    at_utc: dt.datetime


class RuleRecord(BaseModel):
    rule_id: str
    version: int = Field(ge=1)
    title: str
    jurisdiction: str
    tags: list[str] = Field(default_factory=list)
    source: RuleSource
    status: Literal["unconfirmed", "confirmed"] = "unconfirmed"
    review: RuleReview = Field(default_factory=RuleReview)
    extraction: RuleExtractionMeta
    constraints: RuleConstraintsExtracted

    def to_constraints(self) -> RuleConstraints:
        """Project the extracted record onto the scheduler's RuleConstraints."""
        c = self.constraints
        return RuleConstraints(
            rule_ids=[self.rule_id],
            banned_hour_windows=[HourWindow(start=w.start, end=w.end)
                                 for w in c.banned_hour_windows],
            wbgt_stop_work_c=(c.wbgt_stop_work_c.value
                              if c.wbgt_stop_work_c else None),
            seasonal_window=(DateWindow(start=c.seasonal_window.start,
                                        end=c.seasonal_window.end)
                             if c.seasonal_window else None),
        )


class LookupRuleRequest(BaseModel):
    rule_id: Optional[str] = None
    query: Optional[str] = None
    include_unconfirmed: bool = False

    @model_validator(mode="after")
    def _one_of(self):
        if not self.rule_id and not self.query:
            raise ValueError("provide rule_id or query")
        return self


class LookupRuleResponse(BaseModel):
    matches: list[RuleRecord]


# --------------------------------------------------------------------------
# NL parsing outcome
# --------------------------------------------------------------------------
class Location(BaseModel):
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class PlanIntent(BaseModel):
    """The safety-relevant fields of a scheduling request, resolved from
    natural language. The weather input is attached later by the caller,
    which fetches a forecast for `location` before calling the scheduler."""

    target_local_date: dt.date
    required_work_hours: float = Field(gt=0, le=14)
    crew: CrewParams
    location: Location
    timezone: str = "Asia/Qatar"

    def to_request(
        self,
        *,
        wbgt_hours: Optional[list[WbgtHour]] = None,
        forecast: Optional[GetForecastResponse] = None,
        constraints: Optional[RuleConstraints] = None,
        beta: float = 0.90,
        seed: int = 0,
    ) -> RunSchedulerRequest:
        return RunSchedulerRequest(
            target_local_date=self.target_local_date,
            required_work_hours=self.required_work_hours,
            crew=self.crew,
            constraints=constraints or RuleConstraints(),
            timezone=self.timezone,
            wbgt_hours=wbgt_hours,
            forecast=forecast,
            beta=beta,
            seed=seed,
        )


class ClarificationNeeded(BaseModel):
    missing_fields: list[str]
    question: str


class ParsedRequest(BaseModel):
    tool: Literal["run_scheduler"] = "run_scheduler"
    intent: PlanIntent
