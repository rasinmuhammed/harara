# Harara scheduler API

A thin FastAPI service over the deterministic work/rest scheduler in `src/`.
It adds no domain logic: every number comes from the tool layer in
`src/agent/` (`get_forecast` -> `compute_wbgt` -> `run_scheduler`). The
comparison it exposes is the one in `docs/technical_report.md` section 8 --
the forecast-driven optimiser against Qatar Decision 17/2021's fixed
10:00-15:30 calendar ban, at the same delivered work-hours and, now, with the
crew's time on site held no longer than that rule keeps them.

## Endpoints

### `POST /api/plan`

```jsonc
// request
{ "lat": 25.2854, "lon": 51.5310, "date": "2026-09-14",
  "required_work_hours": 8, "workload_class": "moderate",
  "acclimatised": true, "tz": "Asia/Qatar",
  // optional worker-time controls
  "max_span_hours": null,        // default: required_work_hours + rest_allowance_hours
  "rest_allowance_hours": 2.0,   // on-site hours allowed over the work owed
  "earlier_start": true }        // include the earlier-start fixed block
```

Returns `hours[]` (per local hour 05:00-18:00: `wbgt_c`,
`plan_work_fraction`, `calendar_work_fraction`, `earlier_start_work_fraction`,
`retained_load_plan`, `retained_load_calendar`, `retained_load_earlier`,
`plan_state` = work|reduced|stop, `over_threshold`, `on_site`),
a `summary` (`peak_*`, `tail_*` = p90, `pct_*_reduction`, delivered hours and
stop hours for both policies, `wbgt_ref_c`, `threshold_c`, `solver_status`),
and `meta` (model, forecast source, lead-time note, Open-Meteo CC-BY
attribution). `400` if `date` is outside the forecast horizon, `422` on an
invalid body, `502` if the forecast upstream fails.

The scheduler now solves the CVaR work/rest LP inside an outer search over
contiguous on-site windows. The window is capped at `required_work_hours +
rest_allowance_hours` and the day is held to at most two work blocks, so the
plan can never keep a crew on site longer, resting in the heat longer, or in
more pieces than the fixed 17/2021 calendar rule. The `summary` reports both
sides of that: `span_hours_plan` / `span_hours_calendar`,
`onsite_rest_hours_plan` / `_calendar`, `work_blocks_plan` / `_calendar`,
`cumulative_exposure_plan` / `_calendar` (time-integrated heat dose over worked
hours), and `earlier_start_fixed` (`{peak, tail, span_hours}` for the plain
earlier-start block). Each `hours[]` row carries `on_site` for the plan's
window.

Note: neither policy is given a hard 32.1 C stop -- the optimiser minimises
retained heat load at equal output within the on-site window, and hours where
it still schedules work above 32.1 C are flagged `over_threshold` for the
client to surface. The 32.1 C stop-work clause is applied on top by the
operator. Constraining worker time removes the peak-load advantage the
unbounded optimiser showed: see `docs/technical_report.md` section 8.

### `POST /api/parse` (optional NL box)

`{ "text": "..." }` -> `{ "outcome": "parsed", "intent": {...} }` or
`{ "outcome": "clarification", "missing_fields": [...], "question": "..." }`.
Backed by the fail-closed parser in `src/agent/parse.py` with the
deterministic mock model -- it never guesses a safety-relevant field.

### `POST /api/chat` (streaming, SSE)

`{ "messages": [...], "context": { "req": {...}?, "plan": {...}?, "gathering": bool? } }`.
Frames: `status`, `text` (word by word), `clarification`, `artifact` (the full
`/api/plan` payload), `emergency` (a banner), `source` (`label`, `detail` for
a grounded answer), `notice` (`out_of_scope` | `no_match`), `error`, `done`.

The assistant is scope-locked. Every message is classified by keyword and
pattern before any model call into `plan_request`, `weather_question`,
`heat_safety_question`, `rules_question`, `about_harara`, `emergency` or
`out_of_scope`. Out-of-scope and prompt-injection messages get one fixed
reply, no model call. An emergency message gets a fixed knowledge-base
first-response block with a banner. Heat, first-aid and "what is Harara"
questions are served from a curated KB entry's own text with its source;
rules questions from the rule store or a cited KB summary; weather questions
from a forecast tool (`nowcast`, `coolest_window`, `climatology_compare`,
`heat_trend`, `weekly_outlook`) as a deterministic sentence with its source.
Only a multi-day forecast comparison is phrased by the model, and only after
the numeric guard and an output scope guard pass. The model never emits a
number that reaches the client.

The response also carries `day_curve` when a forecast was fetched: the full
local 24-hour WBGT series for the day (`points[]` with `hour`, `wbgt_c`,
`over_threshold`, `is_daylight` for 05:00 to 18:00), the coolest 3-hour
working window, the hours over 32.1 C, the overnight minimum, and a note that
night hours carry no solar term. It is a research context view, not part of
the plan.

### `GET /api/day-curve`, `/api/nowcast`, `/api/coolest-window`, `/api/climatology`, `/api/heat-trend`

