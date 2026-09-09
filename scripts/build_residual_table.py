"""
Distil the forecast archive into a small residual-quantile table the API can
ship. For each forecast lead (1, 2, 3 days) and each local working hour, the
p05/p10/p50/p90/p95 of (observed WBGT minus forecast WBGT), over warm-season
daylight hours.

The API widens its point forecast into a p10 to p90 band with this table, so
the site can show which hours are borderline across plausible forecasts
without shipping the multi-gigabyte archive. The plan itself stays on the
point forecast (technical_report section 15).

    python scripts/build_residual_table.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.forecast_wbgt import wbgt_from_forecast_frame

ARCHIVE = REPO / "data" / "doha_forecast_archive.csv"
TRUTH = REPO / "data" / "doha_wbgt_16yr.csv"
OUT = REPO / "api" / "data" / "wbgt_residuals.json"

DOHA_LAT, DOHA_LON = 25.27, 51.61
TZ = "Asia/Qatar"
WARM_MONTHS = (5, 6, 7, 8, 9)
HOURS = list(range(5, 19))
LEADS = (1, 2, 3)
QUANTILES = {"p05": 5, "p10": 10, "p50": 50, "p90": 90, "p95": 95}


def _forecast_wbgt(a: pd.DataFrame, lead: int) -> pd.Series:
    ren = {f"{v}_fc{lead}": v for v in
           ("temperature_2m", "relative_humidity_2m", "wind_speed_10m",
            "shortwave_radiation", "direct_radiation", "surface_pressure")}
    have = [c for c in ren if c in a.columns]
    frame = a[["time", *have]].rename(columns=ren).dropna(
        subset=["temperature_2m", "relative_humidity_2m", "wind_speed_10m",
                "shortwave_radiation", "surface_pressure"])
    if frame.empty:
        return pd.Series(dtype=float)
    w = np.asarray(wbgt_from_forecast_frame(frame, DOHA_LAT, DOHA_LON))
    return pd.Series(w, index=frame["time"].to_numpy())


def main() -> None:
    a = pd.read_csv(ARCHIVE)
    a["time"] = pd.to_datetime(a["time"], utc=True)
    t = pd.read_csv(TRUTH, usecols=["time", "wbgt_c"])
    t["time"] = pd.to_datetime(t["time"], utc=True)
    truth = t.set_index("time")["wbgt_c"]

    table: dict = {"leads": {}, "n": {}}
    for lead in LEADS:
        fc = _forecast_wbgt(a, lead)
        if fc.empty:
            print(f"lead {lead}: no forecast columns, skipped", file=sys.stderr)
            continue
        df = pd.DataFrame({"fc": fc})
        df["truth"] = truth.reindex(df.index)
        df = df.dropna()
        df["resid"] = df["truth"] - df["fc"]
        loc = pd.DatetimeIndex(df.index).tz_convert(TZ)
        df = df[np.isin(loc.month, WARM_MONTHS) & np.isin(loc.hour, HOURS)]
        df["lh"] = pd.DatetimeIndex(df.index).tz_convert(TZ).hour

        per_hour, per_hour_n = {}, {}
        for h in HOURS:
            r = df.loc[df["lh"] == h, "resid"].to_numpy()
            if len(r) < 20:
                continue
            per_hour[str(h)] = {k: round(float(np.percentile(r, p)), 2)
                                for k, p in QUANTILES.items()}
            per_hour_n[str(h)] = int(len(r))
        table["leads"][str(lead)] = per_hour
        table["n"][str(lead)] = per_hour_n
        span = df.index.min(), df.index.max()
        print(f"lead {lead}: {len(df)} hourly residuals, "
              f"{span[0].date()}..{span[1].date()}, "
              f"{len(per_hour)}/{len(HOURS)} hours covered", file=sys.stderr)

    table["meta"] = {
        "source": "doha_forecast_archive.csv vs doha_wbgt_16yr.csv",
        "quantity": "observed WBGT minus forecast WBGT, deg C",
        "window": "May to September, local hours 05:00 to 18:00",
        "note": ("Forecast RH and wind begin in 2024, so the residuals rest "
                 "on about 1.5 warm seasons."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(table, indent=2) + "\n")
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
