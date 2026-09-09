# MVP plan: scheduler as a service + single-screen web app

Ship a deployable demo of Contribution 1 (the work/rest scheduler). Backend
`api/` (FastAPI over the existing typed tool layer). Frontend `web/` (Next.js
App Router, world-class editorial design). The claim, conveyed truthfully:
**same work output, materially lower peak and tail heat load than the fixed
10:00-15:30 calendar ban, driven by the forecast.**

Nothing in `src/` is modified. `api/` and `web/` are additive. No twin, no
per-worker or medical claim, no accounts, no persistence, no GEFS numbers.

---

## 1. The equal-output baseline (design decision)

`src/agent/schedule_service.run_scheduler` already computes, over the local
working window 05:00-19:00 (`range(5,19)` -> 14 hourly slots):

- the **optimiser plan** `w_plan`, a single-scenario CVaR solve on the point
  forecast (= the deterministic optimiser; the walk-forward study in
  technical_report S8 shows this is the right choice at these leads), delivering
  exactly `required_work_hours`;
- the **calendar baseline** `w_base = policy_calendar(local_hour, ones)` -- the
  law as written: binary, work every window hour except 10:00-15:30 (hours
  10-15), so it delivers **8.0 h** over this window;
- `path_plan`, `path_base` via `retained_load_path`, and the peak / p90 of each.

`RunSchedulerResponse` keeps only the plan's per-hour fraction and the
aggregate peak/tail. The API re-derives the two per-hour retained-load paths
and the calendar per-hour fraction by calling the **same two functions the
tool layer uses internally** -- `src.scheduler.policy_calendar` and
`src.scheduler.retained_load_path` -- on the response's own hours. No physics
is added; the re-derived aggregates equal `RunSchedulerResponse.*_strain`
exactly (asserted in the golden test).

