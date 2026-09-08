"""
Fetch Open-Meteo's HISTORICAL FORECAST archive for Doha: for every past
hour, both the analysis (best estimate of what happened) and what the
model runs from 1 / 2 / 3 days earlier had FORECAST for that hour.

This is the input for true Layer-1 bias-correction: we compare
forecast-derived WBGT at a given lead against WBGT truth and learn the
systematic error.

Archive starts 2022-01-01. Different product from the reanalysis archive
(fetch_open_meteo.py); its analysis matches ours to <0.1 C, verified.

Output columns:
    time,
    <var>            analysis
    <var>_fc1/2/3    forecast issued ~24/48/72 h before this hour
  for var in {temperature_2m, relative_humidity_2m, wind_speed_10m,
              shortwave_radiation, direct_radiation, surface_pressure}

Usage:
    python scripts/fetch_openmeteo_forecast_archive.py \
        --start 2022-01-01 --end 2026-08-31 --out data/doha_forecast_archive.csv
"""

import argparse
import sys
import time

import pandas as pd
import requests

DOHA_LAT, DOHA_LON = 25.27, 51.61
BASE_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

BASE_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "shortwave_radiation",
    "direct_radiation",
    "surface_pressure",
]
LEADS = (1, 2, 3)


def all_hourly_vars() -> list[str]:
    out = []
    for v in BASE_VARS:
        out.append(v)
        out += [f"{v}_previous_day{n}" for n in LEADS]
    return out


def fetch_chunk(start: str, end: str) -> pd.DataFrame:
    params = {
        "latitude": DOHA_LAT, "longitude": DOHA_LON,
        "start_date": start, "end_date": end,
        "hourly": ",".join(all_hourly_vars()),
        "timezone": "UTC", "wind_speed_unit": "ms",
    }
    r = requests.get(BASE_URL, params=params, timeout=120)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise SystemExit(f"API error: {j.get('reason', j)}")
    df = pd.DataFrame(j["hourly"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    # shorten _previous_dayN -> _fcN
    ren = {f"{v}_previous_day{n}": f"{v}_fc{n}"
           for v in BASE_VARS for n in LEADS}
    return df.rename(columns=ren)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2026-08-31")
    ap.add_argument("--out", default="data/doha_forecast_archive.csv")
    args = ap.parse_args()

    # yearly chunks: resumable, and keeps each response modest
    edges = pd.date_range(args.start, args.end, freq="YS").tolist()
    edges = [pd.Timestamp(args.start)] + [e for e in edges if pd.Timestamp(args.start) < e] \
            + [pd.Timestamp(args.end) + pd.Timedelta(days=1)]
    edges = sorted(set(edges))

    parts = []
    for a, b in zip(edges[:-1], edges[1:]):
        s = a.strftime("%Y-%m-%d")
        e = (b - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"fetching {s} .. {e}", file=sys.stderr)
        parts.append(fetch_chunk(s, e))
        time.sleep(1)

    df = (pd.concat(parts, ignore_index=True)
            .drop_duplicates(subset="time")
            .sort_values("time")
            .reset_index(drop=True))

    # how complete are the forecast columns?
    for n in LEADS:
        col = f"temperature_2m_fc{n}"
        frac = df[col].notna().mean() * 100
        print(f"  fc{n} coverage: {frac:5.1f}%  "
              f"(first non-null {df.loc[df[col].notna(), 'time'].min()})",
              file=sys.stderr)

    df.to_csv(args.out, index=False)
    print(f"wrote {len(df)} rows ({df['time'].min()} .. {df['time'].max()}) "
          f"-> {args.out}", file=sys.stderr)
