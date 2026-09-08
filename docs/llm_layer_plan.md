# LLM Layer: Design

This document fixes the interfaces before any agent code is written: the tool
schemas, the rule-store record format, the "material change" rule for
monitoring, and the evaluation datasets.

## Principle

The language model never produces a number. WBGT, schedules, strain, thresholds
and rule constraints are computed or looked up by deterministic, tested Python.
The model parses input into tool calls, extracts rules into cited structured
records, writes briefings that only restate tool outputs and cited text, and
flags plan changes for human review.

Enforcement:

- The NL parser returns a validated tool-call object or a `ClarificationNeeded`
  object. It never fills a safety-relevant field (workload class,
  acclimatisation, location) with a default.
- The briefing generator output passes through `numeric_guard`, which
  tokenises every number in the text and rejects the briefing if any token is
  absent from the set of numbers in the tool outputs it was given.
- `run_scheduler` and `lookup_rule` refuse rule records whose `status` is not
  `confirmed`.
- The LLM is reached only through `src/agent/llm.py::LLM`. A `MockLLM`
  deterministic implementation is used in tests and in the offline pipeline.

## 1. Tool schemas

Module: `src/agent/tools.py`. Schemas are pydantic v2 models; each tool is a
function `tool_name(request: Request) -> Response` that wraps existing code and
adds no domain logic. `src/agent/schedule_service.py` holds the typed
scheduler entry point.

### 1.1 get_forecast

```
GetForecastRequest:
  lat: float            # [-90, 90]
  lon: float            # [-180, 180]
  start_date: date
  end_date: date        # >= start_date; (end - start) <= 16 days
  source: "open-meteo" | "mock" = "open-meteo"

WeatherHour:
  time_utc: datetime
  temp_c: float
  rh_pct: float          # [0, 100]
  wind_ms: float         # >= 0
  shortwave_wm2: float    # >= 0
  direct_wm2: float       # >= 0
  pressure_hpa: float

GetForecastResponse:
  lat: float
  lon: float
  timezone: str          # "UTC"
  hours: list[WeatherHour]
  provider: str
  retrieved_utc: datetime
```

Wraps a forecast fetch (`scripts/fetch_forecast.py`, Open-Meteo forecast API).
`source="mock"` returns a deterministic synthetic day for tests and offline
runs.

### 1.2 compute_wbgt

```
ComputeWbgtRequest:
  hours: list[WeatherHour]
  lat: float
  lon: float

WbgtHour:
  time_utc: datetime
  wbgt_c: float

ComputeWbgtResponse:
  hours: list[WbgtHour]
  method: "liljegren-thermofeel"
```

Wraps `src.wbgt.wbgt_liljegren_c` and `src.solar.cos_solar_zenith_angle`. Pure.

### 1.3 run_scheduler

```
CrewParams:
  workload: "light" | "moderate" | "heavy" | "very_heavy"
  acclimatised: bool
  crew_size: int         # >= 1; recorded, does not affect the plan

RuleConstraints:
  rule_ids: list[str]                     # confirmed rule-store records to apply
  banned_hour_windows: list[HourWindow]    # merged from the rules
  wbgt_stop_work_c: float | None
  seasonal_window: DateWindow | None
  working_window: HourWindow = 05:00-19:00 # local clock hours worked at all

HourWindow: {start: "HH:MM", end: "HH:MM"}
DateWindow: {start: "MM-DD", end: "MM-DD"}

RunSchedulerRequest:
  wbgt_hours: list[WbgtHour] | None        # provide this or a forecast
  forecast: GetForecastResponse | None
  target_local_date: date
  timezone: str = "Asia/Qatar"
  required_work_hours: float               # (0, 14]
  crew: CrewParams
  constraints: RuleConstraints
  beta: float = 0.90                        # CVaR tail level
  seed: int = 0

HourPlan:
  local_time: datetime
  wbgt_c: float
  work_fraction: float                     # {0, 0.25, 0.5, 0.75, 1.0}
  allowed: bool
  reason_not_allowed: str | None           # "calendar-ban" | "wbgt-stop-work" | "outside-working-window" | "off-season"

RunSchedulerResponse:
  plan: list[HourPlan]
  plan_peak_strain: float
  plan_tail_strain: float                  # p90 of retained load across hours
  baseline_peak_strain: float              # calendar-ban policy on the same WBGT
  baseline_tail_strain: float
  work_hours_delivered: float
  work_hours_required: float
  work_shortfall: float                    # max(0, required - delivered)
  wbgt_ref_c: float                        # ACGIH continuous limit for the crew
  allowed_hours: list[str]                 # "HH:MM"
  stop_work_hours: list[str]               # forecast WBGT above the threshold in the window
  applied_rule_ids: list[str]
  solver_status: str                       # "optimal" | "greedy_fallback"
  notes: list[str]
```

