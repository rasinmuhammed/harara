#!/usr/bin/env bash
# Reproduce the Harara pipeline end to end.
#
#   ./run_all.sh              full pipeline (fetch -> studies -> twin)
#   ./run_all.sh --no-fetch   skip network fetches, use data/ as-is
#
# The GEFS v12 reforecast backfill (2000-2019, a multi-hour S3 job) is
# OFF by default even in fetch mode -- set GEFS_BACKFILL=1 to include it,
# or run it standalone:
#     .venv/bin/python scripts/fetch_gefs_reforecast.py \
#         --start-year 2000 --end-year 2019 --months 6 7 8 9 --newest-first
# It is resumable; the GEFS analysis stages below run on whatever years
# are present in data/gefs/.
#
# Fixed seeds throughout; see docs/technical_report.md. ERA5 (report S2, S5.7)
# is fetched separately with scripts/fetch_era5.py (a slow CDS-queue job,
# not run by this script); once data/era5/ has files, stage 3 below converts
# and cross-checks it automatically.

set -euo pipefail
cd "$(dirname "$0")"

PY=${PY:-.venv/bin/python}
FETCH=1
[[ "${1:-}" == "--no-fetch" ]] && FETCH=0
GEFS_BACKFILL=${GEFS_BACKFILL:-0}

run()      { echo; echo "=== $* ==="; "$PY" "$@"; }
run_if()   { [ -e "$1" ] && { shift; run "$@"; } || { echo; echo "-- skip ($1 absent): $*"; }; }

# ---------------------------------------------------------------- 0. sanity
"$PY" -m pytest -q

# ---------------------------------------------------------------- 1. data
if [[ $FETCH -eq 1 ]]; then
  run scripts/fetch_open_meteo.py --start 2010-01-01 --end 2026-08-31 \
      --out data/doha_openmeteo_16yr.csv
  run scripts/fetch_metar_othh.py --start 2014-01-01 --end 2026-08-31 \
      --out data/othh_metar_hourly.csv
  run scripts/fetch_openmeteo_forecast_archive.py --start 2022-01-01 \
      --end 2026-08-31 --out data/doha_forecast_archive.csv
  run scripts/fetch_previous_runs.py --start 2024-01-01 --end 2026-08-30
  if [[ $GEFS_BACKFILL -eq 1 ]]; then
    run scripts/fetch_gefs_reforecast.py --start-year 2000 --end-year 2019 \
        --months 6 7 8 9 --newest-first --workers 24
  else
    echo; echo "-- GEFS backfill skipped (GEFS_BACKFILL=1 to include)"
  fi
fi

# ---------------------------------------------------------------- 2. WBGT + patch
run scripts/patch_wind.py
run scripts/patch_humidity.py
run scripts/run_first_result.py --data data/doha_weather_16yr_patched.csv

# ---------------------------------------------------------------- 3. studies
run scripts/compare_wind_sources.py
run scripts/diagnose_wbgt.py
run_if data/era5 scripts/era5_to_csv.py
run_if data/doha_era5_hourly.csv scripts/era5_cross_check.py
run_if data/doha_era5_hourly.csv scripts/humidity_defect_study.py
run scripts/spatial_representativeness.py
run scripts/regime_climatology_study.py
run scripts/extreme_event_skill.py
run scripts/work_rest_analysis.py --data data/doha_wbgt_16yr.csv

# ---------------------------------------------------------------- 4. forecasting layer
run scripts/train_layer1_v1.py --data data/doha_wbgt_16yr.csv
run scripts/tune_layer1_threshold.py --data data/doha_wbgt_16yr.csv
run scripts/train_layer1_v2_nwp.py

# ---------------------------------------------------------------- 5. GEFS ensemble (if backfilled)
run_if data/gefs scripts/gefs_calibration.py
run_if data/gefs scripts/gefs_reliability_study.py
run_if data/gefs_emos.json scripts/scheduler_study.py --uncertainty gefs

# ------------------------------------------------ 5b. AI weather models (H-E)
# Reads data/previous_runs/ (fetched in stage 1, or reuse with --no-fetch).
run_if data/previous_runs scripts/aiwp_humid_heat_study.py

# ---------------------------------------------------------------- 6. contributions
run scripts/scheduler_study.py
run scripts/digital_twin_demo.py
# External validation of the heat-strain filter on PROSPIE (Loughborough,
# figshare 10.17028/rd.lboro.26076577, CC BY-NC 4.0). Downloads ~6 MB on
# first run; skips the fetch offline.
if [[ $FETCH -eq 1 ]]; then
  run scripts/twin_external_validation.py
else
  run_if data/prospie/prospie.xlsx scripts/twin_external_validation.py --no-fetch
fi
run scripts/make_figures.py

# ---------------------------------------------------------------- 7. agent layer
# Deterministic by default (MockLLM); set AGENT_MODEL to a real adapter to
# score the language model itself.
run scripts/rules_ingest.py --eval-set --out data/rules --model "${AGENT_MODEL:-mock}"
run eval/agent_eval.py --model "${AGENT_MODEL:-mock}" --json data/agent_eval.json

# --------------------------------------------------- 8. site data artefacts
# Small distilled tables the API ships (forecast-error band, one replay week).
run_if data/doha_forecast_archive.csv scripts/build_residual_table.py
run_if data/doha_wbgt_16yr.csv scripts/build_replay_weeks.py
run_if data/doha_wbgt_16yr.csv scripts/build_climatology_table.py

echo; echo "=== done. see docs/technical_report.md ==="
