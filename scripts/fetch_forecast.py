"""
Command-line wrapper around src.open_meteo.fetch_forecast: an hourly weather
forecast from the Open-Meteo forecast API (no key, up to 16 days), in the same
variable set and units as scripts/fetch_open_meteo.py.

    python scripts/fetch_forecast.py --lat 25.27 --lon 51.61 \
        --start 2026-09-10 --end 2026-09-12 --out data/doha_forecast.csv

The fetch function itself lives in src/ because the API depends on it at
runtime.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.open_meteo import BASE_URL, HOURLY_VARS, fetch_forecast  # noqa: F401,E402


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