Derivation, all deterministic:

- `wbgt_ref_c` from `src.heat_stress`: the WBGT at which the crew's workload can
  be worked continuously (the 100% row of the acclimatised or unacclimatised
  ACGIH table).
- `allowed[h]` is false if the local hour is outside `working_window`, inside
  any `banned_hour_windows`, outside `seasonal_window`, or the forecast WBGT at
  that hour exceeds `wbgt_stop_work_c`.
- Plan: `src.scheduler.schedule_cvar` on a single-scenario WBGT vector (the
  forecast) with `wbgt_ref = wbgt_ref_c`, `allowed` as above,
  `w_req = required_work_hours`, `beta`. Baseline:
  `src.scheduler.policy_calendar` on the same WBGT.
- `run_scheduler` rejects any `rule_id` whose stored `status != "confirmed"`
  and records that in `notes`.

### 1.4 lookup_rule

```
LookupRuleRequest:
  rule_id: str | None
  query: str | None        # keyword match over title / jurisdiction / tags
  include_unconfirmed: bool = false

LookupRuleResponse:
  matches: list[RuleRecord]   # RuleRecord is the stored JSON (section 2), parsed
```

Keyword match only. No embeddings, no model call.

## 2. Rule-store record format

`data/rules/<rule_id>.json`, with the source text at
`data/rules/sources/<rule_id>.<ext>`.

```json
{
  "rule_id": "qatar-md-17-2021",
  "version": 1,
  "title": "Qatar Ministerial Decision No. 17 of 2021",
  "jurisdiction": "QA",
  "tags": ["construction", "outdoor-work", "wbgt"],
  "source": {
    "type": "text",
    "path": "data/rules/sources/qatar-md-17-2021.txt",
    "sha256": "<hex>",
    "retrieved_utc": "2026-09-09T00:00:00Z",
    "note": "Representative English excerpt; verify against the official gazette before operational use."
  },
  "status": "unconfirmed",
  "review": { "by": null, "at": null },
  "extraction": { "model": "mock", "prompt_version": "1", "at_utc": "2026-09-09T00:00:00Z" },
  "constraints": {
    "banned_hour_windows": [
      { "start": "10:00", "end": "15:30",
        "citation": { "span": [412, 486], "quote": "work in open spaces ... is prohibited from 10:00 to 15:30" } }
    ],
    "wbgt_stop_work_c": {
      "value": 32.1,
      "citation": { "span": [601, 672], "quote": "work must stop whenever the WBGT index reaches 32.1 degrees Celsius" }
    },
    "seasonal_window": {
      "start": "06-01", "end": "09-15",
      "citation": { "span": [300, 360], "quote": "from the first of June until the fifteenth of September" }
    },
    "workload_rest_ratios": []
  }
}
```

Rules:

- Every value under `constraints` is an object with its own `citation`
  (`span`: `[start, end]` character offsets into the source file; `quote`: the
  verbatim substring). `span` and `quote` must be consistent; a loader check
  asserts `source_text[span[0]:span[1]] == quote`.
- `status` starts as `unconfirmed`. `scripts/rules_review.py --confirm
  <rule_id> --by <name>` sets it to `confirmed` and stamps `review`.
- A new extraction of the same `rule_id` writes `version + 1`, never overwrites.
- `constraints` with no citation is rejected at write time.

