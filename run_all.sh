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
# Fixed seeds throughout; see docs/technical_report.md. ERA5 is a slow
# optional background job (report S2).

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
  if [[ $GEFS_BACKFILL -eq 1 ]]; then
    run scripts/fetch_gefs_reforecast.py --start-year 2000 --end-year 2019 \
        --months 6 7 8 9 --newest-first --workers 24
  else
    echo; echo "-- GEFS backfill skipped (GEFS_BACKFILL=1 to include)"
  fi
fi

# ---------------------------------------------------------------- 2. WBGT + patch
run scripts/patch_wind.py
run scripts/run_first_result.py --data data/doha_weather_16yr_patched.csv

# ---------------------------------------------------------------- 3. studies
run scripts/compare_wind_sources.py
run scripts/diagnose_wbgt.py
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

# ---------------------------------------------------------------- 6. contributions
run scripts/scheduler_study.py
run scripts/digital_twin_demo.py
run scripts/make_figures.py

echo; echo "=== done. see docs/technical_report.md ==="
