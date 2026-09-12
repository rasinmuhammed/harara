"""
Distil the 16-year Doha WBGT record into the small table api/planning.py
needs for climatology_compare and heat_trend, and ship it under api/data/
alongside wbgt_residuals.json and replay/.

Bug this fixes: api/planning.py used to read data/doha_wbgt_16yr.csv (14 MB,
146,000 hourly rows) directly at the repo's top-level data/ directory. That
directory is gitignored and excluded by .dockerignore, so it is never in the
build context of either Dockerfile - the file simply is not there in a
deployed container. climatology_compare and heat_trend (and the
/api/climatology, /api/heat-trend endpoints, and the chat's answers about
whether heat is increasing) would raise FileNotFoundError in production. It
was not caught locally because tests run against the file on disk.

The fix is the same one already used for the forecast-residual table and the
replay weeks: distil what the API actually needs into a small file that
lives in api/data/, which both Dockerfiles do COPY and which git does track
(data/** in .gitignore is anchored to the repo root and does not match the
nested api/data/ directory).

What's needed, and no more:
  - daily_peaks: one row per day (date, day-of-year, year, peak WBGT over
    05:00-19:00 local) - climatology_compare bins these by day-of-year.
  - annual_stop_work_hours: warm-season (Jun-Sep, 06:00-18:00 local) hour
    count with WBGT over the stop-work threshold, one number per year -
    heat_trend's whole input.
  - last_date: the record's last day, so heat_trend can drop a partial
    final year the same way it always has.

    python scripts/build_climatology_table.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C

TRUTH = REPO / "data" / "doha_wbgt_16yr.csv"
OUT = REPO / "api" / "data" / "climatology.json"
TZ = "Asia/Qatar"
THRESHOLD_C = QATAR_WBGT_STOP_WORK_THRESHOLD_C


def main() -> None:
    df = pd.read_csv(TRUTH, usecols=["time", "wbgt_c"])
    t = pd.to_datetime(df["time"], utc=True).dt.tz_convert(TZ)
    df["date"] = t.dt.date
    df["hour"] = t.dt.hour
    df["doy"] = t.dt.dayofyear
    df["year"] = t.dt.year
    df["month"] = t.dt.month

    daylight = df[df["hour"].between(5, 19)]
    daily = (daylight.groupby("date")
             .agg(peak_wbgt_c=("wbgt_c", "max"), doy=("doy", "first"),
                  year=("year", "first"))
             .reset_index())
    daily_peaks = [
        {"date": row.date.isoformat(), "doy": int(row.doy), "year": int(row.year),
         "peak_wbgt_c": round(float(row.peak_wbgt_c), 2)}
        for row in daily.itertuples()
    ]

    warm = df[(df["month"].between(6, 9)) & (df["hour"].between(6, 18))]
    per_year = (warm.assign(over=warm["wbgt_c"] > THRESHOLD_C)
                .groupby("year")["over"].sum().sort_index())
    annual_stop_work_hours = {str(int(y)): int(v) for y, v in per_year.items()}

    out = {
        "source": "data/doha_wbgt_16yr.csv via scripts/build_climatology_table.py",
        "daily_peaks": daily_peaks,
        "annual_stop_work_hours": annual_stop_work_hours,
        "last_date": max(df["date"]).isoformat(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out))
    print(f"{len(daily_peaks)} daily peaks, {len(annual_stop_work_hours)} years "
          f"-> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
