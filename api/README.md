# Harara scheduler API

A thin FastAPI service over the deterministic work/rest scheduler in `src/`.
It adds no domain logic: every number comes from the tool layer in
`src/agent/` (`get_forecast` -> `compute_wbgt` -> `run_scheduler`). The
comparison it exposes is the one in `docs/technical_report.md` section 8 --
the forecast-driven optimiser against Qatar Decision 17/2021's fixed
10:00-15:30 calendar ban, at the same delivered work-hours.

## Endpoints

### `POST /api/plan`

```jsonc
// request
{ "lat": 25.2854, "lon": 51.5310, "date": "2026-09-14",
  "required_work_hours": 8, "workload_class": "moderate",
  "acclimatised": true, "tz": "Asia/Qatar" }
```

Returns `hours[]` (per local hour 05:00-18:00: `wbgt_c`,
`plan_work_fraction`, `calendar_work_fraction`, `retained_load_plan`,
`retained_load_calendar`, `plan_state` = work|reduced|stop, `over_threshold`),
a `summary` (`peak_*`, `tail_*` = p90, `pct_*_reduction`, delivered hours and
stop hours for both policies, `wbgt_ref_c`, `threshold_c`, `solver_status`),
and `meta` (model, forecast source, lead-time note, Open-Meteo CC-BY
attribution). `400` if `date` is outside the forecast horizon, `422` on an
invalid body, `502` if the forecast upstream fails.

Note: neither policy is given a hard 32.1 C stop -- the optimiser minimises
retained heat load at equal output, and hours where it still schedules work
above 32.1 C are flagged `over_threshold` for the client to surface. The
32.1 C stop-work clause is applied on top by the operator.

### `POST /api/parse` (optional NL box)

`{ "text": "..." }` -> `{ "outcome": "parsed", "intent": {...} }` or
`{ "outcome": "clarification", "missing_fields": [...], "question": "..." }`.
Backed by the fail-closed parser in `src/agent/parse.py` with the
deterministic mock model -- it never guesses a safety-relevant field.

### `GET /api/health` -> `{ "status": "ok", "version": "0.1.0" }`

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