**Output parity.** Default `required_work_hours = 8`, chosen so the optimiser
delivers exactly what the calendar window yields under the ban -- a genuine
like-for-like comparison, as in S8. If the user changes it, both delivered-hour
numbers are shown in the stat strip and the page copy states the difference
plainly. The calendar policy is **never scaled** (scaling would misrepresent a
binary legal rule and, since `retained_load_path` is linear in `w`, would
understate the optimiser's advantage).

---

## 2. API (`api/`, standalone FastAPI)

Imports the installed package; translates HTTP <-> the typed tool layer only.

### 2.1 `POST /api/plan`

Request:

```jsonc
{
  "lat": 25.2854,               // required, -90..90
  "lon": 51.5310,               // required, -180..180
  "date": "2026-09-11",         // required, ISO date; must be within the forecast horizon (today .. today+15)
  "required_work_hours": 8,     // optional, default 8; > 0, <= 14
  "workload_class": "moderate", // optional, default "moderate"; light|moderate|heavy|very_heavy
  "acclimatised": true,         // optional, default true
  "tz": "Asia/Qatar"            // optional, default "Asia/Qatar"
}
```

Response `200`:

```jsonc
{
  "hours": [
    {
      "local_time": "2026-09-11T05:00:00+03:00",
      "hour": 5,                       // local hour, integer, for the x-axis
      "wbgt_c": 30.4,                  // forecast WBGT, 1 dp
      "plan_work_fraction": 1.0,       // optimiser, 0..1
      "calendar_work_fraction": 1.0,   // Decision 17/2021 policy, 0 or 1
      "retained_load_plan": 1.71,      // retained thermal load under the plan, model units, 2 dp
      "retained_load_calendar": 1.71,  // ... under the calendar ban
      "plan_state": "work"             // work | reduced | stop  (from plan_work_fraction + threshold)
    }
    // ... one per hour, 05:00 .. 18:00
  ],
  "summary": {
    "peak_plan": 6.91,
    "peak_calendar": 8.01,
    "tail_plan": 13.58,               // p90 of the retained-load path
    "tail_calendar": 16.15,
    "pct_peak_reduction": 13.7,       // (calendar - plan) / calendar * 100, 1 dp; may be <=0, shown honestly
    "pct_tail_reduction": 15.9,
    "work_hours_delivered_plan": 8.0,
    "work_hours_delivered_calendar": 8.0,
    "work_shortfall_plan": 0.0,       // > 0 only if even the full day cannot meet the target safely
    "stop_hours_plan": 0,             // count of plan hours with fraction == 0
    "stop_hours_calendar": 6,
    "wbgt_ref_c": 27.5,               // continuous-work WBGT limit for this crew (ACGIH), the load reference
    "threshold_c": 32.1,             // Decision 17/2021 stop-work line
    "solver_status": "optimal"
  },
  "meta": {
    "model": "liljegren-thermofeel / cvar-lp",
    "forecast_source": "Open-Meteo forecast API (ERA5-blend NWP)",
    "lead_time_note": "Single-point forecast, nominal lead 1-15 days by target date. Screening decision-support built on ACGIH TLV tables - not medical advice.",
    "generated_at": "2026-09-09T11:42:07Z",
    "date": "2026-09-11",
    "location": { "lat": 25.25, "lon": 51.5, "grid_note": "nearest Open-Meteo 0.25 deg cell" },
    "attribution": "Weather data by Open-Meteo.com, CC BY 4.0"
  }
}
```

`plan_state`: `stop` if `plan_work_fraction == 0`; `reduced` if
`0 < plan_work_fraction < 0.95`; `work` if `>= 0.95`.

Errors: `422` for a body that fails validation (Pydantic); `502` with
`{ "detail": "forecast upstream unavailable" }` if Open-Meteo fails;
`400` if `date` is outside the forecast horizon.

### 2.2 `POST /api/parse`  (optional NL box, built last)

Request: `{ "text": "plan tomorrow for a heavy unacclimatised crew of 12 needing 8 work-hours near Lusail" }`

Response -- parsed:

```jsonc
{
  "outcome": "parsed",
  "intent": {
    "target_local_date": "2026-09-12",
    "required_work_hours": 8.0,
    "crew": { "workload": "heavy", "acclimatised": false, "crew_size": 12 },
    "location": { "name": "lusail", "lat": 25.43, "lon": 51.49 },
    "timezone": "Asia/Qatar"
  }
}
```

Response -- clarification (never a guess):

```jsonc
{
  "outcome": "clarification",
  "missing_fields": ["workload", "acclimatised"],
  "question": "Please specify the workload class (light, moderate, heavy or very heavy); whether the crew is heat-acclimatised."
}
```

Backed by `src.agent.parse.parse_scheduling_request` with the default
deterministic `MockLLM` -- offline, no key, fail-closed by construction.

### 2.3 `GET /api/health` -> `{ "status": "ok", "version": "0.1.0" }`

### 2.4 Cross-cutting

- **Schemas**: reuse `src/agent/schemas.py` (`WorkloadClass`, `PlanIntent`,
  `ClarificationNeeded`) where they fit; add `api/schemas.py` only for the HTTP
  request/response shells above.
- **Caching**: in-process TTL cache, key `(round(lat,2), round(lon,2), date)`,
  TTL 6 h, LRU cap 256, wrapping the `get_forecast` call. Module docstring
  notes Open-Meteo's non-commercial terms and the CC-BY attribution
  requirement; attribution is also in every `/api/plan` response and on the
  page.
- **CORS**: `ALLOWED_ORIGINS` env (comma-separated), default
  `http://localhost:3000`. No secrets are used anywhere; nothing client-side.
- **Deps**: `api/requirements.txt` pins `fastapi`, `uvicorn[standard]`,
  `httpx` (test client) on top of the repo's `requirements.txt`.
- **Tests** (`tests/test_api_*.py`): (a) contract -- valid body -> 200 and the
  response validates against the response model; (b) fail-closed -- an
  ambiguous `/api/parse` text -> `outcome: "clarification"` with the expected
  missing fields; (c) golden -- `/api/plan` for a fixed date/location/crew
  against a stored `tests/data/api_plan_snapshot.json`, hours and summary
  within 1e-6, generated with `source="mock"` forecast so it is deterministic
  and offline.
- **Deploy**: `api/Dockerfile` (`python:3.11-slim`, install both requirement
  files, `uvicorn api.main:app --host 0.0.0.0 --port $PORT`); `api/render.yaml`
  (free web service, health check `/api/health`, `ALLOWED_ORIGINS` env);
  `api/README.md` documents Render + a Fly.io alternative and local
  `uvicorn api.main:app --reload`.

---

## 3. Design tokens

Reference class: Linear / Vercel dashboard / Stripe docs / FT-NYT data
journalism. Editorial restraint, confident whitespace, the data is the
ornament. No hero gradient, no glassmorphism, no illustration, no emoji. The
warmth ("premium Arabic dessert") lives in the **neutral palette bias**
(honey/date/cardamom) and one saffron accent -- never in decoration.

### 3.1 Type

- Display / headings: **Fraunces** (variable serif, optical-size + soft
  axes; warm, editorial, distinctive without shouting). `next/font` self-host.
- UI / body / all numbers: **Inter** (screen-tuned, first-class
  `tabular-nums`). `next/font`.
- Every figure the user is meant to trust: `font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1, "cv05" 1;` and set in Fraunces at the two
  hero sizes, Inter elsewhere.

Scale (major third, 1.25, rem):

| token | size | line-height | face / use |
|---|---|---|---|
| `--fs-caption` | 0.75 (12) | 1.4 | Inter 500, +0.06em, uppercase micro-labels, table meta |
| `--fs-sm` | 0.875 (14) | 1.45 | Inter, secondary text, form labels |
| `--fs-base` | 1.0 (16) | 1.55 | Inter, body |
| `--fs-lead` | 1.125 (18) | 1.5 | Inter, panel intros |
| `--fs-stat` | 1.5 (24) | 1.2 | Inter 600 tnum, the small stat values |
| `--fs-h3` | 1.5 (24) | 1.15 | Fraunces 500, subsection headings |
| `--fs-h2` | 2.0 (32) | 1.1 | Fraunces 500, section headings |
| `--fs-title` | 2.75 (44) | 1.05 | Fraunces 460, page title |
| `--fs-hero` | 3.75 (60) | 1.0 | Fraunces 460 tnum, the single headline number (% peak reduction) |

`--fs-title` / `--fs-hero` clamp down ~30% below 640px.

### 3.2 Neutrals (chosen, warm-biased toward the saffron accent)

| token | light | dark |
|---|---|---|
| `--bg` | `#FBF9F5` | `#15120E` |
| `--surface` | `#FFFFFF` | `#1D1913` |
| `--surface-sunken` | `#F3EFE7` | `#110F0B` |
| `--border` | `#E7E1D5` | `#2C261D` |
| `--border-strong` | `#D7CDBB` | `#3F372B` |
| `--text` | `#211C15` | `#F4EEE3` |
| `--text-secondary` | `#5B5348` | `#B6AC99` |
| `--text-muted` | `#8A8073` | `#847A69` |

### 3.3 Accent (single, saffron/honey)

| token | light | dark |
|---|---|---|
| `--accent` | `#C0791E` | `#E0A343` |
| `--accent-hover` | `#A9670F` | `#EBB35D` |
| `--accent-weak` | `rgba(192,121,30,0.12)` | `rgba(224,163,67,0.16)` |
| `--focus-ring` | `#C0791E` | `#E0A343` |

The **optimiser plan** line/area uses `--accent`. The **calendar-ban**
comparison uses a receding desaturated slate: `--compare` `#6E7E8C` light /
`#7C8B98` dark -- clearly secondary to the accent.

### 3.4 Operational states (work / reduced / stop)

Status colours, reserved. Every state carries **hue + glyph + label + fill
texture**, so hue is never load-bearing alone.

| state | glyph | light | dark | texture |
|---|---|---|---|---|
| work | `●` | `#3C7A57` | `#5CA67C` | solid |
| reduced | `◐` | `#B0741A` | `#D7A23E` | 33% dots |
| stop | `■` | `#AE4636` | `#D96A59` | 45 deg hatch + a solid 1px rule at its top edge |

CVD note: green/amber/red is the classic deuteranopia/protanopia failure
triad. Mitigations: (1) the redundant glyph and text label on every block;
(2) the STOP hatch + edge rule is unmistakable in greyscale; (3) luminance is
staggered (work darkest-green mid, reduced lightest, stop mid-dark) so the
three read as distinct values even fully desaturated. The exact hexes are run
through `dataviz/scripts/validate_palette.js` (`--pairs all`, both modes) and
nudged to pass the CVD Delta-E >= 8 and contrast checks before the chart is
built; failures are fixed there, not reasoned around.

### 3.5 WBGT temperature ramp (perceptual cool -> hot, hard break at 32.1 C)

Two segments with a deliberate discontinuity at the stop-work line. Blue ->
teal -> near-neutral below; hard jump to amber -> red -> deep above. Blue<->amber/red
is the CVD-safe axis; the transitional green-grey is not a distinguishing
step. Domain 24-40 C.

| WBGT C | light | dark |
|---|---|---|
| 24 | `#22506E` | `#3C6E8E` |
| 27 | `#2F7189` | `#4C93AC` |
| 30 | `#6DA0A0` | `#87B9BA` |
| 32.0 | `#AEB8A8` | `#C4CDBD` |
| — 32.1 discontinuity + 1px `--text` rule + label — | | |
| 32.1 | `#E9B24C` | `#F2C066` |
| 34 | `#DB8038` | `#E79A4F` |
| 37 | `#BC4E3C` | `#D06A54` |
| 40 | `#7E2B27` | `#A03E37` |

Stored as `RAMP: [tC, hexLight, hexDark][]`; interpolated in OKLab. The
32.1 C rule is drawn on top as a labelled horizontal line -- "32.1 C - stop-work
(Decision 17/2021)". Also run through the validator (sequential checks) in
both modes.

### 3.6 Space / radius / shadow / motion

- Space (4px base): `--s1..--s9` = 4, 8, 12, 16, 24, 32, 48, 64, 96.
- Radius: `--r-sm` 6, `--r` 10, `--r-lg` 16. Cards `--r-lg`, controls `--r`.
- Elevation: one `--shadow-card` = `0 1px 2px rgba(20,15,8,.05), 0 12px 32px -16px rgba(20,15,8,.12)`; dark leans on `--border-strong`, not shadow.
- Motion: `--dur-1` 120ms, `--dur-2` 220ms, `--dur-3` 420ms; `--ease` `cubic-bezier(.16,1,.3,1)`.
  Uses: results entrance (fade+8px rise, `--dur-3`), chart curve draw-on
  (stroke-dashoffset, 640ms), stat count-ups (900ms, first render only).
  Everything inside `@media (prefers-reduced-motion: reduce)` collapses to
  instant / no transform.

Every token defined in both `:root` (light) and `:root[data-theme="dark"]` /
`@media (prefers-color-scheme: dark) :root:not([data-theme="light"])`. Manual
toggle + system default, no-flash inline script.

---

## 4. Component tree (single screen)

```
app/layout.tsx (RSC)
  <html data-theme> + ThemeNoFlashScript + fonts
  app/page.tsx (RSC shell)
    <SiteHeader>        wordmark "Harara" (Fraunces), one-line tag, ThemeToggle, repo link
    <Planner> ('use client' — owns form state + fetch + UI state machine)
      <div class="grid">                      // sidebar 340px + main; stacks < 900px
        <aside>
          <InputPanel>
            <LocationField>                   // text + datalist presets: Doha (default), Lusail,
                                              //   Industrial Area, Al Wakrah, Mesaieed, Al Rayyan
            <DateField>                        // native date; default tomorrow; min today; max +15d
            <WorkHoursField>                   // slider + number, 1–14, default 8, tabular readout
            <WorkloadSelect>                  // Radix Select: light / moderate / heavy / very heavy
            <AcclimatisedSwitch>              // Radix Switch + helper ("newly arrived crews: off")
            <SubmitButton>                    // "Plan the day"
          </InputPanel>
          <NLBox>                             // OPTIONAL, last: textarea + "Interpret" -> /api/parse
          <AssumptionsPanel>                  // ALWAYS visible (moves below results < 900px)
        </aside>
        <section aria-live="polite">          // the UI state machine renders one of:
          <EmptyState>        | <ResultsSkeleton> | <ErrorState> | <ClarificationState> |
          <Results>
            <HeroChart>                       // hand-built D3 scales + SVG
              <figure role="group" aria-label="WBGT forecast and work plan, {date}, {place}">
                <svg tabindex=0 role="application">   // arrow keys move focusedHour
                  <RampScale>                  // WBGT colour ramp as the y-gradient behind the plot
                  <ThresholdRule>              // 32.1 C labelled line, hard colour break
                  <WbgtCurve>                  // forecast line, draw-on
                  <PlanTrack> <CalendarTrack>  // hour blocks beneath; state = glyph+label+texture
                  <HourCursor>                 // crosshair, follows hover / keyboard
                <Readout>                      // focused hour: WBGT, plan %, calendar %, both loads
                <ChartLegend>                  // plan vs calendar; work/reduced/stop glyphs
                <figcaption>                   // text alternative: colour encoding + headline delta
            <StatStrip>                        // 5 cards, count-up on first render:
                                              //   peak load (plan vs cal + %), tail p90 (+ %),
                                              //   stop-hours (plan vs cal), work-hours delivered
                                              //   (plan vs cal), WBGT reference for this crew
            <HourlyTable>                      // sortable, tabular-nums, ramp chip per row,
                                              //   state chip; the "show me the data" backstop
                                              //   — and the mobile hero (chart -> stacked view < 640)
        </section>
      </div>
    <SiteFooter>          Open-Meteo CC-BY attribution · technical report · results ledger · MIT
```

Data flow: `<Planner>` calls the Next **route handler** `app/api/plan/route.ts`
(server-side proxy to `${API_BASE}/api/plan`; adds `revalidate` caching; keeps
the browser same-origin, no keys). Same for `app/api/parse/route.ts`.

---

## 5. The four non-happy states (designed, not defaulted)

1. **Empty** (first load). Results panel shows a calm instructional card: a
   faint ghosted sketch of the chart axes (inert SVG, `--border` strokes), a
   Fraunces line "Plan a shift", body "Pick a location and day on the left,
   then plan." The AssumptionsPanel is already visible beneath. No spinner, no
   blank.

2. **Loading**. Skeleton that matches the final layout 1:1 -- a
   correct-aspect-ratio block where the chart goes, 5 stat-card skeletons, 6
   table-row skeletons. `aria-busy="true"` on the section. Shimmer sweep at
   `--dur-3`; under reduced-motion it is a static `--surface-sunken` fill. No
   spinner anywhere.

3. **Error** (network / 5xx / upstream forecast down). Inline card in the
   results panel: a broken-line glyph (SVG, not emoji), heading "Couldn't
   reach the planner", body "The forecast service didn't respond. Your inputs
   are kept." Primary "Try again" (re-fires the last request); muted footnote
   "If this persists the API may be redeploying." Never a stack trace; the
   route handler maps upstream failures to a clean `{ error, retryable }`.

4. **Clarification** (NL box only). When `/api/parse` returns
   `outcome: "clarification"`, a friendly card appears under the NL box (and
   the results panel stays in its prior state): Fraunces heading "One more
   thing", the `question` text verbatim, and each `missing_fields` entry as a
   chip that focuses + scrolls to its form control. A one-line explainer --
   "the planner won't assume a safety-relevant value" -- framed as a feature.
   Secondary action "fill the form instead". This state is a first-class
   screen, not a toast.

---

## 6. Discipline / licence / deploy pinning

- `LICENSE` = **MIT**, "Copyright (c) 2026 Muhammed Rasin". README licence
  section updated from "not yet chosen". Data terms unchanged (Open-Meteo
  CC-BY, IEM public domain, GEFS/ERA5 per their terms). Open-Meteo attribution
  visible in the app footer and every `/api/plan` response.
- `src/` untouched. Only `git add` under `api/`, `web/`, `LICENSE`,
  `README.md`, `docs/results_ledger.md`, `docs/mvp_plan.md` -- the unrelated
  uncommitted agent-model work stays out of these commits. The frontend deploy
  is pinned to the HEAD commit produced by this task, not a branch.
- No page claim the ledger/report does not support. Twin absent. "Screening /
  decision-support, not medical advice" throughout. The live single-day % is
  labelled as that day's figure; the ~14% / ~20% headline is cited to the
  walk-forward study (report S8) with a link.
- Commits, small and scoped, in order: (1) LICENSE; (2) API app + schemas +
  planning + cache + CORS + health; (3) API tests; (4) API Dockerfile +
  render.yaml + api/README; (5) web scaffold + tokens + DESIGN.md + shell +
  theme toggle; (6) InputPanel + state machine + route proxy + empty/loading/
  error; (7) HeroChart (D3+SVG, draw-on, hover, keyboard); (8) StatStrip +
  HourlyTable + AssumptionsPanel; (9) NL box + clarification state (only if the
  core screen is solid); (10) mobile hero + a11y + metadata/OG + perf; (11)
  deploy configs + README "Live demo" + ledger one-liner + written summary.

## 7. Deliverables checklist

- `api/` FastAPI service, `api/Dockerfile`, `api/render.yaml`, `api/README.md`,
  `tests/test_api_*.py` (contract, fail-closed, golden).
- `web/` Next.js app (Vercel-deployable), `web/README.md`, `web/DESIGN.md`.
- Both wired: `pnpm dev` against local `uvicorn` shows a working Doha plan.
- `LICENSE`; README "Live demo" section; `docs/results_ledger.md` one-liner
  ("the scheduler is now exposed as a service + UI - built, not a new result").
- Written summary: what the MVP does, what it omits and why, deploy URLs,
  Lighthouse scores.
