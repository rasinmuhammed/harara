"""
Fetch historical hourly weather for Doha from Open-Meteo's free archive API.

No API key required. Use this to get the pipeline running end-to-end
TODAY, before you've set up ERA5/Copernicus credentials (see
fetch_era5.py for that, once you have a CDS API key).

Note: Open-Meteo's historical archive is itself a reanalysis-blended
product, not raw station observations. Treat it as a convenient
bootstrap data source for pipeline development, not as the final
ground-truth source for your benchmark, that should be OTHH station
observations (see fetch_metar_othh.py) plus ERA5.

Usage:
    python scripts/fetch_open_meteo.py --start 2015-01-01 --end 2024-12-31 --out data/doha_openmeteo_hourly.csv
"""

import argparse
import sys
import time
import pandas as pd
import requests

DOHA_LAT = 25.27
DOHA_LON = 51.61

HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_speed_10m",
    "direct_radiation",
    "shortwave_radiation",
]

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_chunk(start: str, end: str) -> pd.DataFrame:
    params = {
        "latitude": DOHA_LAT,
        "longitude": DOHA_LON,
        "start_date": start,
        "end_date": end,
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC",
        # Return wind in m/s so downstream code never has to guess the unit
        # (Open-Meteo's default is km/h).
        "wind_speed_unit": "ms",
    }
    resp = requests.get(BASE_URL, params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    df = pd.DataFrame(payload["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    return df


def fetch_range(start: str, end: str, chunk_days: int = 365) -> pd.DataFrame:
    """Open-Meteo handles multi-year ranges fine in one call in practice,
    but chunking keeps individual requests small and resumable if a
    single request fails partway through a long backfill."""
    dates = pd.date_range(start, end, freq=f"{chunk_days}D")
    if dates[-1] < pd.Timestamp(end):
        dates = dates.append(pd.DatetimeIndex([pd.Timestamp(end)]))

    chunks = []
    for i in range(len(dates) - 1):
        s = dates[i].strftime("%Y-%m-%d")
        e = (dates[i + 1] - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"Fetching {s} to {e}...", file=sys.stderr)
        chunks.append(fetch_chunk(s, e))
        time.sleep(1)  # be polite to the free API
    return pd.concat(chunks, ignore_index=True).drop_duplicates(subset="time")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--out", default="data/doha_openmeteo_hourly.csv")
    args = ap.parse_args()

    df = fetch_range(args.start, args.end)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}", file=sys.stderr)
