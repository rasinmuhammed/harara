"""
Fetch an hourly weather forecast from the Open-Meteo forecast API (no key
required, up to 16 days). Same variable set and units as
scripts/fetch_open_meteo.py so the WBGT code consumes it unchanged.

Used by src.agent.tools.get_forecast. Standalone:

    python scripts/fetch_forecast.py --lat 25.27 --lon 51.61 \
        --start 2026-09-10 --end 2026-09-12 --out data/doha_forecast.csv
"""

import argparse
import datetime as dt

import pandas as pd
import requests

BASE_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = [
    "temperature_2m", "relative_humidity_2m", "surface_pressure",
    "wind_speed_10m", "direct_radiation", "shortwave_radiation",
]


def fetch_forecast(lat: float, lon: float, start: dt.date, end: dt.date,
                   timeout: int = 60) -> pd.DataFrame:
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC", "wind_speed_unit": "ms",
    }
    r = requests.get(BASE_URL, params=params, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(j.get("reason", "open-meteo forecast error"))
    df = pd.DataFrame(j["hourly"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=25.27)
    ap.add_argument("--lon", type=float, default=51.61)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", default="data/doha_forecast.csv")
    args = ap.parse_args()
    df = fetch_forecast(args.lat, args.lon,
                        dt.date.fromisoformat(args.start),
                        dt.date.fromisoformat(args.end))
    df.to_csv(args.out, index=False)
    print(f"wrote {len(df)} rows -> {args.out}")