`{ "lat", "lon" }` (plus `date` for coolest-window and climatology). The same
deterministic tools the chat narrates: current WBGT and the ACGIH band; the
coolest working hours and the 32.1 C crossings; the day's forecast peak
against the 16-year distribution; warm-season stop-work hours per year over
the Doha record. `502` if the forecast upstream fails.

### `GET /api/chat-refusals`

`{ "buckets": { "<intent>": <count> } }` for this process. Counts only, no
message content.

### `GET /api/site-heat`, `GET /api/site-heat/{slug}`, `GET /api/site-heat/{slug}/image`

A precomputed, advisory satellite surface-heat layer for the app's known
location presets (Doha, Lusail, Industrial Area, Al Wakrah, Mesaieed), built
offline by `scripts/build_site_heat_presets.py` from free Landsat and
Sentinel-2 imagery (see `docs/technical_report.md` section 5.9) and served
as static files, the same pattern as `/api/replay`. `/api/site-heat` lists
the available slugs; `/api/site-heat/{slug}` returns the summary (bounding
box, spatial cross-validation RMSE, the vegetated-vs-bare temperature
difference, and the caveats); `/api/site-heat/{slug}/image` returns the
rendered PNG overlay. `404` for an unknown slug.

This is a **climatological pattern from recent summers, not a live
reading**, and it **never appears in `/api/plan` or feeds the WBGT or
scheduler path**. It exists so a visitor can see where a specific
neighbourhood tends to run hotter or cooler, for siting and awareness, not
as a second safety number. Refresh the presets by rerunning the build
script; there is no live compute in this endpoint, it only serves what that
script has already written to `api/data/site_heat/`.

### `GET /api/health`

`{ "status", "version", "llm", "forecast_source", "chat_agent" }`. `chat_agent`
is `true` only when `HARARA_LLM` is a real adapter whose key is present, so a
deploy can confirm the conversational path is live.

## Run locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r api/requirements.txt
uvicorn api.main:app --reload            # from the repo root
# http://127.0.0.1:8000/docs  for the OpenAPI UI
```

Environment:

| var | default | meaning |
|---|---|---|
| `ALLOWED_ORIGINS` | `http://localhost:3000` | comma-separated CORS origins |
| `HARARA_FORECAST_SOURCE` | `open-meteo` | `mock` serves a deterministic synthetic day, no network |

## Tests

```bash
pip install -r requirements.txt -r api/requirements.txt
HARARA_FORECAST_SOURCE=mock python -m pytest -q tests/test_api_plan.py tests/test_api_parse.py
```

## Deploy

### Hugging Face Spaces (Docker SDK)

The repo root has a Space-ready `Dockerfile` (uid 1000, port 7860, installs only
`api/requirements.txt`, copies `src/` and `api/`) and a `.dockerignore` that
keeps the build context to those two folders.

1. Create the Space: on huggingface.co, New -> Space -> SDK **Docker** -> blank.
   Call it e.g. `harara-api`.
2. Add this YAML block to the **top of the Space's `README.md`** (Spaces read
   their config from there):

   ```
   ---
   title: Harara Scheduler API
   emoji: "\U0001F321"
   colorFrom: orange
   colorTo: blue
   sdk: docker
   app_port: 7860
   pinned: false
   ---
   ```

   If you push this repo's `README.md` as-is you must prepend that block; or
   keep a separate `README.md` on the Space's `main` branch.
3. Push the code:

   ```bash
   git remote add space https://huggingface.co/spaces/<your-user>/harara-api
   git push space main            # asks for your HF username + a write token
   ```

   The Space builds `./Dockerfile` automatically.
4. In the Space, Settings -> Variables and secrets:

   | name | value |
   |---|---|
   | `ALLOWED_ORIGINS` | your web URL, e.g. `https://harara.vercel.app` (comma-separate to add `http://localhost:3000`) |
   | `HARARA_FORECAST_SOURCE` | `open-meteo` |
   | `HARARA_LLM` | `k2` once the chat is wired (`mock` otherwise) |
   | `IFM_API_KEY` | secret, only if `HARARA_LLM=k2` |

5. The API is then at `https://<your-user>-harara-api.hf.space`. Point the web
   app's `API_BASE` (Vercel env) at it. Check `…/api/health`.

Notes: the free CPU tier sleeps after about 48 h idle and cold-starts in
~30 s on the next request. Space code and build logs are public; the secrets
above are not.

### Render (blueprint included)

Push to GitHub, then Render dashboard -> New -> Blueprint -> this repo. It
reads `api/render.yaml` (Docker runtime, free plan, health check
`/api/health`). After the first deploy set `ALLOWED_ORIGINS` in the dashboard
to the web app's URL.

### Fly.io (alternative)

```bash
fly launch --dockerfile api/Dockerfile --no-deploy
fly secrets set ALLOWED_ORIGINS=https://<your-web-app>
fly deploy
```

The image installs only `api/requirements.txt` (FastAPI + numpy/scipy/pandas/
pydantic/requests/thermofeel) and copies `src/` and `api/` -- no ML or
data-science dependencies.

## Data terms

Forecasts are from the Open-Meteo API, licensed CC BY 4.0 and intended for
non-commercial use. The attribution string is returned in every `/api/plan`
response and shown on the web page. See the module docstring in
`api/cache.py`.
