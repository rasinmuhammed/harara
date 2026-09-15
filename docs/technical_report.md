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

One gap-analysis finding is positive: Qatar's 10:00 to 15:30 calendar ban
covers about 25% of daylight warm-season hours, and roughly 60% of the hours
that are physiologically unsafe for heavy work by unacclimatised workers fall
outside it, while over-restriction is about 6%. An earlier claim that a
risk-optimal daily schedule reduces mean peak thermal load by about 14% at
equal output did not survive scrutiny: that reduction was obtained by
spreading the same work across a longer on-site day, which for a bussed-in
accommodation worker is a cost. Once the crew's time on site, day
fragmentation and cumulative heat dose are held no worse than the calendar
rule, the daily optimiser no longer beats it on peak load; the rule's fixed
midday break is load-bearing on the hottest days (section 8). A physics-based
particle filter estimates individual core temperature with 0.08 C MAE on
synthetic data when a skin-temperature patch is available, compared with 0.36 C
for a heart-rate-only Kalman filter; this has not been validated against
measured core temperature. A cross-check against ERA5, a second reanalysis
independent of the working dataset, strongly corroborates its WBGT climatology
overall (r = 0.99, 97% agreement on stop-work hours) and independently
confirms the wind-archive defect, but disagrees on the size of the reported
upward exceedance-hour trend (section 5.7). Triangulating against the METAR
station resolves this in ERA5's direction: Open-Meteo's Doha archive carries
a second, previously undocumented defect, a nine-year drift toward drier
humidity from 2018 onward, and correcting it with measured data turns the
reported near-flat trend into a clearly rising one -- the true rate of
increase in outdoor-heat exposure is understated, not overstated, by the
working dataset (section 5.8).

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
| Open-Meteo historical archive (ERA5 / ERA5-Land blend) | 2010-2026, hourly, Doha grid cell | Gridded reanalysis under test; modelling substrate | Two known defects: 10 m wind from Nov 2024 (section 4.2, patched) and summer humidity drift from 2018 (section 5.8, sized, not yet patched) |
| OTHH (Hamad International) METAR, via Iowa Environmental Mesonet | 2014-2026, hourly | Station reference; visibility and present-weather codes | Homogeneous; airport site |
| Open-Meteo historical forecast archive | 2022-2026, leads 24/48/72 h | Archived NWP forecasts for bias-correction and skill studies | Temperature only before 2024; RH and wind from 2024 (section 6) |
| NOAA GEFS v12 reforecast (`noaa-gefs-retrospective` on S3) | 2000-2019, 5 members, May-Sep | Homogeneous frozen-model ensemble | Consistent file layout across the period; checked |
| ERA5 (Copernicus CDS) | 2010-2026, hourly, same Doha point | Independent second reanalysis; cross-check only (section 5.7) | Complete; not used as modelling substrate for any other section |

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

On the 16-year record, WBGT exceeds 32.1 C on about 61% of hours in the
regulated summer working window (June to September, 10:00 to 15:00 local).
Exceedance hours per year (June to September, 06:00 to 18:00 local) trend
upward, from about 519 in 2013 to 2014 to about 761 in 2021 to 2025, a fitted
slope of +9.0 hours/year.

These are the corrected figures (section 5.8): Open-Meteo's own archive
carried a persistent summer humidity drift, confirmed against ERA5 and the
METAR station, that understated this trend on the previously reported record
(then about 58% of hours, and a rise from about 500 to 650-770). The shape of
the finding is unchanged - the ban leaves a gap and the hazard is worsening -
but the corrected numbers, not the original ones, are the ones to cite.

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
| 24 h | 1.01 C | 11.7% | MAE 0.95, miss 26.0% |
| 48 h | 1.10 C | 13.5% | MAE 1.03, miss 27.3% |
| 72 h | 1.14 C | 14.2% | MAE 1.06, miss 28.1% |

Miss rate is the fraction of true WBGT > 32.1 C hours the prediction placed
below 32.1, over the walk-forward test set (6153 exceedance hours in the
observation-only study, 1252 in the NWP study). The raw forecast bias is
small and near zero at every lead (-0.05 to -0.02 C on this test set).
Re-run on the humidity-corrected truth series, the finding changes in kind,
not just size: the correction now wins on headline MAE and RMSE at every
lead (24 h: MAE 1.01 -> 0.95 C, RMSE 1.32 -> 1.24 C) where it previously lost
on both. It still substantially worsens the miss rate that actually matters
for a stop-work decision (11.7% -> 26.0% at 24 h), because it buys a much
lower false-positive rate (3.0% -> 0.8%) by regressing toward climatology and
under-predicting the hot tail. The mechanism and the verdict are unchanged -
an MAE-minimising model is the wrong thing to optimise for a safety
threshold - but "degrades every metric" is no longer the accurate summary;
it degrades the one metric that is actually safety-relevant while improving
the ones that are not.

An observation-only variant (`train_layer1_v1.py`, `tune_layer1_threshold.py`)
using only past observations beats persistence by 13 to 21% on MAE but not on
miss rate; lowering the decision threshold recovers a usable safety operating
point (miss 10% at about 5% false-positive hours, miss 5% at about 8%).
Quantile training helps only marginally and only in the aggressive-safety
regime.

### 5.2 Metro-scale spatial downscaling

`scripts/spatial_representativeness.py`. Nine points across greater Doha, coast
to 55 km inland, 2015 to 2026. Summer-afternoon WBGT is lower inland (-0.4 C at
the Industrial Area, -0.6 C in deep desert, re-verified on the humidity-
corrected record): the Gulf humidity gradient dominates the wet-bulb term over
the inland temperature rise. The ACGIH work/rest band differs from the airport
reference on 23 to 34% of inland daylight hours, but a site being unsafe while
the reference indicates work is permissible occurs on only 1 to 3% of hours. A
single grid-cell forecast is, if anything, mildly conservative for inland
sites at grid scale. Block-scale microclimate (a trench, a rooftop, sun-heated
steel) is not resolved by any public model.

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

Re-verification note: this section's "gridded product under test" has to stay
independent of the OTHH station, which is also the section's ground truth.
The humidity correction (section 5.8) breaks that independence for the
production WBGT file - it substitutes METAR temperature and dewpoint into
71.7% of its hours - so this script now reads temperature and relative
humidity from the raw, unpatched Open-Meteo archive instead (wind, pressure
and radiation, none of them touched by the humidity patch, still come from
the current pipeline file). Re-run this way, every number above is unchanged
to two decimal places from the pre-correction report, confirming this
section's conclusion never depended on the defect the correction fixed.

### 5.4 Skill on extreme days

`scripts/extreme_event_skill.py`, 24 h lead, re-verified on the humidity-
corrected truth series. Forecast MAE by observed-WBGT band is close to flat
(0.95 below 28 C, 1.11 in the 32 to 33 C band, 0.90 above 34 C); hours above
34 C are caught 99.1% of the time (was 99.7%); the event peak is under-
forecast by more than 1 C in 6% of events (was 3%). The large errors that do
occur concentrate on dry-transition days and are over-predictions, driven by
the forecast carrying a near-constant RH of about 33% regardless of
conditions. The comparison against the station on those specific days (+2 C
air temperature, +1.3 m/s wind versus OTHH) predates this correction and has
not itself been re-run; it should be treated as illustrative of the
mechanism rather than a re-verified number. The defensible residual: on
dynamic-transition days no gridded product is reliable at the +/-2 C level,
and only local observation resolves it.

