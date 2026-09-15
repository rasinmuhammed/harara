# Harara

Forecast-driven heat-safety scheduling for outdoor work in the Gulf.

Qatar's Ministerial Decision 17/2021 set a strong foundation for outdoor-worker
heat safety: a WBGT-based legal standard and a fixed midday rest window from
10:00 to 15:30, June to mid-September. Harara builds on that foundation with the
daily forecast. It reads the weather forecast for a specific site, works out how
hard the heat will be on the body hour by hour, and plans the working day inside
the regulation so the crew spends less time in the worst of the heat at the same
total output. Qatar is the case study throughout.

The project has two parts. The first is a study, built on 16 years of Doha
weather and checked against published physiology, of how much a forecast-driven
plan can actually improve on the fixed rule. The second is a working system:
the scheduler exposed as an API, a website, and a chat interface where you
describe a shift in plain words and get a plan back with every number traceable
to its source.

Full method, results, and the negative findings are in
[`docs/technical_report.md`](docs/technical_report.md) and
[`docs/results_ledger.md`](docs/results_ledger.md). A plain-language walkthrough
of the whole project is in
[`docs/PROJECT_EXPLAINER.md`](docs/PROJECT_EXPLAINER.md).

Three rules the project holds to:

1. **The regulation is a hard constraint.** Qatar Ministerial Decision 17/2021
   was the first GCC rule to adopt WBGT, a heat-stress index that accounts for
   humidity, as its legal standard. The scheduler encodes it as a limit it
   never plans work above. It adds protection inside the rule, it does not
   relax it.
2. **A site foreman should have the same tools an elite sports team uses for
   heat.** The physics is public, the forecasts are free, the rules are
   written down. Harara connects them and delivers a plain-language briefing
   each morning.
3. **The language model explains, it does not decide.** Every number in every
   output comes from tested physics code. The model parses requests, writes the
   explanation, and flags changes. It never computes a risk value or a
   threshold, and a guard rejects any number in its text that did not come from
   the solver.

---

## Where this fits

Forecast-driven, pre-exposure heat scheduling is not an empty category.
**Perry Weather** (Dallas; on-site black-globe hardware plus a 72-hour
forecast; $131M+ raised, a $110M round in September 2026), **Tomorrow.io**
(Boston/Tel Aviv; satellite-fed, "Weather-Adaptive Scheduling"; $543M+
raised, unicorn valuation) and **HEAT-SHIELD** (an EU-funded academic
consortium; ECMWF forecasts driving personalised WBGT/UTCI work-rest
schedules) all do some version of turning a forecast into a schedule
before anyone is exposed. Harara does not claim to be the first or only
system in that category, and any pitch of this project that says
otherwise should be read as out of date.

What none of the above does is specific to this project's actual case
study:

- **The GCC does not have one heat law, it has several incompatible
  ones**, and nobody surveyed builds for that. Qatar mandates WBGT by
  statute; Abu Dhabi's industry practice references Thermal Work Limit
  (TWL), a physically different index; Dubai runs a heat-index-style
  reading; the rest of the GCC enforces a calendar-only midday ban.
  Harara computes WBGT ([`src/wbgt.py`](src/wbgt.py)), TWL
  ([`src/twl.py`](src/twl.py), a direct port of Brake & Bates' own
  reference implementation, not a black-box approximation), and a
  heat-index variant ([`src/heat_index.py`](src/heat_index.py)) as
  three independently tested physics/statistical engines, compared
  against each other on the same real weather (technical report
  section 5.10).
- **Every comparable commercial system keeps its formulas closed.**
  Perry Weather's own materials describe its scheduling math as
  "closely guarded." Harara's physics, validation numbers, and
  mistakes are public: [`docs/results_ledger.md`](docs/results_ledger.md)
  records 39 investigated questions including the ones that came back
  negative, a headline result (a 14 percent peak-load improvement)
  that was retracted once the underlying scheduling logic was shown to
  be dishonest, two self-discovered defects in the weather archive
  this project itself depends on, and a heat-strain filter whose
  stated confidence interval was found to be wrong by external
  validation and then fixed with a published correction. That ledger
  is the actual moat: it is expensive to fake and unattractive to
  copy.
- **No on-site hardware is required.** Perry Weather and comparable
  platforms pair their forecasts with physical black-globe stations
  per site. Harara runs on public forecasts alone, at the cost of the
  hyper-local accuracy that on-site sensors give — a real trade-off,
  not a free win, and one the satellite surface-heat layer (section
  5.9) exists to partially narrow.
- **Thermal Work Limit exists almost nowhere as working software.**
  The clearest gap found in a survey of this market: TWL is published
  in academic papers and closed research scripts, not in a deployable
  product, anywhere. `src/twl.py` is a tested, cited, working
  implementation.

