# Technical Report

Forecast-driven, physiologically explicit heat-safety analysis for outdoor
labour. Doha case study. All results are reproducible with `./run_all.sh`.

## Abstract

Outdoor workers in the Gulf are exposed to a humid-heat hazard that current
regulation addresses with a fixed midday calendar ban. This report evaluates
whether public forecast data supports a useful technical contribution to
heat-safety decision-making, and reports the results, including several
negative ones.

Modern blended numerical weather prediction already estimates Doha wet-bulb
globe temperature (WBGT) to about 0.8 C mean absolute error at 24 to 72 hours,
and a learned bias correction does not improve it. The coast-to-inland WBGT
gradient a public model resolves is about 0.5 C and errs on the safe side for
inland sites. A recurring dry-advection ("Shamal") regime, roughly 52 days per
year, does not systematically degrade the gridded product when compared against
station observations over 12 years.

Two findings are positive. First, Qatar's 10:00 to 15:30 calendar ban covers
about 25% of daylight warm-season hours, and roughly 60% of the hours that are
physiologically unsafe for heavy work by unacclimatised workers fall outside
it; over-restriction is about 6%. Second, in simulation a risk-optimal
work/rest schedule reduces mean peak thermal load by about 14% and its tail by
about 20% relative to the calendar rule, at equal output. A physics-based
particle filter estimates individual core temperature with 0.08 C MAE on
synthetic data when a skin-temperature patch is available, compared with 0.36 C
for a heart-rate-only Kalman filter; this has not been validated against
measured core temperature.

## 1. Motivation

Migrant construction and last-mile-delivery workers in Qatar and the wider Gulf
are exposed to humid heat implicated in excess cardiovascular mortality
(Pradhan et al., 2019) and, for delivery and gig workers specifically, in a
2024 Human Rights Watch report and a 2024 ILO convention on occupational safety
for platform work. Qatar Ministerial Decision 17/2021 mandates a fixed midday
outdoor-work ban (approximately 10:00 to 15:30, 1 June to 15 September) and a
stop-work clause at WBGT above 32.1 C.

## 2. Data

| Source | Coverage | Role | Homogeneity |
|---|---|---|---|
| Open-Meteo historical archive (ERA5 / ERA5-Land blend) | 2010-2026, hourly, Doha grid cell | Gridded reanalysis under test; modelling substrate | Homogeneous except 10 m wind (section 4.2) |
| OTHH (Hamad International) METAR, via Iowa Environmental Mesonet | 2014-2026, hourly | Station reference; visibility and present-weather codes | Homogeneous; airport site |
| Open-Meteo historical forecast archive | 2022-2026, leads 24/48/72 h | Archived NWP forecasts for bias-correction and skill studies | Temperature only before 2024; RH and wind from 2024 (section 6) |
| NOAA GEFS v12 reforecast (`noaa-gefs-retrospective` on S3) | 2000-2019, 5 members, May-Sep | Homogeneous frozen-model ensemble | Consistent file layout across the period; checked |
| ERA5 (Copernicus CDS) | Partial | Intended second reanalysis for cross-checks | Backfill is slow (CDS queue); not required for the current results |

Timestamps are UTC; local analysis uses Asia/Qatar (UTC+3, no DST). The cosine
of the solar zenith angle is computed from timestamp and location using the
NOAA solar-position equations (`src/solar.py`).

## 3. WBGT computation

Outdoor WBGT is computed with the Liljegren et al. (2008) energy-balance method
through ECMWF's `thermofeel` (`src/wbgt.py`). The globe and natural-wet-bulb
temperatures are solved from a steady-state balance and combined as
`WBGT = 0.7 T_nwb + 0.2 T_g + 0.1 T_a`. Kong and Huber (2022) validated this
method against station observations globally.

An earlier version of the code used an algebraic globe-temperature
approximation. Diagnostics (`scripts/diagnose_wbgt.py`) showed it adding about
0.5 C to the globe temperature under 800 W/m^2 of sun where the physical value
is about 5 C, which biased WBGT low by 1 to 2 C and made the
threshold-exceedance count over-sensitive to small errors. It was replaced.

The forecast-archive analysis temperature matches the reanalysis archive to
within 0.1 C, so the two datasets share a consistent target for the WBGT
studies.

## 4. Hazard characterisation

### 4.1 Climatology

On the 16-year record, WBGT exceeds 32.1 C on 58 to 61% of hours in the
regulated summer working window. Exceedance hours per year trend upward, from
about 500 in 2013 to 2014 to about 650 to 770 in 2021 to 2026.

