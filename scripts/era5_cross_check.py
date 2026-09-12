"""
scripts/era5_cross_check.py

A TARGETED ERA5 CROSS-CHECK of the section 5 findings (technical_report.md
S12 limitation 2, S13 further-work item 3), now that the 2010-2026 ERA5
backfill (fetch_era5.py, era5_to_csv.py) is complete.

ERA5 is a genuinely independent product from the working dataset: different
provider (Copernicus, not Open-Meteo's blend), different underlying model
(IFS Cy41r2, frozen), different processing (4D-Var reanalysis, not a
forecast-verification archive). It is not "ground truth" any more than
Open-Meteo is - both are model estimates - but where they and the METAR
station agree, that is real signal; where they disagree, that is the
uncertainty the report should own.

Three questions, each answered independently of the others so a null result
on one does not colour another:

  Q1  Is Open-Meteo's Nov-2024-onward wind defect (row 4 of the results
      ledger; confirmed against METAR in compare_wind_sources.py) also
      visible in ERA5, a third independent source? If ERA5 tracks METAR and
      diverges from Open-Meteo in the same window, that is now a
      two-against-one confirmation, not a single station's word against a
      blend.
  Q2  How well does ERA5-derived WBGT agree with the working dataset
      (data/doha_wbgt_16yr.csv, i.e. Open-Meteo patched with METAR wind from
      Nov 2024) over the full 16-year overlap: bias, RMSE, and - the metric
      that matters throughout this report - agreement on which hours cross
      the 32.1 C stop-work line.
  Q3  Does ERA5, independently, reproduce the rising exceedance-hour trend
      reported in section 4.1 (about 500 hours/year in 2013-2014 to about
      650-770 in 2021-2026)?

WBGT is computed from ERA5 with the exact same Liljegren solver and the same
Doha grid point (25.27, 51.61) as the working dataset (run_first_result.py),
so any difference is in the inputs, not the physics. As an internal check
before trusting any ERA5 comparison, this script first recomputes WBGT from
the patched Open-Meteo file and confirms it reproduces the stored
data/doha_wbgt_16yr.csv - if that check fails, the pipeline has drifted and
the ERA5 numbers below are not to be trusted.

Season / exceedance-hour definition (Q3), for consistency with
api/planning.py's heat_trend(): June-September, 06:00-18:00 local
(Asia/Qatar), WBGT > 32.1 C. This is deliberately a plain daytime-hours
count, not the report's "regulated summer working window" figure (10:00 to
15:30) - the two answer different questions and are not meant to match.

Run:  python scripts/era5_cross_check.py
Writes:  data/era5_cross_check_results.json (every number below, for the
         report and the results ledger; nothing here is reported that is
         not in that file).
"""

from __future__ import annotations

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd

from src.solar import cos_solar_zenith_angle
from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C, wbgt_liljegren_c

DATA = REPO_ROOT / "data"
DOHA_LAT, DOHA_LON = 25.27, 51.61     # same point as run_first_result.py / era5_to_csv.py
THR = QATAR_WBGT_STOP_WORK_THRESHOLD_C
TZ = "Asia/Qatar"
RNG = np.random.default_rng(11)       # fixed seed, matches the rest of the repo


