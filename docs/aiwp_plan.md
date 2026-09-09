# Plan: AI weather models for Gulf humid heat

Do AI weather prediction models under-forecast Doha humid-heat extremes, at
what leads, by how much, and how many stop-work hours does that miss?
Motivation: arXiv 2504.21195 finds GraphCast, Pangu and GEFS carry a
consistent regional **cold** bias in 2 m temperature in the 5-10 days
before CONUS heat-wave onset. Cold bias before extreme heat is the
dangerous direction. Nobody has checked this for WBGT in the Gulf.

Scored the way this repo scores forecasts: walk-forward, against the
METAR-patched observational truth, miss rate at 32.1 C as the headline,
not average error.

## 1. Models and coverage

Source: Open-Meteo Previous Runs (`historical-forecast-api.open-meteo.com`,
`<var>_previous_dayN` fields, N = 1..7). The previous-runs API and the
historical-forecast API share this backend; results are identical. Grid
point 25.27 N, 51.61 E snaps to the 25.25 / 51.5 cell (elevation 4 m,
coastal), the same cell used throughout the repo.

Coverage was probed directly on 2026-09-09. Windows below are the
first date at which the full variable set returns non-null through the
truth-data end (2026-08-30).

| Model | Open-Meteo id | Role | Fields on the feed | Usable window (this study) |
|---|---|---|---|---|
| ECMWF IFS-HRES | `ecmwf_ifs025` | physics NWP reference | T, RH, wind10, SW, direct, P | full set 2024-03-05 -> 2026-08-30 (T alone from 2024-02-08) |
| ECMWF AIFS Single | `ecmwf_aifs025_single` | AI model (deterministic) | T, RH, wind10, SW, direct, P | full set 2025-02-26 -> 2026-08-30 |
| NOAA GraphCast | `gfs_graphcast025` | AI model (deterministic) | **T and cloud_cover only** | T only, 2024-09-01 -> 2025-09-30, with production gaps; null after ~2025-10 |
| NOAA GFS | `gfs_seamless` | physics NWP; GFS/UFS deterministic reference, same family as the repo's GEFS reforecast | T, RH, wind10, SW, direct, P | full set 2024-02-11 -> 2026-08-30 (T alone back to ~2015) |

`ecmwf_aifs025` (non-single) returns null at every probed date; use
`ecmwf_aifs025_single`. `ncep_gfs025` likewise null; `gfs_seamless` is the
served GFS.

**Consequence for the design.** GraphCast on the public feed carries no
humidity, pressure, wind or radiation, so a genuine WBGT forecast cannot
be built from it. The study therefore has two tracks:

- **WBGT track (headline):** IFS, AIFS, GFS. Full Liljegren WBGT, miss
  rate at 32.1 C, pre-heat-wave WBGT bias. This is the humid-heat question
  the project cares about and where the novelty sits.
- **2 m-temperature track:** IFS, AIFS, GFS **and GraphCast**. Signed bias,
  MAE, pre-heat-wave bias, "hot-hour" miss rate at the prior-years 95th
  percentile of warm-season daylight T. This is the direct replication of
  the arXiv finding and the only place GraphCast can appear.
- **Appendix sensitivity:** WBGT recomputed with GraphCast T substituted
  into IFS humidity + radiation + wind, to isolate whether GraphCast's T
  error alone would flip stop-work calls. Clearly labelled as a hybrid,
  not a GraphCast WBGT forecast.

Warm seasons captured (full set, warm-season daylight only): IFS and GFS
~2.5 (2024, 2025, partial 2026); **AIFS ~1.5 (2025 + partial 2026)** — the
binding sample-size constraint, stated everywhere AIFS is reported.
GraphCast T: one clean core summer (2025) plus 2024 from September.

Long-record complement: the repo's GEFS v12 reforecast (2000-2019,
`data/gefs/`, patched-WBGT overlap 2010-2019; `gefs_calibration.py`,
`gefs_reliability_study.py`) is cross-referenced for the GFS-family
deterministic bias/RMSE over a decade, as context for whether the
~2.5-season GFS number here is consistent with the long record.

## 2. Lead convention

`<var>_previous_dayN` is the value for a given valid hour as it stood in
the model run from N days earlier. Nominal lead = N x 24 h; the underlying
run is 0.75-1.75 x 24 h old depending on valid hour and the 00Z cadence.
Same convention as `scripts/fetch_openmeteo_forecast_archive.py` and
technical_report Section 5.1. Leads N = 1..7.

## 3. Warm-season and daylight window

- **Warm season:** 1 May - 30 September (months 5-9). Wider than the Qatar
  statutory window (1 Jun - 15 Sep) so onset and offset shoulders are
  captured; narrower than the regime study's Apr-Oct because April and
  October almost never breach 32.1 C WBGT and would only dilute the
  exceedance base rate.