### 4.2 A wind-data defect

`scripts/compare_wind_sources.py` compares Open-Meteo archive 10 m wind against
the OTHH anemometer. From 2014 to 2024 the two agree to 0.03 m/s on the June to
August mean (hourly correlation 0.81). From November 2024 the archive runs 1.5
to 2.5 m/s (about 35%) low while the measured wind stays at its climatological
norm, consistent with a change in the archive's underlying model rather than
weather. Recomputing 2025 to 2026 WBGT with measured wind lowers the mean by
about 0.3 C and reduces the threshold-exceedance-hour count by 15 to 23%,
moving those years from apparent outliers back into the historical range.

`scripts/patch_wind.py` substitutes measured METAR wind from November 2024
onward, with a `wind_source` column recording the provenance of every row. The
patched file `data/doha_weather_16yr_patched.csv` is the working dataset;
pre-2024 data is unchanged.

## 5. Forecast evaluation

Four hypotheses about where a forecasting contribution might lie were tested.
All four were rejected.

### 5.1 Bias-correcting NWP WBGT

`scripts/train_layer1_v2_nwp.py`. Target: patched-reanalysis WBGT. Predictor:
WBGT derived from the forecast issued 24, 48 or 72 hours earlier. A LightGBM
correction model was trained walk-forward.

| Lead | Raw forecast MAE | Raw forecast miss rate | Corrected (LightGBM) |
|---|---|---|---|
| 24 h | 0.80 C | 6.8% | MAE 0.92, miss 29.5% |
| 48 h | 0.93 C | 8.8% | MAE 1.03, miss 31.8% |
| 72 h | 1.00 C | 10.6% | MAE 1.08, miss 32.3% |

Miss rate is the fraction of true WBGT > 32.1 C hours the prediction placed
below 32.1, over the walk-forward test set (6153 exceedance hours in the
observation-only study, 1194 in the NWP study). The raw forecast bias is
between -0.28 C (recent) and +0.59 C (full sample), small and non-stationary.
The learned correction degrades every metric: an MAE-minimising model regresses
toward climatology and under-predicts the hot tail.

An observation-only variant (`train_layer1_v1.py`, `tune_layer1_threshold.py`)
using only past observations beats persistence by 12 to 22% on MAE but not on
miss rate; lowering the decision threshold recovers a usable safety operating
point (miss 10% at about 5% false-positive hours, miss 5% at about 7%).
Quantile training helps only marginally and only in the aggressive-safety
regime.

### 5.2 Metro-scale spatial downscaling

`scripts/spatial_representativeness.py`. Nine points across greater Doha, coast
to 55 km inland, 2015 to 2026. Summer-afternoon WBGT is lower inland (-0.4 C at
the Industrial Area, -0.8 C in deep desert): the Gulf humidity gradient
dominates the wet-bulb term over the inland temperature rise. The ACGIH
work/rest band differs from the airport reference on 23 to 34% of inland
daylight hours, but a site being unsafe while the reference indicates work is
permissible occurs on only 1 to 3% of hours. A single grid-cell forecast is, if
anything, mildly conservative for inland sites at grid scale. Block-scale
microclimate (a trench, a rooftop, sun-heated steel) is not resolved by any
public model.

### 5.3 The dry-advection regime

`scripts/regime_climatology_study.py`. Regime days are defined as those with a
daytime-mean RH anomaly below -8 points relative to a leave-year-out
day-of-year climatology from the station record: 52 days per year, 26% of
warm-season days, physically consistent with a Shamal (NW-wind hours 38% versus
10%, RH 25% versus 43%, air maximum 40 C versus 37 C). These are not dust
events (dust hours 1.9% versus 2.0%).

Reanalysis-minus-station error, daily daytime mean, regime versus normal, with
95% moving-block-bootstrap intervals:

| Variable | Regime bias [CI] | Normal bias | Difference [CI] |
|---|---|---|---|
| Air temperature | +0.50 [+0.38, +0.63] | +1.06 | -0.55 [-0.67, -0.43] |
| Wet-bulb | -0.07 [-0.24, +0.09] | -0.75 | +0.68 [+0.54, +0.82] |
| WBGT (common radiation) | +0.13 [+0.03, +0.22] | -0.20 | +0.33 [+0.24, +0.41] |

