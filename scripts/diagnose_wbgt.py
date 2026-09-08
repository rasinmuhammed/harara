"""
Diagnostics for the Liljegren WBGT history:
  A) Sanity of the WBGT field (ranges, diurnal shape, exceedance rates)
  B) Is the recent exceedance jump real, or a seam in the archive data?

Run:  python scripts/diagnose_wbgt.py
"""

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd

from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C

THR = QATAR_WBGT_STOP_WORK_THRESHOLD_C

df = pd.read_csv(REPO_ROOT / "data" / "doha_wbgt_16yr.csv")
df["time"] = pd.to_datetime(df["time"], utc=True)
local = df["time"].dt.tz_convert("Asia/Qatar")
df["year"] = local.dt.year
df["month"] = local.dt.month
df["hour"] = local.dt.hour

# ----------------------------------------------------------------------
print("=" * 68)
print("A) WBGT FIELD SANITY")
print("=" * 68)

w = df["wbgt_c"]
print(f"  rows                 {len(df):,}   NaN: {int(w.isna().sum())}")
print(f"  WBGT min / max       {w.min():.1f} / {w.max():.1f} C")
print(f"  WBGT mean / median   {w.mean():.1f} / {w.median():.1f} C")

peak = df["month"].isin([7, 8]) & df["hour"].between(12, 15)
d = df.loc[peak]
print(f"\n  Jul-Aug 12-15 local (n={len(d):,}):")
print(f"    mean air temp      {d['temperature_2m'].mean():.1f} C")
print(f"    mean WBGT          {d['wbgt_c'].mean():.1f} C")
print(f"    WBGT p10 / p90     {d['wbgt_c'].quantile(0.1):.1f} / "
      f"{d['wbgt_c'].quantile(0.9):.1f} C")
print(f"    exceedance > {THR}   {(d['wbgt_c'] > THR).mean() * 100:.1f} %")

print("\n  Mean WBGT by local hour (summer, Jun-Sep):")
summer = df[df["month"].isin([6, 7, 8, 9])]
by_hour = summer.groupby("hour")["wbgt_c"].mean()
for h in range(0, 24, 3):
    bar = "#" * int(by_hour[h] - 15)
    print(f"    {h:02d}:00  {by_hour[h]:5.1f}  {bar}")

print("\n  Exceedance rate in the regulated window "
      "(Jun-15 Sep, 10:00-15:30 local):")
reg = (
    ((df["month"] == 6) | (df["month"] == 7) | (df["month"] == 8)
     | ((df["month"] == 9) & (local.dt.day <= 15)))
    & (local.dt.hour + local.dt.minute / 60 >= 10.0)
    & (local.dt.hour + local.dt.minute / 60 < 15.5)
)
print(f"    {(df.loc[reg, 'wbgt_c'] > THR).mean() * 100:.1f} %  "
      f"(n={int(reg.sum()):,})")

# ----------------------------------------------------------------------
print()
print("=" * 68)
print("B) DATA SEAM CHECK  (Jun-Aug only, like-for-like across years)")
print("=" * 68)

jja = df["month"].isin([6, 7, 8])
g = df.loc[jja].groupby("year")
summ = pd.DataFrame({
    "mean_Ta": g["temperature_2m"].mean(),
    "mean_RH": g["relative_humidity_2m"].mean(),
    "mean_P": g["surface_pressure"].mean(),
    "mean_SW": g["solar_wm2"].mean(),
    "mean_WS": g["wind_speed_ms"].mean(),
    "mean_WBGT": g["wbgt_c"].mean(),
    "exceed_h": g.apply(lambda x: int((x["wbgt_c"] > THR).sum())),
})
print(summ.round(2).to_string())

pre = summ.loc[2010:2020].mean(numeric_only=True)
recent = summ.loc[2021:2024].mean(numeric_only=True)
print()
print(f"  2010-2020 : Ta {pre['mean_Ta']:.2f}  WS {pre['mean_WS']:.2f}  "
      f"WBGT {pre['mean_WBGT']:.2f}")
print(f"  2021-2024 : Ta {recent['mean_Ta']:.2f}  WS {recent['mean_WS']:.2f}  "
      f"WBGT {recent['mean_WBGT']:.2f}")
for y in (2025, 2026):
    if y in summ.index:
        r = summ.loc[y]
        print(f"  {y}      : Ta {r['mean_Ta']:.2f}  WS {r['mean_WS']:.2f}  "
              f"WBGT {r['mean_WBGT']:.2f}   <-- check WS drop")
