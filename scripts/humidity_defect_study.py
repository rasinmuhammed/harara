"""
scripts/humidity_defect_study.py

A FOLLOW-ON to the ERA5 cross-check (era5_cross_check.py, technical_report.md
S5.7): that check found ERA5 and the working (Open-Meteo-patched) dataset
disagreeing on the section 4.1 exceedance-hour trend, traced to a humidity
divergence in specific years. This script asks the harder question the
cross-check could not answer on its own, because ERA5 is not ground truth
either: which side is METAR, the measured station, actually on?

METHOD
    Three independent series for the same Doha point and period:
      Open-Meteo (working dataset)  - the archive under test
      ERA5                          - a second reanalysis (era5_cross_check.py)
      METAR (OTHH)                  - the measured station, ground truth
    Dewpoint (not RH) is compared directly, because RH is a derived quantity
    and comparing it can hide whether a temperature or a moisture difference
    is responsible; dewpoint isolates the moisture signal.

FINDING (see the printed report and results JSON for exact numbers)
    Open-Meteo's June-August dewpoint runs WET relative to METAR in
    2014-2016, crosses over, and runs DRY relative to METAR in every year
    2018 through 2026 - a persistent, multi-year sign flip, not noise in a
    couple of years. ERA5 tracks METAR closely and consistently throughout,
    with no such flip. This is a second, previously undocumented Open-Meteo
    archive defect, structurally different from the November-2024 wind defect
    (compare_wind_sources.py): a gradual, seasonal humidity drift rather than
    a sharp step change, and present for about a decade rather than two years.

IMPACT ESTIMATE (not applied to data/doha_wbgt_16yr.csv - see the module
docstring's closing note)
    A METAR-humidity-corrected version of the working dataset is built here
    (substitute measured RH and temperature wherever METAR has them, same
    principle as patch_wind.py already applies to wind) and WBGT is
    recomputed through the identical Liljegren pipeline. The section 4.1
    trend (June-September, 06:00-18:00 local, WBGT > 32.1 C) is compared
    across all three: Open-Meteo (production), METAR-corrected, and ERA5.

CONSEQUENCE, IF CONFIRMED
    If the METAR-corrected trend sits closer to ERA5's steeper rise than to
    Open-Meteo's near-flat one, the section 4.1 "500 to 650-770 hours/year"
    claim is not overstated, as the ERA5 cross-check's cautious framing
    suggested - it is UNDERSTATED, because the working dataset has been
    quietly drying out (and therefore under-counting heat stress) for the
    back half of the record it is measured over.

THIS SCRIPT DOES NOT REWRITE data/doha_wbgt_16yr.csv OR ANY OTHER PRODUCTION
FILE. Repatching the humidity record the way patch_wind.py repatches wind
would change the input to nearly every quantitative result in the technical
report (sections 4 through 9), which is a substantial, separately-scoped
follow-up, not a side effect of a cross-check. This script quantifies the
size of that follow-up so it can be prioritised honestly.

Run:  python scripts/humidity_defect_study.py
Writes: data/humidity_defect_results.json
"""

from __future__ import annotations

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import numpy as np
import pandas as pd

from src.solar import cos_solar_zenith_angle
from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C, wbgt_liljegren_c

DATA = REPO / "data"
DOHA_LAT, DOHA_LON = 25.27, 51.61
THR = QATAR_WBGT_STOP_WORK_THRESHOLD_C
TZ = "Asia/Qatar"
MAX_GAP_H = 6            # same interpolation limit as patch_wind.py


def dewpoint_from_rh(t_c: np.ndarray, rh: np.ndarray) -> np.ndarray:
    """Magnus-formula dewpoint from temperature and relative humidity, the
    inverse of era5_to_csv.py's rh_from_dewpoint."""
    a, b = 17.625, 243.04
    gamma = np.log(np.clip(rh, 1e-6, 100.0) / 100.0) + (a * t_c) / (b + t_c)
    return b * gamma / (a - gamma)


def rh_from_dewpoint(t_c: np.ndarray, td_c: np.ndarray) -> np.ndarray:
    a, b = 17.625, 243.04
    e = np.exp(a * td_c / (b + td_c))
    es = np.exp(a * t_c / (b + t_c))
    return np.clip(100.0 * e / es, 0.0, 100.0)