The reanalysis bias is smaller during the regime, not larger. Adding an NW-wind
gate removes the excess error entirely (difference -0.02 [-0.12, +0.07]). The
result is robust across anomaly thresholds of 6 to 12 points. Earlier
hand-picked case days that appeared to support the hypothesis were selection
bias.

### 5.4 Skill on extreme days

`scripts/extreme_event_skill.py`. Forecast MAE by observed-WBGT band is flat
(0.94 below 28 C, 1.17 in the 32 to 33 C band, 0.88 above 34 C); hours above
34 C are caught 99.7% of the time; the event peak is under-forecast by more
than 1 C in only 3% of events. The large errors that do occur concentrate on
dry-transition days and are over-predictions, driven by the forecast carrying a
near-constant RH of about 33% regardless of conditions. Adjudicated against the
station, the reanalysis is also wrong on those days (+2 C air temperature,
+1.3 m/s wind versus OTHH), so part of the apparent forecast error is target
error. The defensible residual: on dynamic-transition days no gridded product
is reliable at the +/-2 C level, and only local observation resolves it.

### 5.5 What survived

The reanalysis carries a stationary bias of about +1 C in air temperature and
about -0.75 C in wet-bulb on normal days. A fixed offset correction is a
modest, legitimate accuracy gain.

## 6. GEFS v12 reforecast integration

A multi-year forecast-reliability study on the Open-Meteo forecast archive is
not possible: it carries temperature only before 2024, with RH and wind from
2024, leaving about 1.5 complete warm seasons. The homogeneous alternative is
the NOAA GEFS v12 reforecast (2000-2019, 5 members, on the
`noaa-gefs-retrospective` S3 bucket).

### 6.1 Backfill

`scripts/fetch_gefs_reforecast.py` extracts the Doha point for May to September,
2000 to 2019, all 5 members. Each variable file is a global 0.25 degree GRIB2
with a `.idx` sidecar of per-message byte offsets; the fetcher range-requests
only the three consecutive daytime leads per forecast day (12:00, 15:00 and
18:00 local; leads 33/36/39 h for forecast day +1, +57..63 for +2, +81..87 for
+3). GRIB2 messages are stored with no gaps, so byte-adjacency alone would merge
every message between the first and last wanted lead; the coalescer merges only
consecutive 3-hourly leads, and a regression test covers this. Surface pressure
is not fetched; a fixed 1000 hPa changes WBGT by less than 0.05 C over the Doha
summer range. Output is one Parquet file per year. An init date is treated as
complete only when all members are present, so a re-run resumes cleanly.
`tests/test_gefs_alignment.py` verifies that each lead lands on the intended
local working hour and forecast day.

On the network path used for development (about 0.2 MB/s single-connection) the
full May to September run takes several hours. It runs newest-year first so the
overlap with the patched-WBGT record (2010-2019) is available soonest.

### 6.2 Radiation timing

The reforecast reports downward shortwave as a 3 to 6 hour average ending at
the lead. At the 18:00-local lead this carries the afternoon mean while the sun
is nearly set, which inflated the WBGT globe term by +4.9 C (RMSE 5.0 C) at
that lead. `compute_gefs_wbgt` clips shortwave to the clear-sky ceiling for the
actual solar geometry (`1361 cos(z) 0.82`). The 12:00 and 15:00 leads are
unchanged; the 18:00 lead falls to bias -1.4 C, RMSE 1.7 C.

### 6.3 Calibration

`src/emos.py` implements nonhomogeneous Gaussian regression: `mu = a + b xbar`,
`sigma^2 = c + d s^2`, fit by CRPS minimisation per (lead, calendar month).
Cells with too few training instances (mostly May) pool to month +/- 1 and then
to a lead-only fit, and are flagged. `tests/test_emos.py` checks the
closed-form Gaussian CRPS against Monte Carlo and verifies that fitting removes
a known bias and inflates an under-dispersed spread.

`scripts/gefs_calibration.py` runs expanding-window walk-forward by year (score
year Y with EMOS fit on years before Y, minimum 3), reporting RMSE,
spread-to-RMSE ratio, CRPS, and CRPSS of EMOS relative to the raw ensemble with
moving-block-bootstrap intervals, per forecast day and per lead. It writes
`data/gefs_emos.json`.

`src.forecast_uncertainty.GEFSEnsembleModel` accepts an EMOS model and
recalibrates its scenarios by ensemble copula coupling: each hour's marginal is
replaced by the EMOS Normal evaluated at the raw members' ranks, so the
hour-to-hour rank structure the scheduler depends on is preserved.