---

## Key results

| Question | Finding |
|---|---|
| How reliable is public weather forecasting for Doha WBGT at 24 to 72 hours out? | Raw forecast error is about 0.8 °C. A learned correction made every metric worse. The forecast is already good for this location; the value is in how you use it. |
| Does modelling the coast-to-inland difference across Doha change the safety picture? | The gradient is about 0.5 °C and leans conservative for inland sites. A single grid cell is a safe planning unit. |
| Do gridded forecasts fail during the dry Shamal wind? | No systematic failure over a 12-year comparison against station data. |
| How much additional protection can a forecast-driven plan add on top of the fixed window? | Less than an earlier version of this project claimed. A risk-optimal scheduler appeared to cut mean peak heat load by about 14 percent, but only by keeping the crew on site across a longer day. Once time on site, day fragmentation and heat dose are held no worse than the calendar rule, the daily optimiser no longer beats it on peak load; a plain earlier start is better on heat but leaves work undelivered on about half of peak-season days. This is a simulation on real past weather. |
| Can a physics filter estimate a worker's core temperature better than a heart-rate monitor alone? | On the PROSPIE dataset (40 subjects, rectal-probe reference), adding a skin-temperature channel to a two-node thermoregulation filter cut RMSE by 21 percent against a heart-rate-only baseline. The earlier synthetic figure (0.083 °C MAE) does not transfer — real bodies are 0.35 °C MAE. The filter's stated 95% interval also turned out to cover the truth only 36–42% of the time; conformal calibration (split conformal, leave-one-subject-out validated) fixes that to a 94–95% mean without touching the physics. The subjects are lab treadmill walkers, not outdoor workers, so the fix is for the interval's *width*, not for the remaining domain gap. |
| Do AI weather models miss Gulf heat extremes more than conventional forecasting? | No. On identical hours, ECMWF IFS and AIFS miss 12 to 18 percent of true stop-work exceedances; NOAA GFS misses 40 to 45 percent at every lead, and gets worse before heat waves. The practical takeaway is to use ECMWF-family forecasts for Gulf heat-safety decisions. |
| Is the rising-heat trend this project reports actually real, or an artefact of one weather archive? | The trend is real and understated, not overstated. Cross-checking the working dataset against a second reanalysis (ERA5) and the measured station (METAR) found a second, previously undocumented archive defect: Open-Meteo's Doha humidity drifted dry from 2018 onward. Correcting it with measured data turns a reported flat trend into a clearly rising one. Not yet applied to the production record; see the technical report section 5.8. |

---

## Architecture

### The deterministic core

Every safety-relevant number is computed in tested Python with no model
involved:

```
src/
  wbgt.py                Liljegren outdoor WBGT (ECMWF thermofeel library)
  solar.py               Solar zenith angle
  psychro.py             Wet-bulb temperature (Stull 2011)
  heat_stress.py         ACGIH work/rest tables; Qatar Decision 17/2021 constraints
  thermoreg.py           Two-node Gagge-Stolwijk-Nishi thermoregulation model
  heat_strain_filter.py  Particle filter for individual core-temperature estimation
  scheduler.py           CVaR work/rest linear program (SciPy/HiGHS)
  forecast_uncertainty.py  Analog resampling and GEFS lagged-ensemble models
  emos.py                Nonhomogeneous Gaussian regression for ensemble calibration
eval/
  harness.py             Walk-forward splits and leakage-safe metrics
scripts/
  fetch_*.py             Data acquisition (Open-Meteo, Hamad Airport METAR, GEFS, ERA5)
  *_study.py             The studies behind the technical report
docs/                    Technical report, results ledger, pilot protocol
tests/                   Unit tests for physics, statistics, and evaluation metrics
```

### The language layer

A thin layer sits on top of the core as an interface and an explanation
surface. The rule, enforced in code and tests, is that the model never computes
or estimates WBGT, a schedule, a risk, or a threshold. It does four things:

1. **Parse** a plain-language shift request into a validated tool call. If a
   safety-relevant field is missing (which day, how many hours, how hard the
   work, whether the crew is used to the heat, where), it asks a question
   rather than guessing.
2. **Extract** constraints from a rule document into structured records, each
   field carrying a verbatim quote and a character offset into the source.
   Nothing is used until a person confirms it.
3. **Write** the shift briefing. Every number is copied from a solver output
   and every rule reference points to a stored record. A check rejects the
   briefing if it contains a number the solver did not produce.
4. **Watch** the forecast and flag when a re-planned day differs enough from
   the last one to need a look, with a grounded explanation of what changed.

