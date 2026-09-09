# MVP summary — scheduler as a service + web app

## What it does

The MVP makes Contribution 1 (the forecast-driven work/rest scheduler)
tangible and deployable.

- **`api/`** — a FastAPI service over the existing typed tool layer.
  `POST /api/plan` takes a location, date, work-hours target, workload class
  and acclimatisation, runs `get_forecast → compute_wbgt → run_scheduler`,
  and returns the hourly forecast WBGT, the optimiser's per-hour work plan,
  the Decision 17/2021 calendar-ban baseline, the per-hour retained-load paths
  for both, and a summary (peak load, 90th-percentile tail, % reduction,
  delivered hours, stop hours). `POST /api/parse` wraps the fail-closed
  natural-language parser (deterministic mock model, offline). `GET /api/health`.
  In-process 6 h forecast cache; CORS via `ALLOWED_ORIGINS`. No `src/` changes.

- **`web/`** — a single-screen Next.js app. Left: a compact input panel
  (location with a Doha default and presets, date, a work-hours slider,
  workload, an acclimatisation switch) and an optional natural-language box.
  Right: the hero chart (hand-built with d3-scale + SVG) — the WBGT curve over
  a perceptual cool→hot colour ramp with a hard break at the 32.1 °C stop-work
  line, and beneath it a work-rate band that shows the optimiser plan and the
  calendar ban delivering the *same total work* in different shapes. Then a
  count-up stat strip, a sortable hourly table, and an always-visible
  assumptions panel. Full light and dark themes, keyboard-navigable chart,
  four designed non-happy states (empty, loading skeleton, error, NL
  clarification).

## The claim it conveys, and how it stays honest

Same work output, materially lower peak and tail heat load than the fixed
10:00–15:30 calendar ban. The comparison follows `technical_report` §8: both
policies deliver the same required work-hours, and neither is given a hard
32.1 °C stop — the optimiser minimises retained heat load, the calendar ban
works full-rate outside the midday window regardless of the forecast. Hours
where the optimiser still schedules work above 32.1 °C are flagged
(`over_threshold`) and called out on the page; the hard stop is applied on top
by the operator. On a representative Doha September day the single-day figure
is a 25–32% peak reduction; the page cites the §8 walk-forward average (14%
peak / 16–20% tail over 236 days) as the evidence base and labels the live
number as that day's.

The headline peak/tail numbers come straight from `RunSchedulerResponse`; the
API only re-derives per-hour display series, with `policy_calendar` and
`retained_load_path` — the same functions the tool layer uses internally.

## What it deliberately omits, and why

- **The individual digital twin.** Synthetic-only; it would imply a per-worker
  or medical capability that no pilot supports. Absent from the API and the UI.
- **Login, accounts, persistence.** Not needed to demonstrate the decision;
  they add attack surface and privacy obligations to a demo.
- **The GEFS ensemble numbers.** The live service uses the single-scenario
  CVaR solve (= the deterministic optimiser), which §8 shows is the right
  choice at these leads anyway.
- **Any claim the ledger does not support.** "Screening / decision-support,
  not medical advice" throughout; ACGIH TLV framing; a single-point forecast
  with its lead and source stated.

## Deploy

- **Web:** _(Vercel URL — set after deploy)_
- **API:** _(Render URL — set after deploy)_

`api/render.yaml` (Docker, free plan, health check) and `web/vercel.json` are
in the repo; `api/README.md` and `web/README.md` carry the steps. After the
first web deploy, set the API's `ALLOWED_ORIGINS` to the Vercel origin.

## Lighthouse

Local production build (`next start`), `/?demo=1` ready state, desktop preset:

| category | light | dark |
|---|---|---|
| Performance | 100 | 100 |
| Accessibility | 99 | 99 |
| Best practices | 100 | 100 |
| SEO | 100 | 100 |

CLS 0, TBT 0 ms, LCP ~2.3 s local. First Load JS 141 kB. Fonts self-hosted
via `next/font` (no layout shift). Deployed-URL scores to be recorded once the
web app is on Vercel; the local build is representative.

## Tests

`tests/test_api_plan.py` (contract + a golden snapshot on a hand-built day,
16.4% peak / 11.2% tail at equal 8 h) and `tests/test_api_parse.py`
(fail-closed: an ambiguous request returns a clarification, never a guess).
The full suite is 90 passing.
