"""
Fetch ERA5 hourly reanalysis for the Doha grid cell from the Copernicus
Climate Data Store (CDS), one NetCDF file per 6-month half-year.

WHAT ERA5 IS
    A reanalysis: one frozen modern forecast model re-run over 1940-present,
    continuously nudged toward every historical observation. Output is a
    physically consistent, gap-free, hourly ~31 km global grid. It is a
    model *estimate*, not station data - see fetch_metar_othh.py for the
    measured ground-truth check.

WHY WE USE IT HERE
    - exact radiation inputs for the Liljegren WBGT (accumulated SSRD and
      direct-beam, converted to W/m2), instead of Open-Meteo's hourly mean
    - a single documented, versioned product to bias-correct forecasts
      against (Open-Meteo's archive is an undocumented blend)
    - an independent cross-check on Open-Meteo (e.g. the 2025-26 wind bug)

ONE-TIME SETUP (do this before running)
    1. Create a free account: https://cds.climate.copernicus.eu
    2. Accept the ERA5 licence: open
       https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels
       -> "Download" tab -> tick "Terms of use" once.
    3. Get your API token: https://cds.climate.copernicus.eu/how-to-api
    4. Create  ~/.cdsapirc  (in your HOME dir, not this repo):
           url: https://cds.climate.copernicus.eu/api
           key: <your-token>
    5. pip install "cdsapi>=0.7"   (already in requirements.txt)

WHY QUARTERLY FILES
    The new CDS rejects large requests ("cost limits exceeded"). Cost is
    ~ (hours x variables): tested, ~4 months of 7 hourly variables is the
    ceiling, 6 months is over it. So each year is four files, _Q1.._Q4.
    2010-2026 = ~68 files. Files already present are skipped, so a failed
    run just resumes.

NOTE ON TIMELINESS
    Requests queue server-side. The most recent ~3 months are "ERA5T"
    (preliminary) and may be revised. This script only asks for months
    that are already complete.

Usage:
    python scripts/fetch_era5.py --start-year 2010 --end-year 2026 --outdir data/era5
"""

import argparse
import datetime as dt
import pathlib
import sys
import time

try:
    import cdsapi
except ImportError:
    raise SystemExit(
        "cdsapi not installed. Run: pip install 'cdsapi>=0.7'\n"
        "Then set up ~/.cdsapirc per this file's docstring."
    )

DATASET = "reanalysis-era5-single-levels"

# Small box around Doha (25.27 N, 51.61 E). ERA5 grid is 0.25 deg;
# [North, West, South, East]. Kept identical to the earlier per-month
# pulls so the two are directly comparable.
DOHA_BBOX = [25.5, 51.375, 25.0, 51.875]

# Variables needed by src.wbgt.wbgt_liljegren_c (+ what we derive):
#   2m_temperature                              -> air temp
#   2m_dewpoint_temperature                     -> relative humidity
#   surface_pressure                            -> pressure (Pa -> hPa)
#   10m_u/v_component_of_wind                   -> wind speed sqrt(u^2+v^2)
#   surface_solar_radiation_downwards (ssrd)    -> shortwave (J/m2 -> W/m2)
#   total_sky_direct_solar_radiation_at_surface -> direct beam (J/m2 -> W/m2)
# (cosine of solar zenith angle is computed in src/solar.py, not a CDS var.)
VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "surface_pressure",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "surface_solar_radiation_downwards",
    "total_sky_direct_solar_radiation_at_surface",
]

ALL_DAYS = [f"{d:02d}" for d in range(1, 32)]
ALL_HOURS = [f"{h:02d}:00" for h in range(24)]

QUARTERS = {"Q1": range(1, 4), "Q2": range(4, 7),
            "Q3": range(7, 10), "Q4": range(10, 13)}


def last_complete_month() -> tuple[int, int]:
    """(year, month) of the last month that has fully ended."""
    today = dt.date.today()
    first_of_this_month = today.replace(day=1)
    prev = first_of_this_month - dt.timedelta(days=1)
    return prev.year, prev.month


def periods(start_year: int, end_year: int):
    """Yield (year, 'Q1'..'Q4', ['01',...]) for every quarter whose months
    are all complete."""
    ley, lem = last_complete_month()
    for y in range(start_year, end_year + 1):
        for q, months in QUARTERS.items():
            ms = [m for m in months if (y, m) <= (ley, lem)]
            if ms:
                yield y, q, [f"{m:02d}" for m in ms]


def fetch_period(client, year, q, months, out_path: pathlib.Path):
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"  {year}-{q}: exists, skip", file=sys.stderr)
        return
    print(f"  {year}-{q} (months {months[0]}..{months[-1]}) -> {out_path.name}",
          file=sys.stderr)
    client.retrieve(
        DATASET,
        {
            "product_type": ["reanalysis"],
            "variable": VARIABLES,
            "year": [str(year)],
            "month": months,
            "day": ALL_DAYS,          # CDS ignores non-existent days
            "time": ALL_HOURS,
            "area": DOHA_BBOX,
            "data_format": "netcdf",
            "download_format": "unarchived",
        },
        str(out_path),
    )
    time.sleep(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2010)
    ap.add_argument("--end-year", type=int, default=2026)
    ap.add_argument("--outdir", default="data/era5")
    args = ap.parse_args()

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    client = cdsapi.Client()
    for year, q, months in periods(args.start_year, args.end_year):
        out = outdir / f"era5_doha_{year}_{q}.nc"
        try:
            fetch_period(client, year, q, months, out)
        except Exception as e:                       # noqa: BLE001
            print(f"  {year}-{q}: FAILED ({e}); re-run to resume",
                  file=sys.stderr)
    print("Done. Next: python scripts/era5_to_csv.py", file=sys.stderr)