- **Daylight:** local Asia/Qatar hour in [7, 18] **and** `cos_zenith > 0`.
  WBGT > 32.1 C in Doha falls roughly 08:00-17:00; [7, 18] is safely
  inclusive and matches when outdoor work happens. Night hours carry no
  stop-work decision (no globe-temperature load) and are excluded from the
  headline; a full-warm-season variant is reported for MAE/bias
  completeness only.

All timestamps UTC internally; local hour via `tz_convert("Asia/Qatar")`.

## 4. Heat-wave onset (leakage-safe)

Applied independently to the truth series for WBGT and for 2 m T.

1. From the patched truth, per calendar day, take the **daily maximum**
   over warm-season daylight hours.
2. For evaluation year Y, the threshold is the **90th percentile of
   daily-max values over warm-season days in years strictly before Y**
   (2010..Y-1). With forecasts starting 2024, this always rests on >=13
   years of prior truth. Using pre-forecast truth climatology is not
   leakage: it is exactly the climatology an operator has at issue time.
3. **Onset day** = the first day of a run of >= 2 consecutive warm-season
   days at or above that threshold, whose immediately preceding day was
   below it (so onsets are transitions *into* a heat wave, not mid-event
   days).
4. **Pre-onset window** = the N days before onset. Headline N = 5 (the
   arXiv "5-10 days before"); N = 3 and N = 7 also reported.
5. **Pre-heat-wave bias** at lead L = mean signed error (forecast - truth)
   over every forecast-valid hour in warm-season daylight whose valid date
   is in [onset - N, onset - 1], for that model and lead. Compared against
   the all-warm-season-days bias at the same lead: the excursion between
   the two is the analogue of the published result.

Onset detection is unit-tested (synthetic daily series with known
transitions, boundary cases: run of exactly 2, run starting on day 1 of
the season, back-to-back events).

## 5. Method

1. **Fetch** (`scripts/fetch_previous_runs.py`, resumable). One request per
   model over 2024-01-01 -> 2026-08-30, yearly chunks (politeness +
   resume), `timezone=UTC`, `wind_speed_unit=ms`. Reshape the wide
   `_previous_dayN` response to **one tidy file per (model, lead)**:
   `data/previous_runs/<model>__lead{N}d.csv`, columns
   `time, temperature_2m, relative_humidity_2m, wind_speed_10m,
   shortwave_radiation, direct_radiation, surface_pressure`
   (GraphCast: `time, temperature_2m, cloud_cover`). Skip a file already
   present and covering the range; `--refresh` forces refetch. Full-year
   rows are cached; warm-season filtering happens at analysis time.
2. **WBGT from model fields** (`src/forecast_wbgt.py`, new, unit-tested):
   `wbgt_from_forecast_frame(df, lat, lon)` computes `cos_zenith` via
   `src.solar.cos_solar_zenith_angle` and calls
   `src.wbgt.wbgt_liljegren_c` with the same argument mapping as
   `run_first_result.add_wbgt`. `direct_radiation` passed through
   (`fillna(0)`); if a model-lead ever has SW but no direct, fall back to
   an Erbs cos_zenith split and record that it fired (not expected — IFS,
   AIFS, GFS all serve direct). Night rows (`cos_zenith == 0`) return a
   finite WBGT. Test: tiny known frame reproduces a direct
   `wbgt_liljegren_c` call to 1e-6; missing-column raises a clear error.
3. **Truth**: `data/doha_wbgt_16yr.csv` (built from
   `doha_weather_16yr_patched.csv`, METAR wind patch from 2024-11). Truth
   WBGT uses measured wind; forecast WBGT uses each model's forecast wind
   as issued — that is the real forecast an operator receives. A wind
   check is reported: forecast-wind minus METAR-wind bias over the
   overlap, per model. A forecast low-wind bias inflates forecast WBGT,
   which *masks* a cold bias — so any WBGT cold bias found is a lower
   bound. Stated in the report.
4. **Score** (`scripts/aiwp_humid_heat_study.py`), `eval/harness.py`
   conventions, per (model, lead):
   - MAE, RMSE, signed bias — overall and stratified by truth-WBGT band
     `<28, 28-30, 30-32, 32-34, >34` (fixed physical edges, no leakage).
   - **Miss rate at 32.1 C** (`eval.harness.evaluate`
     `false_negative_rate`): of truly-exceedance daylight hours, the
     fraction the forecast placed below 32.1. Plus false-positive rate.
     Headline.
   - Pre-heat-wave bias per Section 4, WBGT and T tracks.
   - Baselines through the same `evaluate`: `baseline_persistence`
     (WBGT at valid time minus N*24 h) and
     `baseline_climatology_walk_forward`.
   - **Block-bootstrap 95% CIs** on every headline number, reusing the
     moving-block bootstrap from `scripts/regime_climatology_study.py`
     (`moving_block_ci`, block = 1 day of daylight hours, `N_BOOT = 2000`,
     `RNG = np.random.default_rng(20260909)`).
