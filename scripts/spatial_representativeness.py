"""
scripts/spatial_representativeness.py

How wrong is ONE WBGT forecast for a whole metro area? We pull the
reanalysis archive at a coast->inland transect across greater Doha plus
the main labour locations, compute Liljegren WBGT at each, and measure how
far each point departs from the coastal/airport reference that a single
"Doha forecast" effectively represents.

Key outputs, over daylight outdoor hours (06-18 local, Apr-Oct):
  - mean and p95 of (WBGT_site - WBGT_reference)
  - % of hours the ACGIH work/rest band (moderate work, acclimatized)
    differs from the reference
  - % of hours a site is STOP-WORK while the reference is not
    (the dangerous representativeness error)

Resolution note: the archive (ERA5 / ERA5-Land, ~9-31 km) resolves the
coast-inland gradient but NOT block-scale microclimate. So this is a
LOWER bound on site-representativeness error; closing the rest needs local
sensing - i.e. the pilot.

Run:  python scripts/spatial_representativeness.py
"""

import pathlib
import sys
import time

import numpy as np
import pandas as pd
import requests

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.heat_stress import allowable_work_fraction, stop_work
from src.solar import cos_solar_zenith_angle
from src.wbgt import wbgt_liljegren_c

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
START, END = "2015-01-01", "2026-08-31"
CACHE = REPO / "data" / "spatial"

# name, lat, lon, kind. Reference first.
POINTS = [
    ("airport_OTHH",     25.27, 51.61, "coastal-ref"),
    ("westbay_coast",     25.32, 51.53, "coastal"),
    ("doha_center",       25.28, 51.52, "urban"),
    ("al_wakrah_coast",   25.17, 51.60, "coastal-south"),
    ("industrial_area",   25.19, 51.44, "inland-labour"),
    ("al_rayyan",         25.29, 51.42, "inland"),
    ("inland_30km",       25.28, 51.30, "desert"),
    ("inland_55km",       25.28, 51.10, "deep-desert"),
    ("mesaieed_industry", 24.99, 51.55, "south-industry"),
]

HOURLY = ["temperature_2m", "relative_humidity_2m", "surface_pressure",
          "wind_speed_10m", "shortwave_radiation", "direct_radiation"]


def fetch_point(name, lat, lon) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    fp = CACHE / f"{name}.csv"
    if fp.exists():
        df = pd.read_csv(fp)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        return df
    params = {
        "latitude": lat, "longitude": lon, "start_date": START, "end_date": END,
        "hourly": ",".join(HOURLY), "timezone": "UTC", "wind_speed_unit": "ms",
    }
    for attempt in range(8):
        print(f"  fetching {name} ({lat},{lon})  [try {attempt+1}]", file=sys.stderr)
        r = requests.get(ARCHIVE_URL, params=params, timeout=180)
        if r.status_code == 429:
            wait = 30 * (attempt + 1)
            print(f"    429 rate-limited; sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        r.raise_for_status()
        df = pd.DataFrame(r.json()["hourly"])
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df.to_csv(fp, index=False)
        time.sleep(20)                       # stay under the free-tier rate cap
        return df
    raise SystemExit(f"gave up on {name} after repeated 429s")


def wbgt_series(df: pd.DataFrame) -> np.ndarray:
    cz = cos_solar_zenith_angle(pd.DatetimeIndex(df["time"]), 25.27, 51.5)
    return wbgt_liljegren_c(
        temp_c=df["temperature_2m"].to_numpy(),
        rh_pct=df["relative_humidity_2m"].to_numpy(),
        pressure_hpa=df["surface_pressure"].to_numpy(),
        wind_speed_10m_ms=df["wind_speed_10m"].to_numpy(),
        shortwave_wm2=np.nan_to_num(df["shortwave_radiation"].to_numpy()),
        direct_wm2=np.nan_to_num(df["direct_radiation"].to_numpy()),
        cos_zenith=cz,
    )


def main():
    wb = {}
    for name, lat, lon, _ in POINTS:
        d = fetch_point(name, lat, lon)
        d = d.set_index("time")
        wb[name] = pd.Series(wbgt_series(d.reset_index()), index=d.index, name=name)

    W = pd.DataFrame(wb).dropna()
    local = W.index.tz_convert("Asia/Qatar")
    hod = local.hour + local.minute / 60.0
    day = (hod >= 6) & (hod < 18) & np.isin(local.month, [4, 5, 6, 7, 8, 9, 10])
    Wd = W.loc[day]
    ref = Wd["airport_OTHH"]

    print(f"Daylight outdoor hours compared: {len(Wd):,}\n")

    # --- afternoon gradient snapshot ---
    aft = Wd.loc[(hod[day] >= 12) & (hod[day] < 16)
                 & np.isin(local[day].month, [6, 7, 8, 9])]
    print("Summer (Jun-Sep) 12-16 local, mean WBGT and delta vs airport:")
    print(f"  {'site':<20}{'kind':<16}{'meanWBGT':>10}{'Δ vs ref':>10}")
    for name, lat, lon, kind in POINTS:
        m = aft[name].mean()
        print(f"  {name:<20}{kind:<16}{m:10.1f}{m - aft['airport_OTHH'].mean():+10.1f}")
    print()

    # --- representativeness error over all daylight-season hours ---
    print("Site vs airport reference, daylight outdoor hours (Apr-Oct):")
    print(f"  {'site':<20}{'meanΔ':>8}{'p95Δ':>8}{'band≠ref':>10}{'STOP&refOK':>12}")
    ref_band = allowable_work_fraction(ref.to_numpy(), "moderate", True)
    ref_stop = stop_work(ref.to_numpy(), "moderate", True)
    for name, lat, lon, kind in POINTS:
        if name == "airport_OTHH":
            continue
        delta = Wd[name].to_numpy() - ref.to_numpy()
        band = allowable_work_fraction(Wd[name].to_numpy(), "moderate", True)
        stp = stop_work(Wd[name].to_numpy(), "moderate", True)
        band_diff = np.mean(band != ref_band) * 100
        stop_gap = np.mean(stp & ~ref_stop) * 100
        print(f"  {name:<20}{delta.mean():+8.1f}{np.percentile(delta,95):+8.1f}"
              f"{band_diff:9.1f}%{stop_gap:11.1f}%")
    print()

    worst = "inland_55km"
    d = Wd[worst].to_numpy() - ref.to_numpy()
    sg = np.mean(stop_work(Wd[worst].to_numpy(), "moderate", True) & ~ref_stop) * 100
    ind = "industrial_area"
    di = Wd[ind].to_numpy() - ref.to_numpy()
    sgi = np.mean(stop_work(Wd[ind].to_numpy(), "moderate", True) & ~ref_stop) * 100
    print("Headline:")
    print(f"  - A worker at the Industrial Area sees WBGT on average "
          f"{di.mean():+.1f} C vs the airport-equivalent forecast, up to "
          f"{np.percentile(di,95):+.1f} C at the 95th pct.")
    print(f"  - {sgi:.0f}% of daylight-season hours, the Industrial Area is "
          f"STOP-WORK (moderate/acclimatized) while the reference says work "
          f"is allowed.")
    print(f"  - Deep desert ({worst}): mean {d.mean():+.1f} C, "
          f"stop-vs-ref-ok {sg:.0f}% of hours.")
    print(f"  - This is the coast-inland gradient only (~10 km scale). "
          f"Block-scale error is on top and needs local sensing.")


if __name__ == "__main__":
    main()