## 3. "Material change" for the monitoring loop

`src/agent/monitor.py`. A freshly re-optimised plan for a working day is
materially different from the last issued plan for that day if any of:

1. Any hour changes `allowed` state (allowed to banned or banned to allowed).
2. `abs(new.plan_peak_strain - issued.plan_peak_strain) / max(issued.plan_peak_strain, 1e-6) > 0.15`.
3. `abs(new.plan_tail_strain - issued.plan_tail_strain) / max(issued.plan_tail_strain, 1e-6) > 0.15`.
4. `len(new.stop_work_hours) != len(issued.stop_work_hours)`.
5. `new.work_shortfall > 0` and `issued.work_shortfall == 0` (a shortfall
   appeared).

`MATERIAL_STRAIN_FRAC = 0.15` is a module constant. When any condition fires,
the agent drafts an alert listing which conditions fired and the specific
before/after values, each value taken verbatim from a scheduler response. The
scheduler does the optimisation; the agent only selects and explains.

## 4. Evaluation datasets

`eval/agent_eval.py`, data under `eval/agent_eval/`. Fixed seed. Runs against
`MockLLM` by default; a `--model` flag can point at a real adapter.

### 4.1 Rule extraction (`eval/agent_eval/rules/`)

At least three source documents, each with a hand-labelled gold record:

1. `qatar-md-17-2021.txt` - representative English excerpt of the midday-ban
   decision (banned window, WBGT threshold, seasonal window).
2. `acgih-work-rest.txt` - the ACGIH TLV screening description (workload
   classes and rest ratios; no banned window).
3. `platform-duty-of-care.txt` - a synthetic delivery-platform policy (a
   softer "reduce dispatch" threshold, a cooling-point requirement, no legal
   ban).
4. `site-sop.txt` - a synthetic contractor site SOP (a stricter local window,
   a lower stop-work threshold).

Metric: field-level precision and recall over the constraint fields
(`banned_hour_windows`, `wbgt_stop_work_c`, `seasonal_window`,
`workload_rest_ratios`), plus citation validity (does the extracted span match
the quoted text). Report per document and pooled.

### 4.2 Tool-call correctness (`eval/agent_eval/nl_requests.jsonl`)

15 to 20 requests, each with an expected outcome: either a parsed
`RunSchedulerRequest` (partial, the fields the sentence specifies) or
`ClarificationNeeded` with the expected missing fields. Includes:

- Fully specified requests.
- Missing workload class, missing acclimatisation, vague location ("near the
  port"), missing required hours, contradictory constraints.

Metrics: exact-match rate on the outcome type; per-field accuracy on parsed
requests; and the fraction of ambiguous inputs that correctly return a
clarification (target: all of them).

### 4.3 No hallucinated numbers (`eval/agent_eval/briefings.jsonl`)

Adversarial cases: a scheduler response plus a prompt that tempts invention
("add a 10% safety buffer to the peak", "estimate how many of the 12 workers
will be affected", "round the work hours up"). For each generated briefing,
assert that every numeric token appears in the scheduler response it was given.
Metric: hallucinated-number rate (target: 0).

### 4.4 Groundedness

Every rule reference token in generated text (`[rule:<id>#<field>]`) must
resolve to a stored record and a real citation span. Metric: unresolved
reference rate (target: 0).

## Build order

1. `src/agent/schedule_service.py` and `src/agent/tools.py` with tests. No LLM.
2. Rule-store loader/writer, `scripts/rules_ingest.py` (uses `MockLLM`
   extractor), `scripts/rules_review.py`, and the four source docs plus gold
   labels.
3. `src/agent/llm.py` interface and `MockLLM`.
4. NL parser (`src/agent/parse.py`) with fail-closed behaviour, and the
   briefing generator (`src/agent/brief.py`) with `numeric_guard`.
5. `src/agent/monitor.py`.
6. `eval/agent_eval.py` and the datasets; wire skippable stages into
   `run_all.sh`.
7. A real model adapter, chosen last.
