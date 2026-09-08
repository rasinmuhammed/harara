"""
Fetch OTHH (Doha / Hamad International) hourly surface observations from the
Iowa Environmental Mesonet (IEM) ASOS/METAR archive.

This is station data - an actual anemometer, thermometer and
hygrometer at the airport - not a reanalysis. It is the ground-truth
check on the blended products (Open-Meteo, and later ERA5): if a trend
shows up in a reanalysis but not here, the reanalysis is suspect.

No account or API key required. IEM asks that you not hammer the service;
this script pulls one multi-year request per call.

Coverage note: OTHH (Hamad Int'l) METARs begin in 2014. Doha's older
airport was OTBD (closed 2014); pass --station OTBD for pre-2014 if needed.

Usage:
    python scripts/fetch_metar_othh.py --start 2014-01-01 --end 2026-08-31 \
        --out data/othh_metar_hourly.csv
"""

import argparse
import io
import sys

import pandas as pd
import requests

IEM_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"

# METAR fields we care about. sknt = sustained wind [knots], drct = wind
# direction [deg], gust [knots], tmpf/dwpf = temp/dewpoint [F], relh [%],
# mslp [hPa], vsby = visibility [statute miles], wxcodes = present-weather
# tokens (DU/BLDU/HZ/DS/SS/FU... -> dust, haze, dust/sand storm).
IEM_DATA = ["sknt", "drct", "gust", "tmpf", "dwpf", "relh", "mslp",
            "vsby", "wxcodes"]

KNOTS_TO_MS = 0.514444


def fetch(station: str, start: str, end: str) -> pd.DataFrame:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    params = {
        "station": station,
        "data": ",".join(IEM_DATA),
        "year1": s.year, "month1": s.month, "day1": s.day,
        "year2": e.year, "month2": e.month, "day2": e.day,
        "tz": "Etc/UTC",
        "format": "onlycomma",
        "missing": "empty",
        "trace": "0.0001",
        "latlon": "no",
        "elev": "no",
        "report_type": [3, 4],   # routine + special METARs
    }
    print(f"Requesting {station} {start}..{end} from IEM...", file=sys.stderr)
    r = requests.get(IEM_URL, params=params, timeout=300)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    if df.empty:
        raise SystemExit("IEM returned no rows - check station id / dates.")
    return df


def to_hourly(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={"valid": "time"})
    df["time"] = pd.to_datetime(df["time"], utc=True)

    for c in ["sknt", "drct", "gust", "tmpf", "dwpf", "relh", "mslp", "vsby"]:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")

    df["wind_speed_ms"] = df["sknt"] * KNOTS_TO_MS
    df["gust_ms"] = df["gust"] * KNOTS_TO_MS
    df["wind_dir_deg"] = df["drct"]
    df["temp_c"] = (df["tmpf"] - 32.0) * 5.0 / 9.0
    df["dewpoint_c"] = (df["dwpf"] - 32.0) * 5.0 / 9.0
    df["rh_pct"] = df["relh"]
    df["mslp_hpa"] = df["mslp"]
    df["visibility_km"] = df["vsby"] * 1.609344
    wx = df.get("wxcodes")
    df["wxcodes"] = wx.fillna("") if wx is not None else ""
    dust_tok = ("DU", "BLDU", "DS", "SS", "PO", "SA")
    df["is_dust"] = df["wxcodes"].str.contains("|".join(dust_tok), na=False)
    df["is_haze"] = df["wxcodes"].str.contains("HZ|FU", na=False)

    keep = ["time", "wind_speed_ms", "gust_ms", "wind_dir_deg", "temp_c",
            "dewpoint_c", "rh_pct", "mslp_hpa", "visibility_km",
            "wxcodes", "is_dust", "is_haze"]
    df = df[keep].dropna(subset=["time"])

    # METARs land at :00, :30, and off-schedule "special" reports. Collapse
    # to one row per clock hour: numeric/state fields from the ob closest to
    # the top of the hour; dust/haze flags are "any within the hour" and
    # visibility is the hour's minimum (a dust ob at :20 must not be hidden
    # by a clear ob at :00).
    df = df.sort_values("time")
    df["hour"] = df["time"].dt.floor("h")
    df["dist"] = (df["time"] - df["hour"]).abs()

    nearest = (df.sort_values("dist")
                 .groupby("hour", as_index=False)
                 .first()
                 .drop(columns=["time", "dist", "is_dust", "is_haze",
                                "visibility_km", "wxcodes"]))
    agg = df.groupby("hour", as_index=False).agg(
        is_dust=("is_dust", "max"),
        is_haze=("is_haze", "max"),
        visibility_km=("visibility_km", "min"),
        wxcodes=("wxcodes", lambda s: ";".join(sorted({x for x in s if x}))),
    )
    hourly = (nearest.merge(agg, on="hour")
                     .rename(columns={"hour": "time"})
                     .sort_values("time")
                     .reset_index(drop=True))
    return hourly


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--station", default="OTHH")
    ap.add_argument("--start", default="2014-01-01")
    ap.add_argument("--end", default="2026-08-31")
    ap.add_argument("--out", default="data/othh_metar_hourly.csv")
    args = ap.parse_args()

    raw = fetch(args.station, args.start, args.end)
    hourly = to_hourly(raw)
    hourly.to_csv(args.out, index=False)
    print(f"Wrote {len(hourly)} hourly rows "
          f"({hourly['time'].min()} .. {hourly['time'].max()}) to {args.out}",
          file=sys.stderr)