`scripts/gefs_reliability_study.py` builds a held-out-by-year LightGBM
classifier that predicts, from issue-time GEFS features, whether the day's
peak-WBGT forecast will have a large error (EMOS mean peak minus
patched-reanalysis peak above the training 90th percentile). It reports PR-AUC
with a block-bootstrap interval against a spread-decile rule and the base rate.

### 6.4 First results and scope

From the first backfill year (values refresh as more years land; walk-forward
EMOS needs at least 2): ensemble-mean WBGT RMSE is about 1.3 C at forecast day
+1, rising to about 1.6 C at the evening lead. For reference (non-paired, the
archives do not overlap in time) the Open-Meteo blend achieves about 0.8 C.
Ensemble spread-to-RMSE is about 0.45 to 0.51, so the raw ensemble is
under-dispersed by roughly a factor of two, as expected for a single 0.25
degree model over a narrow gulf, and as EMOS is intended to address.

The reliability study's target remains the patched-reanalysis WBGT (its own
1 C error, larger on dry-transition days, section 5), so it predicts
GEFS-versus-reanalysis divergence rather than GEFS-versus-observation. Only
about 10 overlap years exist, roughly 7 scorable, so its interval is wide. It
is the multi-year homogeneous study the substrate makes possible, with its
limits stated.

## 7. Operational gap analysis

`scripts/work_rest_analysis.py` applies the ACGIH TLV and Action Limit
screening criteria (`src/heat_stress.py`) to the 16-year patched WBGT record,
over daylight outdoor hours in April to October.

- The calendar ban covers 25% of those hours.
- Share of daylight hours requiring a full stop: light/acclimatised 20%,
  moderate/acclimatised 38%, heavy/acclimatised 49%, moderate/unacclimatised
  59%, heavy/unacclimatised 68%.
- Unsafe hours outside the ban window: heavy/acclimatised 656 per year (35% of
  hours outside the ban), heavy/unacclimatised 1085 per year (57%). Overall,
  63% of the unsafe daylight hours for heavy unacclimatised work occur outside
  the ban, in mornings, evenings and the shoulder months.
- Hours the ban closes that are in fact safe for continuous light acclimatised
  work: 6%; for anything heavier, close to 0%.

The dry-advection regime is a second limitation of the index itself: on those
52 days per year, air temperature reaches 40 C while WBGT reads lower, so
WBGT-based rules under-weight the dry-heat and dehydration hazard.

## 8. Scheduling

`src/scheduler.py`, `scripts/scheduler_study.py`. The decision variable is an
hourly work fraction in [0, 1]; a crew must deliver a fixed number of effective
work-hours over the day. Thermal load is a one-state passive-retention
integrator (`load = max(0, WBGT - 28)`, hourly retention 0.8, day strain =
peak retained load). The objective is the conditional value at risk at the 90th
percentile of day strain over forecast scenarios, solved as a linear program
(Rockafellar and Uryasev, 2000; SciPy/HiGHS). Scenario uncertainty comes from
analog residual resampling of the forecast archive by default, or from the
calibrated GEFS ensemble with `--uncertainty gefs`.

Walk-forward over 236 held-out days (June 2025 to August 2026), scored against
realised WBGT, all policies delivering the same 9 work-hours with no shortfall:

| Policy | Mean peak load | p90 | Regret vs oracle |
|---|---|---|---|
| Calendar (17/2021 style) | 8.01 | 16.15 | 2.22 |
| Reactive (coolest safe hours first) | 8.18 | 16.96 | 2.39 |
| Optimiser | 6.91 | 13.58 | 1.12 |
| Clairvoyant (oracle) | 5.80 | 12.87 | 0 |

The optimiser reduces mean peak strain by 14% relative to the calendar rule
(95% interval on the reduction [+0.80, +1.39] at 24 h) and the p90 tail by 16
to 20%, at no productivity cost, holding at 24, 48 and 72 hour leads.

The stochastic (CVaR) optimiser is 3% worse than the deterministic
point-forecast optimiser (interval [-0.25, -0.11]): the forecast is accurate
enough that hedging over-conservatises. The stochastic formulation is expected
to be worthwhile only at longer leads with a genuine ensemble, under a hard
chance constraint on an individual crossing a core-temperature limit, or with
intraday re-planning. The `--uncertainty gefs` run tests the first of these as
the GEFS backfill accumulates years.