### 5.5 What survived

The reanalysis carries a stationary bias of about +1 C in air temperature and
about -0.75 C in wet-bulb on normal days. A fixed offset correction is a
modest, legitimate accuracy gain.

### 5.6 AI weather models for Gulf humid heat

**H-E: AI weather prediction models degrade humid-heat stop-work decisions
relative to conventional NWP.** Kong et al. (2025, arXiv 2504.21195) report
that GraphCast, Pangu-Weather and NOAA GEFS carry a consistent regional cold
bias in 2 m temperature in the days before CONUS heat-wave onset. A cold bias
before extreme heat is the dangerous direction. Whether this holds for humid
heat (WBGT) in the Gulf, and whether it produces missed stop-work decisions at
the 32.1 C threshold, had not been tested. `scripts/aiwp_humid_heat_study.py`.

**Data.** Archived past model runs for the Doha grid point from Open-Meteo's
Previous Runs API (`scripts/fetch_previous_runs.py`), at nominal leads of 1 to
7 days: ECMWF IFS-HRES (`ecmwf_ifs025`), ECMWF AIFS Single
(`ecmwf_aifs025_single`), NOAA GraphCast (`gfs_graphcast025`) and NOAA GFS
(`gfs_seamless`). GraphCast on this feed serves only 2 m temperature and cloud,
so it cannot yield a WBGT forecast; the study runs a WBGT track (IFS, AIFS,
GFS) and a 2 m-temperature track (all four). WBGT is computed from each
model's fields through the same Liljegren pipeline as the truth
(`src/forecast_wbgt.py`). Scoring is walk-forward against the METAR-patched,
humidity-corrected observational truth (section 5.8), warm-season (May to
September) daylight hours (local 07:00 to 18:00), with a one-day moving-block
bootstrap for 95% intervals. AIFS starts only in February 2025 on this feed
(about 1.5 warm seasons), so the headline tables score every model on the
common window per lead; a full-window appendix covers IFS and GFS. Heat-wave
onset is the first day of a run of at least two consecutive days whose
daily-maximum WBGT is at or above the 90th percentile of strictly prior
years, the preceding day below it.

**WBGT track (common window, warm-season daylight, leads 1, 5, 7).**

| Model | Bias (C) | Miss rate at 32.1 C | FPR |
|---|---|---|---|
| IFS | +0.70 to +0.90 | 0.12 (L1) to 0.18 (L7) | 0.19 to 0.21 |
| AIFS | +0.64 to +0.67 | 0.13 (L1) to 0.16 (L7) | 0.14 to 0.15 |
| GFS | -0.27 to -0.75 | **0.40 to 0.45, every lead** | 0.03 to 0.09 |

Bias and FPR are essentially unchanged from the pre-correction run; miss
rates moved up 3 to 6 points for IFS and AIFS (the corrected truth has more
genuine exceedance hours to miss) while GFS's stayed flat, still clearly the
worst of the three. The AI model, AIFS, is statistically indistinguishable
from IFS on the miss rate, and more clearly so than before: the paired
AIFS - IFS difference is +0.01 to +0.03 across leads 1 to 7 and its interval
is clear of zero only at lead 2 (+0.03 [+0.00,+0.05]); every other lead
includes zero. GFS misses about a quarter to a third more true exceedance
hours than either, at every lead, with the paired interval far from zero
(Figure 6). Stratified by observed band at lead 5, GFS bias runs from +0.92 C
below 28 C to **-2.21 C above 34 C** -- worst exactly in the stop-work band --
while IFS stays between +0.37 and +1.06 C across all bands (Figure 10).

**The cold-bias direction, on WBGT.** In the five days before a heat-wave
onset, GFS WBGT bias is -1.02 to -1.23 C against an all-days bias of -0.27 to
-0.75 C: its cold bias worsens ahead of heat waves, the published direction,
and by slightly more than the pre-correction run showed. IFS and AIFS show no
such excursion; both stay warm-biased, AIFS if anything more so ahead of
onset (+0.93 to +1.17 C) than on all days (+0.64 to +0.67 C) (Figure 8).
Leads are capped at 7 days here, so the 8 to 10 day part of the published
window is not probed; this is bias at leads 1 to 7 for forecasts valid in the
days before onset, not a full replication.

**2 m temperature track (the direct replication).** This track moved the
most on re-verification, because `patch_humidity.py` corrects the truth
series' own 2 m temperature, not just its humidity, for 71.7% of hours - and
the pre-correction Open-Meteo archive ran warm as well as dry in exactly this
period (section 5.8). Every model's apparent bias against that truth shifts
in the same direction as a result. AIFS's cold bias against the corrected
truth roughly halves (-0.24 to -0.55 C, was -1.4 to -1.7 C) but the practical
finding does not change: it still misses 91 to 100% of hours above the
prior-years 95th percentile (about 42 C), across leads 1 to 7. GFS's cold
bias shrinks the same way (-0.90 to +0.01 C, was -1.2 to -2.0 C; miss rate 64
to 86%). IFS and GraphCast, which were never cold-biased, move the other
way and now run substantially warmer against the corrected truth: IFS +1.90
to +2.32 C (was +0.8 to +1.1 C), GraphCast **+1.53 to +2.25 C** (was +0.4 to
+1.0 C) - still the opposite sign from the published finding, and more
clearly so, though GraphCast's coverage is still sparse and gappy and the
common window falls to about 500 to 1,400 hours depending on lead (Figure 9).

**Why the WBGT and temperature results diverge for AIFS.** Component bias on
the common window (lead 1, core daylight) also moved with the truth-series
correction: AIFS air temperature -0.14 C (was -1.5 C), relative humidity
+0.3% (was +6.2%), wind -0.55 m/s (unchanged; wind is not touched by the
humidity patch). The previous story - a large cold-temperature bias mostly
offset by a large moist-humidity bias - measured the old truth series' own
warm-and-dry drift as much as it measured AIFS's forecast error; both of
AIFS's component biases against the corrected truth are now small. AIFS's
WBGT bias itself barely moved (+0.64 to +0.67 C, was +0.66 to +0.69 C), so
what is left to explain it is the smaller residual temperature and humidity
biases together with AIFS's own low wind bias, which inflates WBGT. GFS's
component bias shrank the same way (temperature -0.48 C, was -1.7 C;
humidity -4.2%, was +1.6%) and its WBGT stays cold, as in the table above. A
cold air-temperature bias is still not the same thing as a cold humid-heat
bias; the two still have to be evaluated separately, and both are now more
sensitive to the truth series than the original write-up assumed.