The model sits behind an interface with an offline mock, so the whole pipeline
runs with no model call. See
[`docs/llm_layer_plan.md`](docs/llm_layer_plan.md) for the tool schemas and the
evaluation design.

### Evaluation with K2-Horizon

The language layer is scored against **K2-Horizon-375B-A23B**, a
mixture-of-experts model from the Institute of Foundation Models at MBZUAI, run
twice over 18 structured test cases. The choice keeps the evaluation inside the
GCC AI ecosystem.

- Every ambiguous request drew a clarifying question. No silent guesses, on
  either run.
- No ungrounded number reached a caller, across 67 numeric tokens in clean
  briefings. The numeric guard caught every injected foreign number.
- Structured extraction was uneven and not reproducible at temperature zero on
  the hosted endpoint. The guards, not the model, are what make the layer safe.

Full record in [`docs/results_ledger.md`](docs/results_ledger.md), rows 20, 21,
and 31.

---

## Data sources

| Dataset | Coverage | Notes |
|---|---|---|
| Open-Meteo historical archive (ERA5 blend) | 2010 to 2026 hourly, Doha grid cell | Two known archive defects, both patched: 10 m wind from Nov 2024, and a summer humidity drift from 2018 onward (sized and corrected against METAR and ERA5; technical report section 5.8). Every figure in the report is computed on the corrected record. |
| Hamad International Airport (OTHH) METAR, via Iowa Environmental Mesonet | 2014 to 2026 hourly | Station reference. |
| Open-Meteo historical forecast archive | 2022 to 2026, leads 24, 48, 72 h | Archived forecasts for scoring against what happened. |
| NOAA GEFS v12 reforecast (`noaa-gefs-retrospective` on S3) | 2000 to 2019, 5 members, May to Sep | Frozen-model ensemble for probabilistic calibration. |
| ERA5 (Copernicus CDS) | 2010 to 2026 | Second reanalysis for cross-checks. |
| PROSPIE (Havenith et al., Loughborough) | 40 subjects, 154 treadmill trials, rectal-probe reference | Filter validation. CC BY-NC 4.0, so it stays in the research track only. |
| Landsat Collection 2 Level 2 and Sentinel-2 L2A, via Microsoft Planetary Computer | 2024 to 2026 summers, per-site composites | Site-scale surface-heat pattern (technical report section 5.9). Public domain (USGS) and Copernicus-licensed respectively. Advisory only, never feeds WBGT or the scheduler. |

Everything under `data/` is regenerated by the pipeline and is git-ignored. `api/data/` (including `api/data/site_heat/`) is precomputed, static, and committed, the same pattern as the replay weeks.

---

## Live demo

The scheduler runs three ways: a FastAPI service in `api/`, a chat product app,
and a public site in `web/`.

- Site: _(Vercel URL to be added)_
- API: _(Railway URL to be added)_

Run it locally:

```bash
# API, from the repo root
pip install -r api/requirements.txt
HARARA_FORECAST_SOURCE=mock uvicorn api.main:app --port 8000
# Drop HARARA_FORECAST_SOURCE for live Open-Meteo forecasts.
# Set HARARA_LLM for a real conversational assistant; the default "mock"
# runs fully offline with a deterministic summary.

# Web, in a separate shell
cd web && pnpm install
echo "API_BASE=http://127.0.0.1:8000" > .env.local
pnpm dev       # http://localhost:3000, chat app at /app
```

Deploy steps are in `api/README.md` and `web/README.md`. `web/DESIGN.md`
documents the design system.

---

## Reproducing

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # LightGBM needs libomp: brew install libomp on macOS
./run_all.sh                           # fetch, studies, scheduler, twin
pytest -q
```

`./run_all.sh --no-fetch` reuses data already in `data/`. The GEFS 2000 to 2019
backfill is a multi-hour job and is off by default. Set `GEFS_BACKFILL=1` or run
`scripts/fetch_gefs_reforecast.py` directly. It is resumable.

---

## Status

The hazard analysis, the scheduler, the AI weather model study, the GEFS
ensemble calibration and reliability study, the ERA5 cross-check, and the
language layer are done. The individual heat-strain filter has been checked
against external physiology data (PROSPIE) and needs a field pilot with
ingestible-capsule ground truth in the target population before it means
anything operationally; the protocol is in
[`docs/digital_twin_protocol.md`](docs/digital_twin_protocol.md).

---

## Licence

Code is under the MIT Licence (see `LICENSE`). Input data follows the terms of
each source: Open-Meteo CC BY 4.0, IEM METAR public domain, GEFS reforecast and
ERA5 under their own terms, PROSPIE CC BY-NC 4.0.