## 9. Individual heat-strain estimation (proof of concept)

`src/thermoreg.py` (a two-node Gagge-Stolwijk-Nishi model),
`src/heat_strain_filter.py` (a particle filter with forecast-driven forward
prediction), `scripts/digital_twin_demo.py`.

The filter state is (core temperature, skin temperature, a slow per-person
metabolic scale). The process model is the two-node physiology forced by the
measured environment and an accelerometry-derived metabolic rate. Observations
are heart rate and, in the primary configuration, a skin-temperature patch.
Resampling uses post-resample kernel roughening. For anticipation, the particle
cloud is propagated under a WBGT forecast ensemble to give the probability of
core temperature exceeding 38.5 C within a horizon and the time-to-threshold
distribution.

Results on synthetic data (30 real Doha summer days, the two-node model as
ground truth, realistic sensor noise; indicative only, pending a pilot):

| Method | MAE | 95% interval coverage |
|---|---|---|
| Heart-rate-only Kalman filter (ECTemp class) | 0.36 C | - |
| Physics particle filter, HR + activity | 0.19 C | 77% |
| Physics particle filter, HR + activity + skin patch | 0.083 C | 92% |

The heart-rate-only residual bias is an identifiability effect: heart rate
responds to both workload and core temperature, and a skin-temperature patch
resolves it. For anticipation, recall is 0.91 at an alarm probability of 0.35,
and the forward probability rises as the crossing approaches (0.34 more than
90 minutes out, 0.54 at 45 to 60 minutes, 0.86 at 0 to 15 minutes), so a 0.5
alarm gives roughly 45 minutes of median warning. Absolute probability
calibration is over-confident on synthetic data and is a pre-registered pilot
endpoint.

USARIEM's ECTemp (Buller et al., 2013) estimates core temperature from heart
rate alone with a random-walk model and no forecast coupling. ISO 7933,
Fiala and JOS-3 are open-loop forward models. The combination here, assimilating
a physics model to a worker's live sensors and propagating it under the WBGT
forecast, validated against ingestible-capsule temperature in a migrant-labour
cohort, has not been published. The pilot design is in
`docs/digital_twin_protocol.md`.

## 10. Language-model layer

An optional interface sits on top of the deterministic scheduler. It does
four things and nothing else:

1. parses a free-text scheduling request into a validated tool call;
2. extracts structured constraints from a rule document, with a
   character-offset citation for every value;
3. drafts a shift briefing from a scheduler result;
4. decides when a re-planned day has changed enough that a human should
   look, and drafts the explanation.

It never computes or estimates a WBGT, a schedule, a risk or a threshold.
Those come only from `src/wbgt.py`, `src/scheduler.py` and
`src/heat_stress.py`, reached through a typed tool layer
(`src/agent/tools.py`) whose requests and responses are Pydantic models,
so an invalid or under-specified call fails before any computation runs.

**Enforcement.** The model is reached only through one interface
(`src/agent/llm.py`), with a deterministic `MockLLM` used by the tests and
the offline pipeline; the default model is deliberately unset. Parsing
fails closed: a safety-relevant field (date, work-hours, workload class,
acclimatisation, location) that is not supported by evidence in the
request text is returned as a clarification question, never a guessed
value (`src/agent/parse.py`). Rule extraction cannot write a value
without a source span that resolves to the quoted text
(`src/agent/rule_store.py`), and a record is invisible to the scheduler
until a person confirms it (`scripts/rules_review.py`). Briefings pass a
numeric guard that rejects the draft if any number in it is absent from
the scheduler response, and a rule guard that rejects any unresolved
`[rule:id#field]` reference (`src/agent/brief.py`); a failed draft is
retried once, then refused. Monitoring alerts are held to the same
numeric guard against the two plans being compared.

**Material change** (`src/agent/monitor.py`) is fixed in code, not left
to the model: a re-optimised plan is material if any working hour flips
allowed/blocked state, if peak or 90th-percentile tail retained load
moves by more than 15%, if the number of stop-work hours changes, or if a
work shortfall appears where there was none.

**Evaluation** (`eval/agent_eval.py`, four rule documents with
hand-labelled gold records under `eval/agent_eval/rules/`, 18 natural-
language requests, 10 briefing scenarios). Against the mock the layer
scores field-level precision and recall of 1.0 on all four extracted
constraint types with every citation resolving; outcome-exact-match 1.0
over the 18 requests with every ambiguous request asking back; zero
ungrounded numbers across 67 numeric tokens in generated briefings, with
the numeric guard catching every injected number; and every rule
reference resolving. These figures measure the plumbing and the guards,
not the language model: the mock is a regex stand-in and the source
documents use canonical phrasing. The harness takes `--model` for a real
adapter, which is the measurement that matters and is still to be run.

