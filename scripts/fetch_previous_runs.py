"""
Fetch archived past model runs for the Doha grid point from Open-Meteo's
Previous Runs API (https://open-meteo.com/en/docs/previous-runs-api).

For every past valid hour the API can return the value as it stood in the
model run from N days earlier, via the `<var>_previous_dayN` fields. That
is a forecast at a nominal lead of N x 24 h (the underlying run is
0.75-1.75 x 24 h old depending on valid hour and the 00Z cadence -- the
same convention as scripts/fetch_openmeteo_forecast_archive.py and
technical_report Section 5.1).

This is the input for the AI-weather-model humid-heat study
(docs/aiwp_plan.md): does AIFS / GraphCast / IFS / GFS under-forecast Gulf
WBGT extremes, and at what lead.

Models and fields (probed 2026-09-09; windows are where the full set
returns non-null):

    ecmwf_ifs025          physics NWP reference   T RH wind SW direct P
                          full set from 2024-03-05
    ecmwf_aifs025_single  ECMWF AI (deterministic) T RH wind SW direct P
                          full set from 2025-02-26  (~1.5 warm seasons)
    gfs_graphcast025      NOAA GraphCast (AI)      T and cloud_cover ONLY
                          ~2024-09 .. ~2025-09, with production gaps
    gfs_seamless          NOAA GFS reference       T RH wind SW direct P
                          full set from 2024-02-11

GraphCast on the public feed carries no humidity/wind/radiation, so it
cannot yield a WBGT forecast; it is fetched for the 2 m-temperature track
only.

Output: one tidy CSV per (model, lead) under data/previous_runs/ --
    <model>__lead{N}d.csv
with columns time + the forecast fields that model serves. A file that
already spans the requested range is skipped; --refresh forces a refetch.

Usage:
    python scripts/fetch_previous_runs.py --start 2024-01-01 --end 2026-08-30
    python scripts/fetch_previous_runs.py --models ecmwf_aifs025_single --refresh
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

import pandas as pd
import requests

DOHA_LAT, DOHA_LON = 25.27, 51.61
BASE_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
LEADS = (1, 2, 3, 4, 5, 6, 7)

FULL_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "shortwave_radiation",
    "direct_radiation",
    "surface_pressure",
]

# base vars each model actually serves on the previous-runs feed
MODELS: dict[str, list[str]] = {
    "ecmwf_ifs025": FULL_VARS,
    "ecmwf_aifs025_single": FULL_VARS,
    "gfs_seamless": FULL_VARS,
    "gfs_graphcast025": ["temperature_2m", "cloud_cover"],
}

OUTDIR = pathlib.Path("data/previous_runs")


def _lead_fields(base_vars: list[str]) -> list[str]:
    return [f"{v}_previous_day{n}" for v in base_vars for n in LEADS]


def fetch_chunk(model: str, base_vars: list[str], start: str, end: str,
                timeout: int = 120) -> pd.DataFrame:
    params = {
        "latitude": DOHA_LAT, "longitude": DOHA_LON,
        "start_date": start, "end_date": end,
        "hourly": ",".join(_lead_fields(base_vars)),
        "models": model,
        "timezone": "UTC", "wind_speed_unit": "ms",
    }
    r = requests.get(BASE_URL, params=params, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise SystemExit(f"{model}: API error: {j.get('reason', j)}")
    df = pd.DataFrame(j["hourly"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def fetch_model(model: str, base_vars: list[str], start: str, end: str
                ) -> pd.DataFrame:
    """One wide frame for the model, all leads, over yearly chunks."""
    edges = pd.date_range(start, end, freq="YS").tolist()
    edges = ([pd.Timestamp(start)]
             + [e for e in edges if pd.Timestamp(start) < e < pd.Timestamp(end)]
             + [pd.Timestamp(end) + pd.Timedelta(days=1)])
    edges = sorted(set(edges))

    parts = []
    for a, b in zip(edges[:-1], edges[1:]):
        s = a.strftime("%Y-%m-%d")
        e = (b - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"  {model}: {s} .. {e}", file=sys.stderr)
        parts.append(fetch_chunk(model, base_vars, s, e))
        time.sleep(1)

    return (pd.concat(parts, ignore_index=True)
              .drop_duplicates(subset="time")
              .sort_values("time")
              .reset_index(drop=True))


def split_to_lead_files(model: str, base_vars: list[str], wide: pd.DataFrame,
                        outdir: pathlib.Path) -> None:
    for n in LEADS:
        cols = {f"{v}_previous_day{n}": v for v in base_vars}
        have = [c for c in cols if c in wide.columns]
        if not have:
            continue
        sub = wide[["time", *have]].rename(columns=cols)
        out = outdir / f"{model}__lead{n}d.csv"
        sub.to_csv(out, index=False)
        nn = int(sub[base_vars[0]].notna().sum())
        first = sub.loc[sub[base_vars[0]].notna(), "time"].min()
        last = sub.loc[sub[base_vars[0]].notna(), "time"].max()
        print(f"    lead {n}d -> {out.name}  ({nn} non-null rows, "
              f"{first} .. {last})", file=sys.stderr)


def already_done(model: str, start: str, end: str, outdir: pathlib.Path) -> bool:
    """True if every lead file for this model exists and reaches the end of
    the requested range (values may be NaN where the model has no coverage;
    what we check is that the hourly index was fetched)."""
    end_ts = pd.Timestamp(end, tz="UTC")
    for n in LEADS:
        p = outdir / f"{model}__lead{n}d.csv"
        if not p.exists():
            return False
        try:
            tmax = pd.to_datetime(pd.read_csv(p, usecols=["time"])["time"],
                                  utc=True).max()
        except Exception:
            return False
        if pd.isna(tmax) or tmax < end_ts - pd.Timedelta(days=2):
            return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-08-30")
    ap.add_argument("--models", nargs="*", default=list(MODELS),
                    choices=list(MODELS))
    ap.add_argument("--outdir", type=pathlib.Path, default=OUTDIR)
    ap.add_argument("--refresh", action="store_true",
                    help="refetch even if lead files already span the range")
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    for model in args.models:
        base_vars = MODELS[model]
        if not args.refresh and already_done(model, args.start, args.end,
                                             args.outdir):
            print(f"{model}: lead files present and current, skip",
                  file=sys.stderr)
            continue
        print(f"{model}: fetching {args.start} .. {args.end}", file=sys.stderr)
        wide = fetch_model(model, base_vars, args.start, args.end)
        split_to_lead_files(model, base_vars, wide, args.outdir)

    print("done -> " + str(args.outdir), file=sys.stderr)


if __name__ == "__main__":
    main()