# --------------------------------------------------------------------------
def _load_hourly(path: pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.sort_values("time").reset_index(drop=True)


def add_wbgt(df: pd.DataFrame) -> pd.DataFrame:
    """Liljegren WBGT at the Doha point, same recipe as run_first_result.py."""
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


def block_ci(diff: np.ndarray, stat=np.mean, block: int = 24 * 30, n: int = 2000):
    """Moving-block-bootstrap 95% CI, block ~ 30 days of hourly data, matching
    the block scale used elsewhere in this report for hourly series."""
    x = np.asarray(diff, dtype=float)
    x = x[~np.isnan(x)]
    m = len(x)
    if m < block * 3:
        return (np.nan, np.nan)
    starts = np.arange(0, m - block + 1)
    nb = int(np.ceil(m / block))
    out = [stat(np.concatenate([x[a:a + block] for a in RNG.choice(starts, nb)])[:m])
           for _ in range(n)]
    return tuple(np.percentile(out, [2.5, 97.5]))


def bias_rmse_r(a: np.ndarray, b: np.ndarray) -> dict:
    """a - b: bias, RMSE, correlation. NaN-safe."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = ~(np.isnan(a) | np.isnan(b))
    a, b = a[ok], b[ok]
    d = a - b
    lo, hi = block_ci(d)
    return {
        "n": int(ok.sum()),
        "bias": round(float(d.mean()), 3),
        "bias_ci95": [round(float(lo), 3), round(float(hi), 3)],
        "rmse": round(float(np.sqrt((d ** 2).mean())), 3),
        "r": round(float(np.corrcoef(a, b)[0, 1]), 3),
    }


# --------------------------------------------------------------------------
def internal_consistency_check(patched: pd.DataFrame) -> dict:
    """Recompute WBGT from the patched Open-Meteo file with this script's own
    pipeline and confirm it reproduces the stored data/doha_wbgt_16yr.csv.
    This is a check on THIS script, not a research finding - if it fails,
    everything below is suspect."""
    recomputed = add_wbgt(patched)[["time", "wbgt_c"]].rename(
        columns={"wbgt_c": "wbgt_recomputed"})
    stored = _load_hourly(DATA / "doha_wbgt_16yr.csv")[["time", "wbgt_c"]].rename(
        columns={"wbgt_c": "wbgt_stored"})
    m = recomputed.merge(stored, on="time", how="inner")
    d = (m["wbgt_recomputed"] - m["wbgt_stored"]).to_numpy()
    max_abs = float(np.nanmax(np.abs(d)))
    ok = bool(np.nanmax(np.abs(d)) < 0.05) and len(m) == len(stored) == len(recomputed)
    return {"n_matched": int(len(m)), "n_stored": int(len(stored)),
           "n_recomputed": int(len(recomputed)), "max_abs_diff": round(max_abs, 4),
           "passed": ok}


def q1_wind_defect(era5: pd.DataFrame, om_raw: pd.DataFrame,
                   metar: pd.DataFrame) -> dict:
    """Does ERA5, a third independent source, corroborate the Open-Meteo
    wind drop from Nov 2024 that METAR alone flagged (results ledger row 4)?
    Same Jun-Aug-mean-by-year framing as compare_wind_sources.py."""
    e = era5[["time", "wind_speed_10m"]].rename(columns={"wind_speed_10m": "wind_era5"})
    o = om_raw[["time", "wind_speed_10m"]].rename(columns={"wind_speed_10m": "wind_om"})
    mt = metar[["time", "wind_speed_ms"]].rename(columns={"wind_speed_ms": "wind_metar"})

    df = e.merge(o, on="time", how="inner").merge(mt, on="time", how="inner")
    df["year"] = df["time"].dt.year
    df["month"] = df["time"].dt.month
    jja = df[df["month"].isin([6, 7, 8])].copy()

    by_year = (jja.groupby("year")[["wind_era5", "wind_om", "wind_metar"]]
              .mean().round(3))

    early = by_year.loc[[y for y in by_year.index if 2014 <= y <= 2024]]
    late = by_year.loc[[y for y in by_year.index if y >= 2025]]

    def pct_drop(col):
        e0, l0 = early[col].mean(), late[col].mean()
        return round(float(l0 - e0), 3), round(float(100 * (l0 / e0 - 1)), 1)

    d_era5, p_era5 = pct_drop("wind_era5")
    d_om, p_om = pct_drop("wind_om")
    d_mt, p_mt = pct_drop("wind_metar")

    # Open-Meteo shows a large-magnitude change; the two independent sources
    # (ERA5, METAR) do not. Near-zero differences can flip sign on rounding
    # noise, so this does not require ERA5 and METAR to agree in sign with
    # each other, only that both stay small while Open-Meteo does not.
    corroborated = (abs(p_om) > 15.0) and (abs(p_era5) < abs(p_om) / 3) and \
        (abs(p_mt) < abs(p_om) / 3)

    return {
        "by_year_jja_mean_wind_ms": {int(y): r.to_dict() for y, r in by_year.iterrows()},
        "drop_2025_26_vs_2014_24": {
            "era5_ms": d_era5, "era5_pct": p_era5,
            "open_meteo_ms": d_om, "open_meteo_pct": p_om,
            "metar_ms": d_mt, "metar_pct": p_mt,
        },
        "era5_corroborates_metar_not_openmeteo": bool(corroborated),
        "note": ("METAR and ERA5 are independent of Open-Meteo and of each "
                "other. If both show a much smaller (or no) drop while "
                "Open-Meteo shows a large one, the defect is in Open-Meteo, "
                "confirming row 4 of the results ledger a second way."),
    }


def q2_wbgt_agreement(era5_wbgt: pd.DataFrame, om_wbgt: pd.DataFrame) -> dict:
    """ERA5-derived WBGT vs the working (patched Open-Meteo) WBGT, full
    16-year hourly overlap: bias, RMSE, and agreement on the 32.1 C
    stop-work exceedance, the decision the whole report is built around."""
    a = era5_wbgt[["time", "wbgt_c"]].rename(columns={"wbgt_c": "wbgt_era5"})
    b = om_wbgt[["time", "wbgt_c"]].rename(columns={"wbgt_c": "wbgt_om"})
    m = a.merge(b, on="time", how="inner").dropna()

    overall = bias_rmse_r(m["wbgt_era5"], m["wbgt_om"])

    m["year"] = m["time"].dt.year
    by_year = {}
    for y, sub in m.groupby("year"):
        by_year[int(y)] = bias_rmse_r(sub["wbgt_era5"], sub["wbgt_om"])

    era5_over = m["wbgt_era5"] > THR
    om_over = m["wbgt_om"] > THR
    both = int((era5_over & om_over).sum())
    era5_only = int((era5_over & ~om_over).sum())
    om_only = int((~era5_over & om_over).sum())
    neither = int((~era5_over & ~om_over).sum())
    n = len(m)

    # Neither series is ground truth, so this is reported as symmetric
    # agreement, not a directional "miss rate" against either as reference.
    return {
        "n_hours": int(n),
        "overall": overall,
        "by_year": by_year,
        "exceedance_32_1c_agreement": {
            "both_over": both, "era5_only_over": era5_only,
            "om_only_over": om_only, "neither_over": neither,
            "agreement_pct": round(100 * (both + neither) / n, 1),
            "of_era5_exceedance_hours_pct_om_also_flags": round(
                100 * both / (both + era5_only), 1) if (both + era5_only) else None,
            "of_om_exceedance_hours_pct_era5_also_flags": round(
                100 * both / (both + om_only), 1) if (both + om_only) else None,
        },
    }


def q3_variable_bias_by_year(era5: pd.DataFrame, om: pd.DataFrame) -> dict:
    """Warm-season daytime bias (ERA5 - working dataset) per input variable,
    per year. Diagnostic support for Q3: if the two WBGT series diverge in
    some years, this says which input variable is driving it, rather than
    leaving the divergence unexplained."""
    m = era5.merge(om, on="time", suffixes=("_era5", "_om"))
    loc = m["time"].dt.tz_convert(TZ)
    m["year"], m["month"], m["hour"] = loc.dt.year, loc.dt.month, loc.dt.hour
    sub = m[(m["month"].between(6, 9)) & (m["hour"].between(6, 18))]

    out = {}
    for y, g in sub.groupby("year"):
        out[int(y)] = {
            "d_temp_c": round(float((g["temperature_2m_era5"] - g["temperature_2m_om"]).mean()), 2),
            "d_rh_pp": round(float((g["relative_humidity_2m_era5"] - g["relative_humidity_2m_om"]).mean()), 2),
            "d_wind_ms": round(float((g["wind_speed_10m_era5"] - g["wind_speed_10m_om"]).mean()), 2),
            "d_shortwave_wm2": round(float((g["shortwave_radiation_era5"] - g["shortwave_radiation_om"]).mean()), 1),
            "n": int(len(g)),
        }
    return out


def q3_trend(era5_wbgt: pd.DataFrame, om_wbgt: pd.DataFrame) -> dict:
    """Warm-season (Jun-Sep, 06:00-18:00 local) WBGT>32.1 hours per year,
    ERA5 vs the working dataset - does an independent product reproduce the
    section 4.1 rising trend?"""
    def per_year_hours(df):
        d = df[["time", "wbgt_c"]].copy()
        loc = d["time"].dt.tz_convert(TZ)
        d["month"], d["hour"], d["year"] = loc.dt.month, loc.dt.hour, loc.dt.year
        sel = d[(d["month"].between(6, 9)) & (d["hour"].between(6, 18))]
        return sel.assign(over=sel["wbgt_c"] > THR).groupby("year")["over"].sum()

    era5_y = per_year_hours(era5_wbgt)
    om_y = per_year_hours(om_wbgt)

    # drop the partial trailing year (record ends 2026-08-31)
    era5_y = era5_y.iloc[:-1] if era5_y.index[-1] == 2026 else era5_y
    om_y = om_y.iloc[:-1] if om_y.index[-1] == 2026 else om_y

    def slope(y):
        yrs = y.index.to_numpy(dtype=float)
        vals = y.to_numpy(dtype=float)
        return float(np.polyfit(yrs, vals, 1)[0]) if len(yrs) >= 3 else float("nan")

    return {
        "era5_hours_per_year": {int(k): int(v) for k, v in era5_y.items()},
        "om_hours_per_year": {int(k): int(v) for k, v in om_y.items()},
        "era5_early_mean_2013_14": round(float(era5_y.reindex([2013, 2014]).mean()), 1),
        "era5_recent_mean_2021_25": round(
            float(era5_y.reindex(range(2021, 2026)).mean()), 1),
        "era5_slope_hours_per_year": round(slope(era5_y), 1),
        "om_slope_hours_per_year": round(slope(om_y), 1),
        "both_rising": bool(slope(era5_y) > 0 and slope(om_y) > 0),
    }


# --------------------------------------------------------------------------
def main() -> None:
    print("Loading ERA5, Open-Meteo (raw + patched), METAR ...", file=sys.stderr)
    era5 = _load_hourly(DATA / "doha_era5_hourly.csv")
    om_raw = _load_hourly(DATA / "doha_openmeteo_16yr.csv")
    om_patched = _load_hourly(DATA / "doha_weather_16yr_patched.csv")
    metar = _load_hourly(DATA / "othh_metar_hourly.csv")

    print(f"  ERA5:          {era5['time'].min()} .. {era5['time'].max()}  "
          f"({len(era5):,} h)", file=sys.stderr)
    print(f"  Open-Meteo raw:{om_raw['time'].min()} .. {om_raw['time'].max()}  "
          f"({len(om_raw):,} h)", file=sys.stderr)

    print("\nInternal consistency check (this script's own pipeline vs the "
          "stored WBGT file) ...", file=sys.stderr)
    consistency = internal_consistency_check(om_patched)
    print(f"  {consistency}", file=sys.stderr)
    if not consistency["passed"]:
        print("  FAILED - stopping. Do not trust the numbers below until this "
              "is fixed.", file=sys.stderr)
        sys.exit(1)

    print("\nComputing WBGT from ERA5 and from the patched Open-Meteo file "
          "...", file=sys.stderr)
    era5_wbgt = add_wbgt(era5)
    om_wbgt = add_wbgt(om_patched)

    print("Q1: the Nov-2024 wind defect, checked against a third source "
          "...", file=sys.stderr)
    q1 = q1_wind_defect(era5, om_raw, metar)

    print("Q2: ERA5 vs working-dataset WBGT, full 16-year overlap ...",
          file=sys.stderr)
    q2 = q2_wbgt_agreement(era5_wbgt, om_wbgt)

    print("Q3: does ERA5 reproduce the rising exceedance-hour trend ...",
          file=sys.stderr)
    q3 = q3_trend(era5_wbgt, om_wbgt)
    q3_diag = q3_variable_bias_by_year(era5, om_patched)

    results = {"internal_consistency_check": consistency,
              "q1_wind_defect": q1, "q2_wbgt_agreement": q2, "q3_trend": q3,
              "q3_variable_bias_by_year": q3_diag}
    out = DATA / "era5_cross_check_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out}", file=sys.stderr)

    # ---------------------------------------------------------- report
    print("\n" + "=" * 72)
    print("ERA5 CROSS-CHECK")
    print("=" * 72)

    print("\nInternal consistency check:")
    print(f"  max |recomputed - stored| WBGT = {consistency['max_abs_diff']} C "
          f"over {consistency['n_matched']:,} matched hours -> "
          f"{'PASS' if consistency['passed'] else 'FAIL'}")

    print("\nQ1. Nov-2024 wind defect (Jun-Aug mean wind, m/s):")
    d = q1["drop_2025_26_vs_2014_24"]
    print(f"  2025-26 vs 2014-24 drop:  ERA5 {d['era5_ms']:+.2f} ({d['era5_pct']:+.0f}%)"
          f"   Open-Meteo {d['open_meteo_ms']:+.2f} ({d['open_meteo_pct']:+.0f}%)"
          f"   METAR {d['metar_ms']:+.2f} ({d['metar_pct']:+.0f}%)")
    print(f"  ERA5 corroborates METAR, not Open-Meteo: "
          f"{q1['era5_corroborates_metar_not_openmeteo']}")

    print(f"\nQ2. ERA5 vs working-dataset WBGT ({q2['n_hours']:,} matched hours):")
    o = q2["overall"]
    print(f"  bias {o['bias']:+.2f} C [{o['bias_ci95'][0]:+.2f}, {o['bias_ci95'][1]:+.2f}]"
          f"   RMSE {o['rmse']:.2f} C   r {o['r']:.3f}")
    e = q2["exceedance_32_1c_agreement"]
    print(f"  32.1 C exceedance: both {e['both_over']:,}  ERA5-only {e['era5_only_over']:,}"
          f"  OM-only {e['om_only_over']:,}  neither {e['neither_over']:,}"
          f"  (agree {e['agreement_pct']}% of hours)")
    print(f"  of ERA5's exceedance hours, OM also flags "
          f"{e['of_era5_exceedance_hours_pct_om_also_flags']}%; "
          f"of OM's, ERA5 also flags {e['of_om_exceedance_hours_pct_era5_also_flags']}%")

    print("\nQ3. Warm-season (Jun-Sep, 06:00-18:00 local) exceedance hours/year:")
    print(f"  ERA5:            {q3['era5_early_mean_2013_14']:.0f} (2013-14 mean) -> "
          f"{q3['era5_recent_mean_2021_25']:.0f} (2021-25 mean), "
          f"slope {q3['era5_slope_hours_per_year']:+.1f} h/yr")
    print(f"  working dataset: slope {q3['om_slope_hours_per_year']:+.1f} h/yr "
          f"over the same years")
    widest = sorted(q3_diag.items(), key=lambda kv: abs(kv[1]["d_rh_pp"]),
                    reverse=True)[:3]
    print("  Years with the largest ERA5-vs-working humidity gap (driver of "
          "the disagreement above):")
    for y, d in widest:
        print(f"    {y}: dRH {d['d_rh_pp']:+.1f} pp, dT {d['d_temp_c']:+.2f} C, "
              f"dWind {d['d_wind_ms']:+.2f} m/s")
    print()


if __name__ == "__main__":
    main()