## 11. Proposed system

```
wearables (HR, accelerometry, skin patch)
    -> particle filter: self-calibrating individual core temperature
    -> forward propagation under the WBGT forecast: P(core > 38.5 C within H)
    -> CVaR work/rest scheduler with a per-crew chance constraint
    -> realised conditions and outcomes feed back to the filter and forecast model
```

Section 8 demonstrates the scheduling step on real data. Section 9 demonstrates
the estimation step on synthetic physiology. The pilot validates the estimation
step against capsule temperature.

## 12. Limitations

1. Ground truth is a single station (OTHH) in one metro area; spatial
   generality is untested.
2. The gridded product under test is the Open-Meteo blend, not ERA5; a targeted
   ERA5 cross-check is outstanding.
3. The physiology in section 9 is synthetic, from a two-node rational model
   that runs core temperature up somewhat fast in strongly uncompensable heat
   and is not calibrated to field data; the error and calibration numbers are
   indicative only.
4. The section 9 process and target models share a family, so real-world error
   will be larger; the pilot quantifies the mismatch.
5. The scheduler uses one crew, one workload class and fixed acclimatisation,
   with a passive-retention thermal load and no intraday re-planning.
6. Wet-bulb via Stull (2011) has about 0.3 C RMS error, up to about 1 C bias
   near 42 C, which partly cancels in same-method differences.
7. The GEFS reliability study is limited by about 10 overlap years and by using
   the patched reanalysis as its target (section 6.4).
8. ACGIH TLVs are conservative population screening thresholds, not
   individualised medical limits.

## 13. Further work

1. The wearable pilot (`docs/digital_twin_protocol.md`): 30 participants over
   at least 4 sessions, ingestible-capsule ground truth, a mixed-effects
   Bland-Altman primary endpoint, and sensor-ablation and acclimatisation
   secondary endpoints.
2. Completing the GEFS 2000-2019 backfill and refreshing the calibration and
   reliability numbers on the full record.
3. A targeted ERA5 cross-check of the section 5 findings.
4. Instrumented sites for block-scale microclimate, which sections 5.2 and 5.4
   show public products cannot provide.

## 14. Reproducibility

`./run_all.sh` runs the pipeline in stages (fetch, WBGT, patch, studies,
scheduler, twin, agent eval). Seeds are fixed. The environment is pinned in
`requirements.txt`. The physics, statistics and metrics have unit tests under
`tests/`. The agent layer runs against a deterministic mock by default;
`AGENT_MODEL` points it at a real adapter.

## References

- ACGIH (2017). TLVs and BEIs: Heat Stress and Strain.
- Bland, Altman (1999). Statistical Methods in Medical Research 8:135-160.
- Buller et al. (2013). Estimation of human core temperature from sequential
  heart rate observations. Physiological Measurement 34:781-798.
- Gagge, Stolwijk, Nishi (1971). ASHRAE Transactions 77(1):247-262.
- Hersbach et al. (2020). The ERA5 global reanalysis. QJRMS 146:1999-2049.
- Human Rights Watch (2024). Report on gig and delivery workers in the Gulf.
- ISO 7243 (WBGT); ISO 7933 (Predicted Heat Strain).
- Kong, Huber (2022). Earth's Future 10, e2021EF002334.
- Liljegren et al. (2008). Journal of Occupational and Environmental Hygiene
  5:645-655.
- Périard et al. (2015). Scandinavian Journal of Medicine and Science in
  Sports 25(S1):20-38.
- Pradhan et al. (2019). Cardiovascular disease mortality among migrant
  workers, Qatar. Cardiology.
- Qatar Ministerial Decision No. 17 of 2021.
- Rockafellar, Uryasev (2000). Optimization of Conditional Value-at-Risk.
  Journal of Risk 2:21-41.
- Sherwood, Huber (2010). PNAS 107:9552-9555.
- Stull (2011). Journal of Applied Meteorology and Climatology 50:2267-2269.
- Vecellio et al. (2022). Journal of Applied Physiology 132:340-345.
- Hamill et al. NOAA GEFS Reforecast v12, dataset documentation.

Citation details should be verified against the primary sources before external
use.
