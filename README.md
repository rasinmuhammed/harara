# Harara

Forecast-driven, physiologically explicit heat-safety analysis for outdoor
labour in the Gulf. Doha case study.

The repository contains the data pipeline, the analysis code, and the write-up
for two lines of work:

1. Characterising the humid-heat hazard for Doha from public data, and
   quantifying how well the current regulatory approach (a fixed midday
   calendar ban) matches the physiological risk.
2. Two candidate contributions: a risk-optimal work/rest scheduler evaluated
   against that calendar rule, and a proof-of-concept individual heat-strain
   estimator built on a physical thermoregulation model.

The methodology notes and the results, including the negative ones, are in
[`docs/technical_report.md`](docs/technical_report.md). A concise index of every
question that was tested, and the outcome, is in
[`docs/results_ledger.md`](docs/results_ledger.md). The pilot design for the
heat-strain estimator is in [`docs/digital_twin_protocol.md`](docs/digital_twin_protocol.md).

## Summary of findings

| Question | Outcome |
|---|---|
| Can blended NWP be usefully bias-corrected for Doha WBGT at 24-72 h? | No. Raw forecast MAE is about 0.8 C; a learned correction degrades every metric. |
| Does metro-scale spatial downscaling change the safety picture? | No. The resolved coast-inland WBGT gradient is about 0.5 C and errs on the safe side for inland sites. |
| Do gridded products fail systematically during dry-advection ("Shamal") regimes? | No, over a 12-year comparison against station observations. |
| Does the calendar ban match the physiological hazard? | No. It covers about 25% of daylight warm-season hours; roughly 60% of the hours that are unsafe for heavy work by unacclimatised workers fall outside it. Over-restriction is about 6%. |
| Does risk-optimal scheduling beat the calendar rule at equal output? | Yes in simulation: mean peak thermal load down about 14%, the tail down about 20%, no work unmet, at all leads. |
| Can a physics filter estimate individual core temperature better than heart rate alone? | Yes on synthetic data: MAE 0.08 C with a skin-temperature patch, versus 0.36 C for a heart-rate-only Kalman filter. Not yet validated against measured core temperature. |

## Product direction

The deterministic core in this repository (forecast to WBGT to physiological
work/rest allocation to a risk-optimal schedule) is the engine. The intended
product wraps it with a thin agentic layer that acts as an interface and an
explanation surface, not as a source of numbers.

The design rule, enforced in code and in tests, is that the language model
never computes or estimates WBGT, schedules, risk, or thresholds. All
computation stays in deterministic Python. The model does four things:

1. Parses unstructured requests into validated tool calls, failing closed on
   any missing safety-relevant parameter rather than guessing.
2. Extracts rules from documents (a labour ministry decision, an ACGIH table, a
   platform duty-of-care policy, a site SOP) into structured constraints, each
   field carrying a verbatim source quote and character offset. Nothing is used
   by the scheduler until a human confirms it.
3. Generates shift briefings whose every number is copied from a tool output
   and every rule reference cites a stored record; a post-generation check
   rejects any numeric token not present in the tool outputs.
4. Decides when a re-planned schedule has changed enough to warrant a human
   alert, and writes the explanation.

The model sits behind a model-agnostic interface with a mock implementation, so
the pipeline runs offline and the choice of model is deferred. See
`docs/llm_layer_plan.md` for the tool schemas, the rule-store format, and the
evaluation design.

## Layout

```
src/
  wbgt.py                Liljegren outdoor WBGT (ECMWF thermofeel)
  solar.py               cosine of the solar zenith angle
  psychro.py             wet-bulb temperature (Stull 2011)
  heat_stress.py         ACGIH TLV work/rest allocation; Qatar Decision 17/2021
  thermoreg.py           two-node Gagge-Stolwijk-Nishi thermoregulation model
  heat_strain_filter.py  particle filter for individual core temperature
  scheduler.py           CVaR work/rest scheduling (linear program)
  forecast_uncertainty.py  analog resampling and GEFS lagged-ensemble models
  emos.py                nonhomogeneous Gaussian regression for ensemble calibration
eval/
  harness.py             walk-forward splits and leakage-safe metrics
scripts/
  fetch_*.py             data acquisition (Open-Meteo archive and forecast,
                         OTHH METAR, GEFS v12 reforecast, ERA5)
  patch_wind.py          substitute measured wind for the 2024-11+ archive defect
  run_first_result.py    WBGT history and baseline comparison
  *_study.py, *_analysis.py   the studies behind the technical report
docs/                    technical report, results ledger, pilot protocol
tests/                   unit tests for the physics, statistics and metrics
```

## Data sources

| Dataset | Coverage | Notes |
|---|---|---|
| Open-Meteo historical archive (ERA5 blend) | 2010-2026 hourly, Doha grid cell | Homogeneous except 10 m wind from 2024-11, which is patched from METAR. |
| OTHH (Hamad International) METAR, via Iowa Environmental Mesonet | 2014-2026 hourly | Station reference. Includes visibility and present-weather codes. |
| Open-Meteo historical forecast archive | 2022-2026, leads 24/48/72 h | Temperature only before 2024. |
| NOAA GEFS v12 reforecast (`noaa-gefs-retrospective` on S3) | 2000-2019, 5 members, May-Sep | Frozen-model ensemble. Point series extracted by GRIB `.idx` byte range. |
| ERA5 (Copernicus CDS) | Optional background backfill | Second reanalysis for cross-checks; not required for the current results. |

Everything under `data/` is regenerated by the pipeline and is git-ignored.

## Reproducing

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # LightGBM needs libomp: `brew install libomp` on macOS
./run_all.sh                           # fetch, studies, scheduler, twin
pytest -q
```

`./run_all.sh --no-fetch` reuses whatever is already in `data/`. The GEFS
2000-2019 backfill is a multi-hour job and is off by default; set
`GEFS_BACKFILL=1` to include it, or run `scripts/fetch_gefs_reforecast.py`
directly. It is resumable and the GEFS analysis stages run on whatever years
are present.

## Status

The hazard analysis and both proof-of-concept contributions are complete. The
individual heat-strain estimator requires a wearable pilot with
ingestible-capsule ground truth before its numbers mean anything; see the
protocol. The GEFS integration (backfill, EMOS calibration, and a forecast
reliability classifier) is implemented; the numeric results populate as the
backfill accumulates years.

## Licence

Code is released under the MIT Licence (see `LICENSE`). Input data is subject
to the terms of each source: Open-Meteo CC BY 4.0, IEM METAR public domain,
GEFS reforecast and ERA5 under their respective terms.