5. **Paired comparison**, per lead, paired block bootstrap on the
   hour-aligned difference: AIFS - IFS, GraphCast - IFS (T track),
   each AI model - GFS, on miss rate and on pre-heat-wave bias. Verdict
   per lead: does the AI model miss more exceedance hours / run colder
   before heat waves than the physics reference, and is the interval clear
   of zero.
6. **Sample-size statement**: AIFS ~1.5 seasons and one core summer;
   effective bootstrap N ~60-90 daylight-days; intervals wide, no
   over-claiming. IFS and GFS ~2.5 seasons, firmer. GEFS reforecast cited
   for the decade-scale GFS-family number.

Study writes tidy aggregates for the figures:
`data/aiwp_scores.csv` (model, lead, metric, value, ci_lo, ci_hi, n) and
`data/aiwp_preheatwave.csv` (model, lead, window_days, track, bias,
ci_lo, ci_hi, n_hours, n_events). ~150 rows total. `make_figures.py`
reads these rather than re-running the bootstrap (deviation from its
"recompute from base CSVs" note, justified by bootstrap cost; noted in
that file).

## 6. Figures (`scripts/make_figures.py` conventions: Okabe-Ito, one axis, `_save`)

1. `aiwp_missrate_vs_lead.png` — miss rate at 32.1 C WBGT vs lead 1-7 d,
   one line per model (IFS, AIFS, GFS), block-bootstrap CI band;
   persistence and climatology miss rate as grey references.
2. `aiwp_bias_vs_lead.png` — signed WBGT bias (forecast - truth, C) vs
   lead, per model, CI band, zero line. Warm-season daylight, all days.
3. `aiwp_preheatwave_bias.png` — signed WBGT bias in the pre-onset window
   (N = 5 d) vs lead, per model, CI band, against the all-days bias
   (dashed) at the same lead. The excursion is the arXiv analogue. Money
   figure.
4. `aiwp_temp_bias_vs_lead.png` — as (2) for 2 m temperature, four lines
   including GraphCast; all-days and pre-heat-wave (N = 5) as two panels.
5. `aiwp_bias_by_wbgt_band.png` — signed WBGT bias by truth-WBGT band,
   grouped bars per model, at headline lead 5 d. Shows whether the bias is
   worst in the dangerous `>32` band.

Core three are (1), (2), (3); (4) and (5) carry the temperature
replication and the band structure.

## 7. Deliverables

- `scripts/fetch_previous_runs.py` (resumable) + `data/previous_runs/`.
- `src/forecast_wbgt.py` + `tests/test_forecast_wbgt.py`.
- `tests/test_heatwave_onset.py`.
- `scripts/aiwp_humid_heat_study.py` — prints the per-(model, lead) table,
  the paired comparisons, and the pre-heat-wave bias result; writes the
  two aggregate CSVs.
- Five figures via `make_figures.py`.
- technical_report **Section 5.6 "AI weather models for Gulf humid heat"**
  (new subsection after 5.5; no renumbering) — tables, figures, the
  sample-size caveat, one-paragraph conclusion.
- results_ledger rows 23-27, adversarial style: question / script /
  result / verdict / consequence. A null result reported plainly if that
  is what the data shows.
- `docs/aiwp_summary.md` (uncommitted OK) — a preprint-intro draft: what
  was asked, what was found, why it matters for heat-safety decisions.

## 8. Discipline

- Seeds fixed (`np.random.default_rng(20260909)`); study otherwise
  deterministic.
- Unit tests: `wbgt_from_forecast_frame`, heat-wave onset.
- `run_all.sh`: new stage after GEFS —
  `fetch_previous_runs.py` inside the `FETCH` guard, then
  `aiwp_humid_heat_study.py` always; `--no-fetch` reuses
  `data/previous_runs/`.
- Leakage: heat-wave threshold from strictly prior years; WBGT bands are
  fixed physical edges; baselines via the existing leakage-safe harness;
  no model tuning or correction anywhere — evaluation only.
- Small commits, one per result: fetch script; forecast-WBGT module +
  test; onset definition + test; scoring script; figures; report + ledger.

## 9. Open choices to confirm before building

1. Warm season 1 May - 30 Sep vs the statutory 1 Jun - 15 Sep. Plan uses
   May-Sep for shoulder capture; the exceedance-only metrics are
   near-identical either way.
2. Daylight [7, 18] local vs a `cos_zenith` cut alone. Plan uses both.
3. Pre-onset headline N = 5 d (also 3, 7). Matches the paper.
4. Hot-hour threshold for the T track = prior-years 95th percentile of
   warm-season daylight T (there is no statutory T threshold to anchor to).
5. GraphCast hybrid-WBGT sensitivity: appendix only, or drop it. Plan
   keeps it in an appendix, clearly labelled.
