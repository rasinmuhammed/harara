"""
scripts/run_first_result.py

How well do trivial baselines predict

Run (from the repo root):
    python scripts/run_first_result.py --data data/doha_openmeteo_16yr.csv
"""

import argparse
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from src.solar import cos_solar_zenith_angle
from src.wbgt import wbgt_liljegren_c, QATAR_WBGT_STOP_WORK_THRESHOLD_C
from eval.harness import run_baseline_comparison, baseline_persistence, evaluate

THRESHOLD = QATAR_WBGT_STOP_WORK_THRESHOLD_C

# Open-Meteo grid cell we fetched (see scripts/fetch_open_meteo.py).
DOHA_LAT, DOHA_LON = 25.27, 51.61


# --------------------------------------------------------------------------
# 1. Load + clean. Every line here prevents a silent benchmark corruption.
# --------------------------------------------------------------------------
def load_and_prepare(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    # CSV stores datetimes as text; sorting, .dt, and climatology keys all
    # need real timestamps. We fetched the data as UTC.
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)

    # Persistence = .shift(lead) only means "lead hours ago" if rows are
    # exactly 1 h apart. Surface any gaps instead of silently trusting them.
    gaps = df["time"].diff().dropna()
    odd = gaps[gaps != pd.Timedelta(hours=1)]
    if len(odd):
        print(f"WARNING: {len(odd)} non-1h gaps (largest {odd.max()}). "
              f"Baselines assume regular hourly spacing.", file=sys.stderr)

    # Wind is already m/s (fetch_open_meteo.py sets wind_speed_unit=ms).
    df["wind_speed_ms"] = df["wind_speed_10m"]

    # Radiation for the Liljegren solver: global horizontal (shortwave) and
    # its direct-beam part. thermofeel derives the direct fraction itself.
    df["solar_wm2"] = df["shortwave_radiation"].fillna(0.0)
    df["direct_wm2"] = df["direct_radiation"].fillna(0.0)

    # Solar geometry: ERA5 ships cos(zenith); Open-Meteo doesn't, so compute
    # it from the timestamp + grid-cell location.
    df["cos_zenith"] = cos_solar_zenith_angle(
        pd.DatetimeIndex(df["time"]), DOHA_LAT, DOHA_LON
    )

    return df


# --------------------------------------------------------------------------
# 2. Weather -> the hazard variable (physically-based Liljegren WBGT).
# --------------------------------------------------------------------------
def add_wbgt(df: pd.DataFrame) -> pd.DataFrame:
    df["wbgt_c"] = wbgt_liljegren_c(
        temp_c=df["temperature_2m"].values,
        rh_pct=df["relative_humidity_2m"].values,
        pressure_hpa=df["surface_pressure"].values,
        wind_speed_10m_ms=df["wind_speed_ms"].values,
        shortwave_wm2=df["solar_wm2"].values,
        direct_wm2=df["direct_wm2"].values,
        cos_zenith=df["cos_zenith"].values,
    )
    n_nan = int(df["wbgt_c"].isna().sum())
    if n_nan:
        print(f"NOTE: {n_nan} rows returned NaN WBGT (solver non-convergence); "
              f"they are dropped from every metric.", file=sys.stderr)
    return df


# --------------------------------------------------------------------------
# 3. Base rates. Threshold metrics are meaningless without knowing how
#    rare the threshold crossing is.
# --------------------------------------------------------------------------
def describe_hazard(df: pd.DataFrame) -> None:
    local = df["time"].dt.tz_convert("Asia/Qatar")   # UTC+3, no DST
    exceed = df["wbgt_c"] > THRESHOLD

    print(f"\n=== Hazard base rate (WBGT > {THRESHOLD} C) ===")
    print(f"All hours:           {exceed.mean() * 100:5.2f}%  "
          f"({int(exceed.sum())}/{len(df)})")

    # The regulation only bites Jun-Sep, ~10:00-15:30 local. That subset is
    # the product's real operating regime.
    reg = local.dt.month.isin([6, 7, 8, 9]) & local.dt.hour.between(10, 15)
    reg_rate = (df.loc[reg, "wbgt_c"] > THRESHOLD).mean() * 100
    print(f"Jun-Sep 10-15 local: {reg_rate:5.1f}%  <- product's real regime")

    per_year = exceed.groupby(local.dt.year).sum()
    print("\nExceedance hours per calendar year:")
    for y, h in per_year.items():
        print(f"  {y}: {int(h):5d} h")


# --------------------------------------------------------------------------
# 4. The baselines. This is the number.
# --------------------------------------------------------------------------
def report(df: pd.DataFrame, leads=(24, 48, 72)) -> None:
    hdr = (f"{'model':<26} {'RMSE':>6} {'MAE':>6} {'hit%':>7} "
           f"{'MISS%':>8} {'falsePos%':>9}")

    def line(r):
        return (f"{r.name:<26} {r.rmse:6.2f} {r.mae:6.2f} "
                f"{r.hit_rate * 100:7.1f} {r.false_negative_rate * 100:8.1f} "
                f"{r.false_positive_rate * 100:9.1f}")

    print(f"\n=== Skill vs baselines ===\n{hdr}\n{'-' * len(hdr)}")

    # 24 h: full comparison (persistence + walk-forward climatology).
    for r in run_baseline_comparison(df[["time", "wbgt_c"]].copy(),
                                     "wbgt_c", "time", 24):
        print(line(r))

    # 48/72 h: climatology is lead-independent in this simple form; only
    # persistence changes. Using the harness pieces directly here is also
    # exactly how you'll plug Layer 1 in later.
    for lead in leads:
        if lead == 24:
            continue
        pred = baseline_persistence(df, "wbgt_c", lead)
        print(line(evaluate(df["wbgt_c"].values, pred,
                            name=f"persistence_{lead}h")))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/doha_openmeteo_16yr.csv")
    args = ap.parse_args()

    df = add_wbgt(load_and_prepare(args.data))
    describe_hazard(df)
    report(df)

    out = REPO_ROOT / "data" / "doha_wbgt_16yr.csv"
    df[["time", "temperature_2m", "relative_humidity_2m", "surface_pressure",
        "wind_speed_ms", "solar_wm2", "direct_wm2", "cos_zenith",
        "wbgt_c"]].to_csv(out, index=False)
    print(f"\nWrote WBGT history -> {out}")
