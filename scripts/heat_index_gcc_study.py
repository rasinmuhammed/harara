"""
scripts/heat_index_gcc_study.py

First step of the multi-jurisdiction GCC comparison: run Dubai's heat
index (src.heat_index, the NWS Rothfusz regression) over the SAME 16-year
Doha record already used for every WBGT figure in this project, and
compare it against WBGT (src.wbgt, Qatar's legal standard). No new data
is fetched -- this is the "apply the methodology to Qatar first" step
before any second city's weather archive is pulled.

The two indices measure different things (WBGT includes wind and solar
radiant load; heat index does not), so this is not a validation of one
against the other -- it is a characterisation of how much they diverge
on the same real weather, which is itself the point: a contractor
operating under Dubai's index instead of Qatar's would be making a
materially different judgement on many of the same afternoons.

Run:  python scripts/heat_index_gcc_study.py
Out:  data/heat_index_gcc_study.json + a printed summary.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.heat_index import heat_index_c
from src.solar import cos_solar_zenith_angle
from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C, wbgt_liljegren_c

DATA = REPO / "data" / "doha_weather_16yr_patched.csv"
OUT = REPO / "data" / "heat_index_gcc_study.json"
DOHA_LAT, DOHA_LON = 25.27, 51.61
TZ = "Asia/Qatar"

# Dubai's enforced rule is the GCC calendar midday ban, not a published
# heat-index numeric threshold -- there is no official "stop work" heat
# index value to compare against, unlike Qatar's WBGT 32.1 C. For a rough
# hazard-band comparator only, NWS's own "danger" category (41 C / 105 F)
# is used here, clearly labelled as a US screening category, not a Dubai
# legal threshold.
NWS_DANGER_C = 41.0


def main() -> None:
    df = pd.read_csv(DATA)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    local = df["time"].dt.tz_convert(TZ)

    cz = cos_solar_zenith_angle(pd.DatetimeIndex(df["time"]), DOHA_LAT, DOHA_LON)
    wbgt = wbgt_liljegren_c(
        temp_c=df["temperature_2m"].to_numpy(),
        rh_pct=df["relative_humidity_2m"].to_numpy(),
        pressure_hpa=df["surface_pressure"].to_numpy(),
        wind_speed_10m_ms=df["wind_speed_10m"].to_numpy(),
        shortwave_wm2=df["shortwave_radiation"].fillna(0.0).to_numpy(),
        direct_wm2=df["direct_radiation"].fillna(0.0).to_numpy(),
        cos_zenith=cz,
    )
    hi = heat_index_c(
        temp_c=df["temperature_2m"].to_numpy(),
        rh_pct=df["relative_humidity_2m"].to_numpy(),
    )

    ok = np.isfinite(wbgt) & np.isfinite(hi)
    daylight = cz > 0.05
    # restrict to the regulated midday window each summer day, the only
    # hours the calendar ban / WBGT stoppage actually governs
    midday = local.dt.hour.between(10, 15) & local.dt.month.isin([6, 7, 8, 9])
    m = ok & midday.to_numpy()

    corr = float(np.corrcoef(wbgt[m], hi[m])[0, 1])
    diff = hi[m] - wbgt[m]

    wbgt_stop = wbgt[m] > QATAR_WBGT_STOP_WORK_THRESHOLD_C
    hi_danger = hi[m] > NWS_DANGER_C
    agree = wbgt_stop == hi_danger
    only_wbgt = wbgt_stop & ~hi_danger
    only_hi = hi_danger & ~wbgt_stop

    report = {
        "note": "Same Doha 16-year record used throughout this project. "
                "Heat index and WBGT measure different things (no wind/"
                "radiation term in heat index) -- this compares them on "
                "identical real weather, it does not validate either.",
        "n_hours_midday_summer": int(m.sum()),
        "pearson_r": corr,
        "diff_c": {
            "mean": float(np.mean(diff)), "std": float(np.std(diff)),
            "p10": float(np.percentile(diff, 10)),
            "p90": float(np.percentile(diff, 90)),
        },
        "exceedance_agreement": {
            "wbgt_threshold_c": QATAR_WBGT_STOP_WORK_THRESHOLD_C,
            "heat_index_danger_threshold_c": NWS_DANGER_C,
            "pct_hours_agree": float(np.mean(agree) * 100),
            "pct_hours_wbgt_only": float(np.mean(only_wbgt) * 100),
            "pct_hours_heat_index_only": float(np.mean(only_hi) * 100),
        },
    }
    OUT.write_text(json.dumps(report, indent=2))

    print(f"midday (10-15h), Jun-Sep, {report['n_hours_midday_summer']} hours\n")
    print(f"  correlation (Pearson r): {corr:.3f}")
    print(f"  heat index minus WBGT: mean {report['diff_c']['mean']:+.2f} C, "
          f"std {report['diff_c']['std']:.2f} C, "
          f"p10..p90 [{report['diff_c']['p10']:+.2f}, {report['diff_c']['p90']:+.2f}]")
    print(f"\n  stop-work flag agreement (WBGT>{QATAR_WBGT_STOP_WORK_THRESHOLD_C} C vs "
          f"heat index>{NWS_DANGER_C} C, illustrative only -- Dubai's actual rule is "
          f"the calendar ban, not this threshold):")
    print(f"    agree:              {report['exceedance_agreement']['pct_hours_agree']:.1f}%")
    print(f"    WBGT flags, HI does not:  {report['exceedance_agreement']['pct_hours_wbgt_only']:.1f}%")
    print(f"    HI flags, WBGT does not:  {report['exceedance_agreement']['pct_hours_heat_index_only']:.1f}%")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