def _load(path: pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.sort_values("time").reset_index(drop=True)


def add_wbgt(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["cos_zenith"] = cos_solar_zenith_angle(
        pd.DatetimeIndex(df["time"]), DOHA_LAT, DOHA_LON)
    df["wbgt_c"] = wbgt_liljegren_c(
        temp_c=df["temperature_2m"].to_numpy(),
        rh_pct=df["relative_humidity_2m"].to_numpy(),
        pressure_hpa=df["surface_pressure"].to_numpy(),
        wind_speed_10m_ms=df["wind_speed_10m"].to_numpy(),
        shortwave_wm2=df["shortwave_radiation"].fillna(0.0).to_numpy(),
        direct_wm2=df["direct_radiation"].fillna(0.0).to_numpy(),
        cos_zenith=df["cos_zenith"].to_numpy(),
    )
    return df


def dewpoint_triangulation(om: pd.DataFrame, era5: pd.DataFrame,
                           metar: pd.DataFrame) -> dict:
    """June-August mean dewpoint bias (product - METAR), by year, for
    Open-Meteo and ERA5. Dewpoint isolates the moisture signal from a
    temperature difference."""
    o = om[["time", "temperature_2m", "relative_humidity_2m"]].copy()
    o["td_om"] = dewpoint_from_rh(o["temperature_2m"].to_numpy(),
                                  o["relative_humidity_2m"].to_numpy())
    e = era5[["time", "temperature_2m", "relative_humidity_2m"]].copy()
    e["td_era5"] = dewpoint_from_rh(e["temperature_2m"].to_numpy(),
                                    e["relative_humidity_2m"].to_numpy())
    m = metar[["time", "dewpoint_c", "temp_c"]].rename(
        columns={"dewpoint_c": "td_metar", "temp_c": "t_metar"})

    df = (o[["time", "td_om"]]
          .merge(e[["time", "td_era5"]], on="time")
          .merge(m, on="time"))
    loc = df["time"].dt.tz_convert(TZ)
    df["year"], df["month"] = loc.dt.year, loc.dt.month
    jja = df[df["month"].isin([6, 7, 8])]

    by_year = {}
    for y, g in jja.groupby("year"):
        if len(g) < 400:
            continue
        by_year[int(y)] = {
            "n": int(len(g)),
            "td_om_minus_metar": round(float((g["td_om"] - g["td_metar"]).mean()), 2),
            "td_era5_minus_metar": round(float((g["td_era5"] - g["td_metar"]).mean()), 2),
        }
    early = np.mean([v["td_om_minus_metar"] for k, v in by_year.items() if k <= 2016])
    late = np.mean([v["td_om_minus_metar"] for k, v in by_year.items() if k >= 2018])
    era5_early = np.mean([v["td_era5_minus_metar"] for k, v in by_year.items() if k <= 2016])
    era5_late = np.mean([v["td_era5_minus_metar"] for k, v in by_year.items() if k >= 2018])
    return {
        "by_year_jja": by_year,
        "open_meteo_dewpoint_bias_2014_2016_mean": round(float(early), 2),
        "open_meteo_dewpoint_bias_2018_2026_mean": round(float(late), 2),
        "era5_dewpoint_bias_2014_2016_mean": round(float(era5_early), 2),
        "era5_dewpoint_bias_2018_2026_mean": round(float(era5_late), 2),
        "sign_flip": bool(early > 0 and late < 0),
        "era5_stable": bool(abs(era5_early) < 1.5 and abs(era5_late) < 1.5),
    }


def build_metar_corrected(om: pd.DataFrame, metar: pd.DataFrame) -> pd.DataFrame:
    """Open-Meteo with temperature and relative humidity replaced by measured
    METAR values wherever METAR has them (small gaps time-interpolated, same
    MAX_GAP_H rule as patch_wind.py), for the full record - not just the
    years the defect is visible in, for the same reason patch_wind.py patches
    wind everywhere it has METAR: prefer the measurement when you have it."""
    df = om.copy()
    mt = metar[["time", "temp_c", "dewpoint_c"]].rename(
        columns={"temp_c": "metar_t", "dewpoint_c": "metar_td"})
    df = df.merge(mt, on="time", how="left")

    t_filled = (df.set_index("time")["metar_t"]
                .interpolate(method="time", limit=MAX_GAP_H, limit_area="inside")
                .to_numpy())
    td_filled = (df.set_index("time")["metar_td"]
                 .interpolate(method="time", limit=MAX_GAP_H, limit_area="inside")
                 .to_numpy())

    have_t = pd.notna(t_filled)
    have_td = pd.notna(td_filled)
    new_t = df["temperature_2m"].to_numpy().copy()
    new_t[have_t] = t_filled[have_t]
    # RH must be recomputed from the (possibly newly patched) temperature and
    # the patched dewpoint together, so the pair stays thermodynamically
    # consistent rather than mixing an old T with a new Td or vice versa.
    new_rh = df["relative_humidity_2m"].to_numpy().copy()
    both = have_t & have_td
    new_rh[both] = rh_from_dewpoint(t_filled[both], td_filled[both])

    df["temperature_2m"] = new_t
    df["relative_humidity_2m"] = new_rh
    df["humidity_source"] = np.where(both, "metar", "openmeteo")
    return df.drop(columns=["metar_t", "metar_td"])


def trend(df_wbgt: pd.DataFrame, label: str) -> dict:
    d = df_wbgt[["time", "wbgt_c"]].copy()
    loc = d["time"].dt.tz_convert(TZ)
    d["month"], d["hour"], d["year"] = loc.dt.month, loc.dt.hour, loc.dt.year
    sel = d[(d["month"].between(6, 9)) & (d["hour"].between(6, 18))]
    per_year = sel.assign(over=sel["wbgt_c"] > THR).groupby("year")["over"].sum()
    if per_year.index[-1] == 2026:
        per_year = per_year.iloc[:-1]           # partial trailing year
    yrs = per_year.index.to_numpy(dtype=float)
    vals = per_year.to_numpy(dtype=float)
    slope = float(np.polyfit(yrs, vals, 1)[0]) if len(yrs) >= 3 else float("nan")

    # section 4.1's other headline: share of hours over 32.1 in the
    # regulated window (Jun-Sep, 10:00-15:00 local)
    reg = d[(d["month"].between(6, 9)) & (d["hour"].between(10, 15))]
    reg_rate = float((reg["wbgt_c"] > THR).mean() * 100)

    return {
        "label": label,
        "hours_per_year": {int(k): int(v) for k, v in per_year.items()},
        "early_2013_14_mean": round(float(per_year.reindex([2013, 2014]).mean()), 1),
        "recent_2021_25_mean": round(
            float(per_year.reindex(range(2021, 2026)).mean()), 1),
        "slope_hours_per_year": round(slope, 1),
        "regulated_window_exceedance_pct": round(reg_rate, 1),
    }


def main() -> None:
    print("Loading Open-Meteo (patched), ERA5, METAR ...", file=sys.stderr)
    om = _load(DATA / "doha_weather_16yr_patched.csv")
    era5 = _load(DATA / "doha_era5_hourly.csv")
    metar = _load(DATA / "othh_metar_hourly.csv")

    print("Triangulating dewpoint (moisture, not RH) against METAR ...",
          file=sys.stderr)
    tri = dewpoint_triangulation(om, era5, metar)

    print("Building a METAR-humidity-and-temperature-corrected series "
          "(not written to production data) ...", file=sys.stderr)
    corrected = build_metar_corrected(om, metar)
    n_metar = int((corrected["humidity_source"] == "metar").sum())
    print(f"  {n_metar}/{len(corrected)} hours use measured METAR humidity",
          file=sys.stderr)

    print("Computing WBGT for all three and the section 4.1 trend ...",
          file=sys.stderr)
    om_wbgt = add_wbgt(om)
    era5_wbgt = add_wbgt(era5)
    corr_wbgt = add_wbgt(corrected)

    t_om = trend(om_wbgt, "open_meteo_production")
    t_era5 = trend(era5_wbgt, "era5")
    t_corr = trend(corr_wbgt, "metar_humidity_corrected")

    results = {"dewpoint_triangulation": tri,
              "trend_open_meteo_production": t_om,
              "trend_era5": t_era5,
              "trend_metar_corrected": t_corr,
              "metar_coverage_hours": n_metar, "total_hours": int(len(corrected))}
    out = DATA / "humidity_defect_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out}", file=sys.stderr)

    print("\n" + "=" * 72)
    print("HUMIDITY DEFECT STUDY")
    print("=" * 72)
    print("\nJune-August dewpoint bias vs METAR (measured), product minus station:")
    print(f"  Open-Meteo  2014-2016 mean {tri['open_meteo_dewpoint_bias_2014_2016_mean']:+.2f} C"
          f"  ->  2018-2026 mean {tri['open_meteo_dewpoint_bias_2018_2026_mean']:+.2f} C"
          f"  (sign flip: {tri['sign_flip']})")
    print(f"  ERA5        2014-2016 mean {tri['era5_dewpoint_bias_2014_2016_mean']:+.2f} C"
          f"  ->  2018-2026 mean {tri['era5_dewpoint_bias_2018_2026_mean']:+.2f} C"
          f"  (stable: {tri['era5_stable']})")
    print("  by year:")
    for y, v in tri["by_year_jja"].items():
        print(f"    {y}: Open-Meteo {v['td_om_minus_metar']:+.2f}  "
              f"ERA5 {v['td_era5_minus_metar']:+.2f}")

    print(f"\nSection 4.1 trend (Jun-Sep, 06:00-18:00 local, WBGT > {THR} C):")
    print(f"  {'series':<28}{'2013-14':>10}{'2021-25':>10}{'slope/yr':>10}{'reg.window %':>14}")
    for t in (t_om, t_corr, t_era5):
        print(f"  {t['label']:<28}{t['early_2013_14_mean']:>10.1f}"
              f"{t['recent_2021_25_mean']:>10.1f}{t['slope_hours_per_year']:>+10.1f}"
              f"{t['regulated_window_exceedance_pct']:>13.1f}%")
    print()


if __name__ == "__main__":
    main()