**GraphCast bound (synthetic).** Splicing GraphCast 2 m temperature into IFS
humidity, wind and radiation (not any real system's output) gives a WBGT bias
of +0.2 to +0.9 C and a miss rate of 0.22 to 0.36 -- safe-side, between IFS and
GFS. GraphCast's temperature error is not a stop-work hazard in the cold
direction.

**Caveats.** AIFS has about 1.5 warm seasons; every AIFS number is flagged,
though the miss-rate intervals ([0.10, 0.21] across leads) are tight enough to
support "about IFS, well below GFS". IFS forecast 10 m wind runs -1.5 m/s
against the METAR-patched truth, which inflates IFS forecast WBGT (safe-side);
GFS forecast wind is close to truth (+0.16 m/s), so the GFS cold WBGT bias is
not a wind artefact. Shoulder months (April, October) carry only about 30
daylight exceedance hours across the whole forecast era and are not scored. The
truth is one station's patched series; the repo's 2000-2019 GEFS reforecast
(Section 6) is the decade-scale complement for the GFS family, and its raw
ensemble-mean WBGT RMSE of 1.68 C at day +1 (1.29 C EMOS-calibrated) is in the
same range as the 1.2 to 1.5 C deterministic-GFS MAE here, both now level
with, or slightly ahead of in EMOS's case, the 1.01 to 1.14 C Open-Meteo
blend (section 5.1).

**Verdict: H-E rejected.** The AI model does not degrade humid-heat stop-work
decisions relative to conventional NWP; AIFS matches the best conventional
model (IFS) at the 32.1 C threshold and clearly beats the other (GFS). The
operational consequence runs the other way: NOAA GFS WBGT is unreliable at the
stop-work threshold -- it misses about four in ten true exceedance hours at all
leads and gets colder before heat waves -- and ECMWF IFS or AIFS should be
preferred for Gulf humid-heat forecasting. The published cold-bias-before-heat-
wave result is real in air temperature but does not by itself indicate a humid-
heat forecasting hazard; humidity compensation has to be accounted for, and the
metric that matters is WBGT at the decision threshold.

### 5.7 A targeted ERA5 cross-check

The working dataset behind sections 4 to 5.6 is Open-Meteo's archive
(patched with METAR wind from November 2024, section 4.2). It is a blend,
not a documented single product, so section 12's limitation 2 asked for an
independent check: ERA5, a reanalysis from a different provider (Copernicus)
running a different, frozen model (IFS Cy41r2), fetched hourly for the same
Doha point (25.27 N, 51.61 E) over the same 2010-2026 span
(`scripts/fetch_era5.py`, `scripts/era5_to_csv.py`, `scripts/era5_cross_check.py`).
ERA5 is not ground truth any more than Open-Meteo is; where the two agree is
real signal, where they disagree is uncertainty this report should own.
WBGT is computed from ERA5 with the identical Liljegren pipeline and Doha
grid point as the working dataset, so any difference is in the inputs, not
the physics -- confirmed by first recomputing WBGT from the patched
Open-Meteo file with this script's own code and checking it reproduces the
stored `data/doha_wbgt_16yr.csv` exactly (max difference 0.0 C over 146,064
hours).

**The November 2024 wind defect, checked against a third source.** Section
4.2 found Open-Meteo's archive wind running low from November 2024, confirmed
against METAR. ERA5 is independent of both. Summer (June-August) mean wind,
2025-2026 against 2014-2024: Open-Meteo -1.56 m/s (-35%), METAR +0.02 m/s
(+0.5%), **ERA5 -0.00 m/s (-0.0%)**. ERA5 corroborates METAR and contradicts
Open-Meteo: the defect is confirmed a second, fully independent way. It is in
Open-Meteo's archive, not the weather.

**Agreement on WBGT, full 16-year hourly overlap (146,064 hours).** ERA5 runs
+0.38 C warm on WBGT relative to the working dataset (95% CI [+0.33, +0.43]),
RMSE 0.92 C, r = 0.99. On the 32.1 C stop-work line the two agree on 97.3% of
hours (9,897 both over, 132,280 both under); of the hours ERA5 flags as over
the line, the working dataset also flags 77.3%; of the hours the working
dataset flags, ERA5 also flags 90.9%. ERA5 runs mildly more conservative:
2,899 hours it calls over the line the working dataset does not, against 988
the other way.

**The rising exceedance-hour trend (section 4.1) does not fully replicate.**
Using a plain warm-season daytime definition (June-September, 06:00-18:00
local, WBGT > 32.1 C, for consistency with `api/planning.py`'s
`heat_trend`), ERA5 shows a clear rise across the full record: 466 hours/year
(2013-2014 mean) to 793 (2021-2025 mean), a fitted slope of +15.3 hours/year.
The working dataset over the same years and definition is essentially flat
(-2.3 hours/year). The two products agree that recent years are hot and
agree hour-by-hour 97% of the time, but disagree on whether the multi-year
trend is a real, steady rise or closer to noise around a high plateau.
Tracing the divergence to its source: the years with the largest gap are
2018, 2019 and 2025, where ERA5 runs 6.3 to 6.9 percentage points more
humid than the working dataset in warm-season daytime hours, with air
temperature 0.5 to 1.4 C *cooler* -- a humidity-driven gap, the same failure
mode section 5.6 found for AIFS temperature-vs-WBGT, not a temperature one.
This gap is resolved, not just flagged, in section 5.8: it is a second,
previously undocumented Open-Meteo archive defect, and the true trend is
larger than the working dataset reports, not smaller.

**Verdict.** The wind-defect finding (section 4.2) is strengthened: two
independent sources now confirm it. The overall WBGT climatology is
strongly corroborated (r = 0.99, agreement on 97% of stop-work hours). The
section 4.1 upward trend is real and, per section 5.8, understated by the
working dataset.

### 5.8 A second archive defect: a persistent humidity drift, and its size

Section 5.7 traced the ERA5-versus-working-dataset trend disagreement to a
humidity gap concentrated in specific years, without saying which product was
closer to reality -- ERA5 is an independent reanalysis, not ground truth.
METAR gives a third, measured answer. `scripts/humidity_defect_study.py`
compares dewpoint (moisture content directly, rather than relative humidity,
which also moves with temperature and can hide which one is actually wrong)
against the OTHH station for all three products, June to August, 2014 to
2026.

**Open-Meteo's summer dewpoint bias against METAR flips sign and stays
flipped.** Mean bias (product minus station): +1.4 C in 2014-2016 (Open-Meteo
too moist), crossing to -0.3 C in 2017, then -0.6 to -1.8 C in every year
from 2018 to 2026 (Open-Meteo too dry) -- nine consecutive years on the dry
side after three years on the wet side, not noise in a couple of unlucky
years. ERA5's bias against METAR stays on one side throughout, +0.7 to +2.0 C
(ERA5 itself runs consistently a little moist against the station, but
*consistently*, with no sign flip and no trend). This is a second,
previously undocumented Open-Meteo archive defect, structurally different
from the November 2024 wind defect (section 4.2): a gradual, seasonal drift
rather than a sharp step, spanning about nine years rather than two, and in
relative humidity rather than wind.

**Sizing the effect.** A METAR-humidity-corrected version of the working
dataset was built for this check only (temperature and dewpoint replaced by
measured METAR values wherever available -- 104,632 of 146,064 hours, 72% --
recombined thermodynamically consistently, then WBGT recomputed through the
identical Liljegren pipeline, for this sizing check only). The section 4.1
trend on this corrected series sat between the pre-correction working
dataset and ERA5, closer to ERA5:

| Series | 2013-2014 mean h/yr | 2021-2025 mean h/yr | Slope h/yr | Regulated-window exceedance |
|---|---|---|---|---|
| Open-Meteo (pre-correction) | 521 | 647 | -2.3 | 57.7% |
| METAR-humidity-corrected (sizing check) | 508 | 739 | +7.4 | 60.2% |
| ERA5 | 466 | 793 | +15.3 | 65.4% |

Correcting only the humidity input, with measured data, turned a flat-to-
declining trend into a clearly rising one, about half of ERA5's estimate.
Both independent corrections (ERA5, METAR) moved the same direction, away
from the pre-correction series.

**Applied.** `scripts/patch_humidity.py` extends `patch_wind.py`'s method to
temperature and dewpoint (patched together, from METAR wherever available,
71.7% of the 16-year record; no date cutover, the same "prefer the
measurement" principle as the wind patch, since the drift is gradual and
seasonal rather than a single step). `data/doha_wbgt_16yr.csv` was rebuilt
from the corrected `data/doha_weather_16yr_patched.csv`, and every figure in
this report from here on is computed on the corrected record. The applied
correction is close to the sizing estimate above and slightly stronger: 2,013
to 2,014 mean 519 h/yr, 2021 to 2025 mean 761 h/yr, slope **+9.0 hours/year**
(59% of ERA5's independent estimate), regulated-window exceedance 61.4%.
Re-running the ERA5 cross-check (section 5.7) against the corrected record
confirms the fix: the WBGT bias against ERA5 falls from +0.38 C to +0.22 C
and the trend gap that motivated this section closes by more than half
(-2.3 to +9.0 hours/year, against ERA5's unchanged +15.3), while the
hour-by-hour agreement on the 32.1 C line is unchanged (97.1%, previously
97.3%) -- the correction fixed the trend and the bias without disturbing the
strong day-to-day agreement that was already there. The section 4.1 headline
now cites these corrected figures directly.

### 5.9 Site-scale surface heat from satellite imagery

Section 5.2 established that a single ~25 km forecast grid cell is a
reasonable, if mildly conservative, planning unit at the metro scale, but
that block-scale microclimate, a trench, a rooftop, sun-heated bare steel,
is not resolved by any public forecast product. This is an initial,
partial answer to that gap, using free satellite imagery rather than a
new physics model, and it is advisory only: it never feeds
`src/wbgt.py`, the scheduler, or `/api/plan`.

**Method.** For a site (`scripts/fetch_satellite_tiles.py`), Landsat
Collection 2 Level 2 surface temperature (`lwir11`, calibrated to Kelvin
via the asset's own scale and offset metadata, not a hardcoded constant)
and Sentinel-2 L2A visible/NIR/SWIR bands are pulled from Microsoft
Planetary Computer's public STAC API for cloud-masked scenes (Landsat
`QA_PIXEL` Clear bit; Sentinel-2 SCL, cloud/shadow/snow/nodata excluded)
over the last three warm seasons, and median-composited per pixel. This
is a **climatological pattern**, the typical surface-heat texture of a
place in summer, not a live reading; a single overpass is one moment in
time.

`src/lst_downscale.py` then downscales Landsat's native 30 m composite to
Sentinel-2's 10 m grid: NDVI, NDBI and a brightness proxy are aggregated
from 10 m to an exact 3x3 mean at 30 m, a gradient-boosted regressor
(LightGBM) is fit at 30 m, predicted back at native 10 m, and a smoothly
upsampled 30 m residual is added back so the output still matches the real
coarse measurement on average (a standard regression-kriging-style
downscaling step). Validation is by spatial block cross-validation (4
contiguous folds over the site tile), never random-pixel holdout, which
would leak neighbouring-pixel information. This is an internal-consistency
check, not a comparison against any ground sensor; no instrumented site
exists to validate against at 10 m, which is exactly the limitation
section 12 already names.

**A real run, Doha city centre, 2 km radius, 10 clearest scenes per
source over 2024 to 2026:** spatial-CV RMSE 2.9 C on 4 folds (rising with
more scenes as the composite firms up), composite mean 48.2 C with a 5.9 C
spread across the tile at the time of day these scenes were captured
(late morning, local time). Vegetated ground (NDVI > 0.3, about 7.5% of
the tile) reads about 2.5 C cooler than bare or built-up ground (about
83% of the tile) in the downscaled output, the correct and expected
direction, and a synthetic test with a known checkerboard vegetation
pattern (`tests/test_satellite_lst.py`) confirms the model recovers that
direction reliably before it is ever pointed at real data.

**What this is not.** It is not validated against a ground sensor network,
it is not live, and the land-cover proxy (NDVI/NDBI/brightness) is
correlational, not a physical surface energy balance. It answers "where
does this neighbourhood tend to run hotter or cooler" for siting and
awareness, for example choosing a shaded laydown area over a bare lot,
never "is it safe to work here right now," which stays the forecast
WBGT's job alone.

**Shipped.** `scripts/build_site_heat_map.py` builds one site;
`scripts/build_site_heat_presets.py` precomputes the app's known location
presets offline (this is a multi-minute, dozens-of-remote-reads job per
site, the same reason the replay weeks and the GEFS backfill are
precomputed rather than run inside a request) and publishes them to
`api/data/site_heat/`, served by `GET /api/site-heat`. The web map shows
it as an opt-in overlay, off by default, with its own colour ramp distinct
from the WBGT ramp used everywhere else, so the two are never visually
confused.

### 5.10 A second and a third GCC index

Qatar is the only GCC state that mandates WBGT by law; the others run
calendar-only midday bans, and industry practice in the wider region also
references at least two other indices: Dubai's heat-index-style "feels
like" reading, and Abu Dhabi's Thermal Work Limit (TWL). Both are now
implemented against the same 16-year Doha record used throughout this
report, so this is a characterisation on real data from day one, not a
formula sitting untested.

`src/heat_index.py` implements the NWS Rothfusz regression (Rothfusz,
1990) exactly, including both correction terms and the low-heat-index
simple formula for the regime it is required in, tested against an
independently re-derived copy of the same reference (16 cases,
`tests/test_heat_index.py`), not against the module's own arithmetic.
`scripts/heat_index_gcc_study.py` runs it over the regulated midday
window (10:00-15:00, June-September) of the corrected Doha record and
compares it to WBGT: **Pearson r = 0.87** across 12,258 hours, but heat
index reads **10.9 C hotter than WBGT on average** (std 2.7 C) on the
same real weather, because heat index has no wind or solar-radiation
term, both of which matter outdoors and both of which WBGT includes.
Using an illustrative comparator only (WBGT's own 32.1 C against the US
NWS's "danger" band, 41 C -- Dubai has no published numeric heat-index
stop-work threshold to compare against, only the calendar ban), the two
flag the same hour 85.0% of the time; heat index alone flags a further
12.1% of hours WBGT would clear, WBGT alone flags 2.9% heat index would
clear. The two indices are correlated but not interchangeable: a
contractor operating under Dubai's index instead of Qatar's would reach
a different stop-work judgement on a material fraction of real Doha
summer afternoons.

**Abu Dhabi's Thermal Work Limit was initially blocked, then unblocked
by the primary source itself.** TWL (Brake & Bates, 2002) is a
heat-balance index using dry-bulb, natural wet-bulb, globe temperature,
wind and pressure, with a published risk-band structure, but its
closed-form equations sit behind a paywalled journal article and no
secondary source found reproduces them in full. The primary source
does exist in full, though: Brake's 2002 Curtin University PhD thesis
(the same derivation the journal paper condenses) is openly available
from Curtin's repository, and its Appendix C reproduces the actual
Visual Basic reference implementation Brake distributed to industry --
not just the equations, the shipped, validated code. `src/twl.py` is a
direct function-for-function port of that reference implementation
(`fHstTWLnew`, "TWL Formulation I: Standard Formulation").

That code turned out to matter for more than convenience: Chapter 3.1's
narrative derivation (the readable walkthrough, pp. 95-107) describes a
three-zone piecewise evaporation model, and a first implementation
against that narrative alone produced a real bug -- TWL was
non-monotonic in air temperature, occasionally reading *higher* at a
hotter temperature than a cooler one, traced to a genuine discontinuity
in the narrative's own printed zone-boundary formula (independently
re-verified against the source page, not a transcription slip on this
project's part). Appendix C's actual code resolved it: the shipped
`fQbalError` function assumes fully wet skin throughout the energy
balance (skin wettedness = 1) and does not use the zone model at all --
the narrative section describes the physiological reasoning behind
the index, not the formula that ships. The port here follows the code,
is monotonic in temperature, humidity and wind as a heat-stress index
should be, and reproduces the thesis's own Figure 18 comparison chart
(Hot, Dry, DB=MRT=WB+10, 0.5 m/s) to within a few W/m^2 at every
wet-bulb point read off it (`tests/test_twl.py`).

One further real behaviour carried over from the reference code: TWL is
not simply "solve at the 38.2 C core-temperature limit and stop." The
reference implementation scans trial core temperature upward and halts
at whichever limit is reached first, core temperature or the 1.2 kg/hr
sweat-rate cap; `src/twl.py` replaces the discrete 0.1 C scan with an
exact root-find for the same crossing. In hot, humid conditions --
Doha's, specifically -- the sweat-rate cap binds before the core-
temperature cap materially more often than in hot, dry conditions, so
this is not a corner case for this project's actual use.

Not yet done: wiring TWL to run end-to-end on Harara's own weather
record. The index needs mean radiant temperature as an input, and
`thermofeel` (already a dependency, used for WBGT) has no public
function that derives it from the shortwave-only radiation fields the
Doha archive carries -- a real, scoped follow-up, not a shortcut taken
here.

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
full 2000-2019 May to September run takes on the order of 15 hours; it is run
newest-year first so the overlap with the patched-WBGT record (2010-2019) is
available soonest, and it is resumable at the (init-day, member) level so it
survives restarts and picks up where it stopped. 2001 through 2019 are fully
backfilled; 2000 is the one year still landing. That does not affect anything
below: the patched-WBGT truth series starts in 2010, so 2000-2009 carry no
overlap to score against regardless, and every result in section 6.4 already
uses the full available 2010-2019 truth overlap. `run_all.sh` with
`GEFS_BACKFILL=1` completes the fetch and refreshes this section if the
backfill is ever repeated from scratch.

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

### 6.4 Results, full 2010-2019 truth overlap

The GEFS x patched-WBGT overlap is 10 years (2010-2019); walk-forward scores
the 7 years from 2013 (>= 3 training years required), on the humidity-
corrected truth series (section 5.8). Ensemble-mean WBGT RMSE is 1.68, 1.74
and 1.77 C at forecast days 1, 2 and 3; EMOS calibration (nonhomogeneous
Gaussian regression, per lead and month) brings that to 1.29, 1.36 and 1.41
C. For reference (non-paired, the archives do not overlap in time) the
Open-Meteo blend achieves 1.01 to 1.14 C at the same leads (section 5.1,
re-verified) - the raw GEFS
point forecast is not competitive with the operational blend at this single
coastal point, which is expected: GEFS v12 is a frozen 2000-vintage 0.25
degree model, not a modern data-assimilating system.

The raw ensemble is under-dispersed by a factor of two to three
(spread-to-RMSE 0.35 to 0.42; the raw-ensemble outer-rank mass is 0.69 to
0.74 against a flat-calibration target of 0.50). EMOS corrects most of this
(PIT outer-decile mass 0.25 to 0.27 against a flat target of 0.20) and
improves CRPS by 32 to 36% (CRPSS +0.32 to +0.36, interval clear of zero at
every forecast day, e.g. [+0.32, +0.41] at day 1) - slightly better than the
pre-correction figure (+0.30 to +0.33), since the corrected target carries
more genuine variability for EMOS to explain. EMOS mean absolute error (0.98
to 1.09 C) is now level with, and at some leads slightly ahead of, the
Open-Meteo blend reference (1.01 to 1.14 C, section 5.1, also re-verified) -
before the correction the blend was clearly ahead (0.80 to 1.00 C). The
comparison is still non-paired (the archives do not overlap in time) and the
GEFS record is a 2000-2019 archive against the blend's 2022-2026 forecast
window, so this is not evidence GEFS has caught up; it says the two numbers
moved together when the same correction was applied to both targets, which
is what re-verification is supposed to show. May is data-thin and its
EMOS cells pool to the neighbouring months and then to a lead-only fit
(9 cells flagged in `data/gefs_emos.json`).

**Reliability** (`scripts/gefs_reliability_study.py`): 9 overlap years
(2011-2019; one fewer than calibration, since the anomaly features need a
prior year of the same forecast-day/day-of-year cell), 6 scored. Predicting,
from issue-time GEFS features alone, whether the day's peak-WBGT forecast
will land in the worst decile of error against the corrected patched-
reanalysis target: the LightGBM classifier reaches PR-AUC 0.193 (interval
[0.151, 0.245]) against a climatological base rate of 0.111 and a
spread-decile rule at 0.115 (ROC-AUC 0.662) - a real, and on the corrected
target somewhat stronger, lift than the pre-correction figure (0.135 vs a
0.078 base rate), but still not an operationally useful alarm: at a
precision around 0.25 it flags 52 of 2,754 forecast-days (recall 0.04) and
its calibration is poor in the confident bins (predicted 0.60, observed 0.22
in the top bin). This predicts GEFS-versus-reanalysis divergence, not
GEFS-versus-observation (the target carries its own error, section 5.8); a
real early-warning signal for forecast surprise exists here but this
classifier is not yet strong enough to act on.

**Scheduler.** With the calibrated ensemble driving `scheduler_study.py
--uncertainty gefs` on its full truth overlap (841 to 843 test days per lead,
2014-07-18 to 2019-10-03) against the corrected truth series, see section 8
for the current worker-time and stochastic-versus-deterministic numbers, and
the results ledger (row 12d) for whether the "confirmed and sharpened"
verdict survives now that the analog-scenario result itself has weakened.

## 7. Operational gap analysis

`scripts/work_rest_analysis.py` applies the ACGIH TLV and Action Limit
screening criteria (`src/heat_stress.py`) to the 16-year patched WBGT record,
over daylight outdoor hours in April to October.

- The calendar ban covers 25% of those hours.
- Share of daylight hours requiring a full stop: light/acclimatised 23%,
  moderate/acclimatised 39%, heavy/acclimatised 50%, moderate/unacclimatised
  60%, heavy/unacclimatised 68%.
- Unsafe hours outside the ban window: heavy/acclimatised 685 per year (36% of
  hours outside the ban), heavy/unacclimatised 1099 per year (58%). Overall,
  64% of the unsafe daylight hours for heavy unacclimatised work occur outside
  the ban, in mornings, evenings and the shoulder months.
- Hours the ban closes that are in fact safe for continuous light acclimatised
  work: 7%; for anything heavier, close to 0%.

(Recomputed on the humidity-corrected record, section 5.8; this finding barely
moves - the calendar-ban coverage gap is a shape-of-the-day result, not a
level one, so it is not sensitive to the archive's summer humidity drift the
way the section 4.1 trend was.)

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

**Worker time is a constraint, not a free variable.** The bare LP above
minimises peak retained load with no bound on how long the crew is on site, so
on a hot day it thins work into a wide, fragmented plateau: full output spread
across a 14 to 15 hour on-site day around a long midday hole. For a bussed-in
accommodation worker that on-site rest is not rest. The LP is now solved inside
an outer search over contiguous on-site windows `[t_in, t_out]` with
`t_out - t_in + 1 <= work_hours + 2`; the day is held to at most two work
blocks and no sub-1.5-hour block (enforced by discarding candidates after the
solve, so no integer variable enters); and the per-window objective gains a
total-variation penalty against fragmentation and a small deviation penalty
toward an earlier-start reference block. The window score adds a residual cost
for resting in the heat on site. A plain **earlier-start fixed block** (start
at first light, work through, pause only for hours over 32.1 C) is scored the
same way and shipped when it delivers the work and scores at least as well; it
is also reported as a baseline in its own right. `cumulative_exposure`
`= sum_h w_h * max(0, WBGT_h - 28)` is the time-integrated heat dose over
worked hours, a metric a stretched day can worsen while lowering the peak. The
outer search is 18 window solves for a 14- or 15-hour day. Details in
`docs/scheduler_worker_time_plan.md`.

Walk-forward over 236 held-out days (June 2025 to August 2026), scored against
realised WBGT, at the 24 hour lead (48 and 72 hour are within rounding):

| Policy | Peak load | p90 | Heat dose | On-site span h | On-site rest h | Blocks | Unmet |
|---|---|---|---|---|---|---|---|
| Calendar (17/2021 style) | 8.67 | 16.29 | 18.5 | 15.0 | 6.0 | 2.0 | 0% |
| Earlier-start fixed block | 6.33 | 10.05 | 10.5 | 12.4 | 5.4 | 1.7 | 49% |
| Reactive (coolest safe first) | 8.86 | 17.86 | 18.6 | 15.0 | 6.0 | 2.1 | 0% |
| Optimiser (span-capped) | 11.36 | 21.01 | 24.8 | 11.3 | 2.3 | 1.1 | 0% |
| Clairvoyant (oracle, span-capped) | 10.50 | 19.34 | 24.0 | 11.1 | 2.1 | 1.1 | 0% |

Worker-time guarantee: on all 236 days the optimiser's on-site span, on-site
rest hours and block count are each at or below the calendar rule's (0
violations, all three leads).

**The 14% peak-load reduction does not survive.** It was bought with on-site
hours: the unbounded optimiser lowered the peak by spreading work over a
longer day. Held to `work + 2` hours and two blocks, the CVaR optimiser must
cram full output around the midday peak and runs about 31% *hotter* than the
calendar rule on mean peak retained load (interval [+2.30, +3.06] at 24 h),
with a higher heat dose. That gap is smaller than an earlier pass on this
same study found (about 44%) - the humidity correction (section 5.8) raises
the calendar rule's own peak too (8.67 against the pre-correction 8.01), so
part of the earlier gap was the calendar policy looking better than it truly
is, not the optimiser looking worse. The direction is unchanged: the
calendar rule's fixed 10:00 to 15:30 break is doing real protective work on
the hottest days, and no worker-time-respecting daily optimiser beats it
there. A plain earlier start is the best policy on heat (peak 6.3 against
8.7, p90 10.1 against 16.3, dose 10.5 against 18.5) and no worse on worker
time, but on about half of peak-season days it cannot deliver all 9
work-hours without working over 32.1 C, so it trades output for safety
rather than giving both. The honest conclusion: once worker time, day
fragmentation and heat dose are constrained, the daily scheduling layer is
not a free improvement over the enforceable calendar rule. The gains that
matter are structural (section 12), and the daily layer's job is to be never
worse for the worker than that rule.

(The earlier-start block itself is capped at the same two-block budget as the
optimiser: without that cap, a day with two separate hot spells could pause
for both and open a third block, on rare days breaking the guarantee the
policy exists to hold. That fixed baseline then ends the day early - a bigger
shortfall - rather than fragment further. `src/scheduler.py`, `test_scheduler_
windowed.py::test_policy_earlier_start_never_exceeds_the_block_cap`.)

On the pre-correction record, the stochastic (CVaR) optimiser was 3% worse
than the deterministic point-forecast optimiser on analog scenarios (interval
[-0.25, -0.11]). On the corrected record this weakens substantially: -1% at
forecast days 1 and 3 (intervals [-0.15, +0.02] and [-0.14, +0.02], both now
crossing zero) and a narrow, only just significant -1% at day 2 ([-0.19,
-0.01]). The corrected humidity record is itself somewhat harder to hedge
against profitably than the pre-correction one - reported plainly rather than
kept at the earlier, more clear-cut number. The direction has not reversed
(stochastic is still numerically worse or tied at every lead, never better),
but "hedging is clearly worse" is now closer to "hedging is not shown to
help, and is not clearly harmful either" at two of the three leads.

**Checked against a real, honestly-spread ensemble - and this time the two
samples disagree.** `scripts/scheduler_study.py --uncertainty gefs` re-runs
the comparison with the calibrated GEFS v12 ensemble (section 6) on its full
2010-2019 truth overlap (841 to 843 test days per lead, 2014-07-18 to
2019-10-03) against the corrected truth series. Here the stochastic-versus-
deterministic finding does NOT weaken: -0.39 to -0.41 retained-load units at
forecast days 1 to 3, interval clear of zero at every lead ([-0.48, -0.33] at
day 1), essentially unchanged from the pre-correction result (-0.36 to
-0.41). The span-capped optimiser runs 47 to 48% hotter than the calendar
rule on this sample (down from 51 to 54% pre-correction, a smaller shift than
the analog test's), and earlier-start and calendar remain essentially tied
(7.8 to 7.9 against 8.0). The worker-time guarantee again holds with zero
violations across all 2,526 optimiser-days.

So the humidity correction moved the analog-scenario hedging result toward
"not significant" but left the GEFS-ensemble hedging result clearly
significant, on two different test windows (2025-2026 for the analog study,
2014-2019 for GEFS, the only years the reforecast truth overlap allows).
Read together rather than picking one: hedging is not reliably helpful, and
whether it is reliably harmful now depends on which years and which
uncertainty source are used to test it - a real, now-documented sensitivity
that a single-sample answer would have hidden.

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

### 9.1 External validation on real physiology

The synthetic study uses the two-node model as its own ground truth, so it can
only show the filter recovers what it assumes. To test the filter against real
bodies it was run on the PROSPIE dataset (Havenith et al., Loughborough
University, figshare `10.17028/rd.lboro.26076577`, CC BY-NC 4.0):
40 participants, 154 usable trials, treadmill walking in a climate chamber at
25, 35 and 40 C, permeable or impermeable clothing, some trials with a
600 W/m^2 radiant load, at 1-minute resolution, with a 10 cm rectal probe as
the reference. `scripts/twin_external_validation.py`.

Heart rate and mean skin temperature (ISO 9886 weighting of 11 sites) are
mapped to the filter inputs; metabolic rate is the ACSM walking estimate from
treadmill speed and grade. Nothing is tuned on the scored subject: the particle
filter runs on library defaults, and the ECTemp-class comparator's population
heart-rate-to-core curve is fit leave-one-subject-out. Aggregates are the mean
of per-subject means (subject as the random effect); 95% CIs and repeated-
measures Bland-Altman limits of agreement are from a cluster bootstrap over
subjects (2000 resamples, seed 0). The first 8 minutes of each trial are a
filter burn-in and are not scored.

| Method | bias (C) | RMSE (C) | MAE (C) | 95% LoA (C) | 95% CI coverage |
|---|---|---|---|---|---|
| ECTemp-class HR-only EKF | -0.45 [-0.50, -0.40] | 0.52 [0.48, 0.56] | 0.48 | [-0.83, -0.07] | - |
| PF, HR + activity | +0.10 [-0.02, +0.20] | 0.54 [0.43, 0.62] | 0.45 | [-0.84, +1.04] | 42% |
| PF, HR + activity + skin | +0.00 [-0.05, +0.05] | 0.41 [0.39, 0.44] | 0.35 | [-0.44, +0.44] | 36% |

What holds from the synthetic study: the skin channel is what makes the physics
filter better than heart rate alone. With HR and activity only, the filter
matches the ECTemp-class baseline on RMSE (0.54 vs 0.52) and improves only the
bias (+0.10 vs -0.45 C). Adding the skin-temperature channel takes RMSE to
0.41 C (a 21% reduction on the baseline, CI on the paired per-subject
difference excludes zero), removes the bias, and halves the limits of agreement
(+/-0.44 vs the baseline's [-0.83, -0.07]). It is also stable across the
clothing and solar splits, where the HR-only configuration degrades
(RMSE 0.65 C under impermeable clothing, a known weakness: the two-node model's
clothing vapour permeability is fixed). For comparison, a tuned deep model on
the same data family reports RMSE 0.29 C against the same ECTemp baseline at
0.34 C (Zhao et al., 2026); the physics filter is less accurate than that but
beats the conventional baseline without any fitting.

What does not transfer: the synthetic 0.083 C MAE. On real bodies the best
configuration is 0.35 C MAE, four times worse, because real inter-individual
variation and model structural error are absent from the synthetic ground
truth. And the credible intervals are not calibrated out of domain: nominal 95%
intervals cover the rectal temperature only 36 to 42% of the time. The point
estimate is usable as-is; the stated uncertainty needed a fix before it could
be trusted, and section 9.2 supplies one.

### 9.2 Conformal calibration of the credible interval

A 36-42% coverage rate on a stated 95% interval is not a rounding error; it
means the filter's process-noise uncertainty describes how uncertain the
*model* is about its own state, which is not the same thing as how often the
model is actually right against a real body. Retuning the process noise by
hand to hit 95% on PROSPIE would just be fitting the calibration set with an
extra step in between; conformal prediction instead measures the gap directly
and closes it with a distribution-free guarantee.

`src/conformal.py` implements split conformal prediction with a CQR-style
(Romano, Patterson & Candes, 2019) nonconformity score: for a held-out point,
`max(lo - y, y - hi)` is how far the truth fell outside its own interval (zero
or negative if it was inside). The empirical `ceil((n+1)(1-alpha))/n` quantile
of that score, added symmetrically to both bounds, gives a marginal coverage
guarantee of at least `1-alpha` under exchangeability alone - no assumption
that the residuals are Gaussian, and no change to the particle filter itself.

The correction is fit and validated with the same leave-one-subject-out
discipline as the ECTemp curve in 9.1: for each of the 40 subjects, the
correction is fit on the other 39 subjects' scored minutes only, then applied
to the held-out subject and scored there, so the reported number is an honest
estimate of what a worker the filter has never seen would get, not the
calibration set's own coverage.

| Configuration | raw 95% coverage | corrected coverage (LOSO mean) | per-subject range | correction |
|---|---|---|---|---|
| PF, HR + activity | 41% | 94% | 31-100% | +/-0.77 C |
| PF, HR + activity + skin | 35% | 95% | 74-100% | +/-0.67 C |

The mean lands almost exactly on the 95% target for both configurations. The
guarantee conformal prediction gives is marginal, not conditional: it holds on
average over the calibration population, not for every individual subject, and
the HR-only configuration's 31-100% per-subject range shows that spread
concretely - some individual workers would still be under- or over-covered
even after correction. The skin-channel configuration is both more accurate
(9.1) and better calibrated per-subject (74-100%), which is one more reason it
is the configuration to carry into a pilot.

The shipped correction (`data/conformal_calibration.json`, regenerated by
`scripts/twin_external_validation.py`, fit on all 40 subjects) is a single
scalar per sensor configuration: widen the stated interval by 0.77 C
(HR-only) or 0.67 C (HR + skin) on both sides. `scripts/digital_twin_demo.py`
demonstrates applying it. This is advisory infrastructure, not a safety
threshold change: it does not alter the point estimate, the WBGT computation,
or the scheduler, and it does not remove the domain-shift caveat below -
conformal calibration corrects the *interval width* for the population it was
fit on; it cannot correct for a population (Gulf outdoor workers, not
European treadmill volunteers) the calibration set does not represent. That
is still the pilot's job.

Domain shift from the intended use is large: European laboratory volunteers
walking on a treadmill, not Gulf outdoor workers; research thermistors, not a
cheap wearable patch; a rectal probe, not the ingestible capsule the pilot
assumes. The result supports the ordering claim (the physics filter with a
skin channel beats heart rate alone on real data) and refutes the synthetic
error magnitude. USARIEM's ECTemp (Buller et al., 2013) estimates core
temperature from heart rate alone with a random-walk model and no forecast
coupling; ISO 7933, Fiala and JOS-3 are open-loop forward models. The
combination here, assimilating a physics model to a worker's live sensors and
propagating it under the WBGT forecast, validated against ingestible-capsule
temperature in a migrant-labour cohort, has not been published. The pilot
design is in `docs/digital_twin_protocol.md`.

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

**The conversational assistant** (`api/chat.py`, `api/chat_scope.py`,
`api/kb.py`) is a bounded front end on top of the same core. Every message
is classified by keyword and pattern, before any model call, into one of
plan_request, weather_question, heat_safety_question, rules_question,
about_harara, emergency, or out_of_scope. Only those buckets go further.
Out-of-scope messages, including prompt-injection attempts
(ignore-instructions, you-are-now, system-prompt extraction, role wrappers,
base64), get one fixed reply and no model call. A message describing
heat-illness signs gets a fixed first-response block from a curated
knowledge-base entry, with a banner to call the local emergency number, and
no model. Heat, first-aid, acclimatisation and "what is Harara" questions
are answered by serving a retrieved KB entry's own text with its published
source shown; the model does not paraphrase it. Rules questions return the
Qatar rule from the rule store or a cited KB summary for the UAE and Saudi
Arabia. Weather questions are answered by a deterministic sentence off one
of five forecast tools (`nowcast`, `coolest_window`, `climatology_compare`,
`heat_trend`, `weekly_outlook`), each with its source; only a multi-day
comparison is phrased by the model, and only after passing the numeric
guard and an output scope guard that rejects any reply drifting into code,
prose forms, or other domains. Refusals are counted by intent bucket only,
never by content.

**Evaluation** (`eval/agent_eval.py`, four rule documents with
hand-labelled gold records under `eval/agent_eval/rules/`, 18 natural-
language requests, 10 briefing scenarios, and a scope-lock section). Against
the mock the layer scores field-level precision and recall of 1.0 on all
four extracted constraint types with every citation resolving;
outcome-exact-match 1.0 over the 18 requests with every ambiguous request
asking back; zero ungrounded numbers across 61 numeric tokens in generated
briefings, with the numeric guard catching every injected number; every
rule reference resolving; and, for the assistant, the fixed reply on every
out-of-scope and injection prompt, the banner and first-response block on
every emergency prompt, and a shown source on every grounded answer. These
figures measure the plumbing and the guards, not the language model: the
mock is a regex stand-in and the source documents use canonical phrasing.

**Against a real model.** The layer was scored with K2-Horizon
(`IFM/K2-Horizon-375B-A23B`, temperature 0) driving all four functions,
run twice. Anthropic could not be scored here (SDK and key absent); the
harness now runs each section independently and records a missing adapter
as a per-section error rather than failing the run.

K2 on the IFM endpoint is not reproducible at temperature 0, so the two
runs are reported as a range. Stable across both: every ambiguous request
returned a clarification and none was guessed; parsed-field accuracy 1.0;
banned-hour-window extraction P/R 1.0; every quote K2 returned was a
verbatim substring, so citation validity is 1.0 and the store accepted
only locatable values; every `[rule:id#field]` reference resolved.
Variable across the two runs: the stop-work-threshold and seasonal-window
recall were 0.67 in one run and 1.0 in the other (in one run K2 did not
return the 32.1 C value from the Qatar Decision 17 text); outcome-exact-
match over the 18 requests was 0.89 to 0.94; the raw ungrounded-number
rate in briefings was 0.02 to 0.09 of numeric tokens. One consistent
weakness: workload rest ratios came back at P 0.57 (three ratios
extracted from the ACGIH table that are not in the gold set), R 1.0, in
both runs.

What did not fail on either run: the guard caught every injected foreign
number (4 of 4), and the guarded path (`generate_briefing`) either
returned a briefing with no ungrounded number and every rule reference
resolved, or refused. No run produced a number that reached a caller
without passing the guard. K2's briefings are chattier than the mock's
and carry stray numbers (clock times, table indices), so in production a
share of K2 drafts hit the retry-then-refuse path rather than return; the
eval's `write_briefing` figures are raw model output, measured before the
guard on purpose.

One change was made to the guard during this work, reported here rather
than folded in silently: the numeric guard now strips ISO and MM-DD
dates, clock times and kebab-case identifiers before scanning, and
whitelists rule values that came from a `lookup_rule` citation. This took
the raw ungrounded-token count on a K2 briefing run from about 85 to
about 25; no prompt was tuned to the eval.

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
   generality is untested. Section 5.9 gives a partial, advisory answer at
   the block scale from satellite imagery, but it is a climatological,
   uncalibrated land-cover proxy, not a validated physical measurement, and
   it still does not reach the instrumented-site data section 5.2 says is
   the real requirement here.
2. The gridded product under test is the Open-Meteo blend, and it carried a
   second archive defect beyond the November 2024 wind issue: a persistent
   summer humidity drift from 2018 onward, confirmed against both ERA5 and
   METAR (section 5.8). This one is applied: `data/doha_wbgt_16yr.csv` was
   rebuilt on the corrected record and every figure in this report is
   computed on it. The 71.7% of hours with a measured METAR value are as good
   as the wind-patched record already was; the remaining 28.3% (mostly
   pre-2014, before the METAR record starts) still carry Open-Meteo's
   humidity as-is, uncorrected.
3. The physiology in section 9 is synthetic, from a two-node rational model
   that runs core temperature up somewhat fast in strongly uncompensable heat
   and is not calibrated to field data; the error and calibration numbers are
   indicative only.
4. The section 9 process and target models share a family, so real-world error
   will be larger; the pilot quantifies the mismatch.
5. The scheduler uses one crew, one workload class and fixed acclimatisation,
   with a passive-retention thermal load and no intraday re-planning. The
   worker-time constraint bounds on-site hours and fragmentation but still does
   not model the commute to and from the labour accommodation, heat in the
   accommodation before and after the shift, cumulative fatigue across a
   split shift, or whether an earlier start or a night shift is operationally
   feasible at a given site. The earlier-start baseline's ~48% unmet-work rate
   in peak season is a real limit of that policy, not an artefact.
6. Wet-bulb via Stull (2011) has about 0.3 C RMS error, up to about 1 C bias
   near 42 C, which partly cancels in same-method differences.
7. The GEFS reliability and calibration studies are capped at the 10-year
   (calibration) or 9-year (reliability) GEFS x patched-WBGT overlap - GEFS
   only exists back to 2000 and the WBGT truth series only forward from 2010,
   so more of the 2000-2019 reforecast years does not add scorable years -
   and by using the patched reanalysis as their target (section 6.4). The
   reliability classifier's PR-AUC (0.135 vs a 0.078 base rate) is a real but
   modest, not yet operational, lift.
8. ACGIH TLVs are conservative population screening thresholds, not
   individualised medical limits.

## 13. Further work

1. The wearable pilot (`docs/digital_twin_protocol.md`): 30 participants over
   at least 4 sessions, ingestible-capsule ground truth, a mixed-effects
   Bland-Altman primary endpoint, and sensor-ablation and acclimatisation
   secondary endpoints.
2. Strengthening the GEFS reliability classifier (section 6.4) past a modest
   lift over the spread-decile baseline into an operationally useful alarm,
   and re-running it once more overlap years accumulate past 2019.
3. The humidity correction (section 5.8) is applied and every downstream
   section (4, 5.1 through 5.4, 5.6, 6, 7 and 8) is re-verified against it.
   None reversed, but two changed materially. Section 5.1's headline changed
   in kind rather than size: the LightGBM correction now beats the raw
   forecast on MAE and RMSE, where before it lost on both, though it still
   substantially worsens the safety-relevant miss rate either way. Section
   5.6's 2 m temperature track moved the most of anything re-verified,
   because the correction fixes the truth series' own temperature, not just
   its humidity: AIFS's and GFS's apparent cold bias roughly halved, while
   IFS's and GraphCast's warm bias grew by about the same amount the other
   way, and the component-bias explanation for AIFS's WBGT result had to be
   rewritten since the biases it previously relied on were partly the old
   truth series' own drift. Section 5.3 required a methodology fix, not just
   a re-run: its comparison reads temperature and humidity from the
   production WBGT file, which the correction now substitutes with METAR
   for 71.7% of hours, silently turning "gridded product versus station"
   into "station versus itself" for most days; re-pointed at the raw,
   unpatched Open-Meteo archive for temperature and RH, every number came
   back unchanged to two decimal places.
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
