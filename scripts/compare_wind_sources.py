"""
Cross-check the Open-Meteo archive wind against OTHH airport METAR
observations, year by year, to decide whether the 2025-2026 summer wind
drop in Open-Meteo is real or a product artifact.

METAR = measured (anemometer). Open-Meteo archive = reanalysis blend.
If the drop is in METAR too, it is weather. If only Open-Meteo drops, the
reanalysis changed under us and we must not rely on recent Open-Meteo wind.

Run:  python scripts/compare_wind_sources.py
"""

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd

om = pd.read_csv(REPO_ROOT / "data" / "doha_openmeteo_16yr.csv")
om["time"] = pd.to_datetime(om["time"], utc=True)
om = om.rename(columns={"wind_speed_10m": "wind_om"})[["time", "wind_om"]]

mt = pd.read_csv(REPO_ROOT / "data" / "othh_metar_hourly.csv")
mt["time"] = pd.to_datetime(mt["time"], utc=True)
mt = mt.rename(columns={"wind_speed_ms": "wind_metar"})[["time", "wind_metar"]]

df = om.merge(mt, on="time", how="inner")
df["year"] = df["time"].dt.year
df["month"] = df["time"].dt.month
jja = df[df["month"].isin([6, 7, 8])].copy()

print(f"Overlap: {df['time'].min().date()} .. {df['time'].max().date()}  "
      f"({len(df):,} hourly rows, {len(jja):,} in Jun-Aug)\n")

print("Jun-Aug mean wind speed [m/s], by year:")
print(f"  {'year':>4}  {'Open-Meteo':>10}  {'METAR':>8}  {'diff':>6}  {'n':>6}")
g = jja.groupby("year")
rows = []
for y, sub in g:
    a, b = sub["wind_om"].mean(), sub["wind_metar"].mean()
    rows.append((y, a, b, a - b, len(sub)))
    print(f"  {y:>4}  {a:>10.2f}  {b:>8.2f}  {a - b:>+6.2f}  {len(sub):>6}")

rows = pd.DataFrame(rows, columns=["year", "om", "metar", "diff", "n"]
                    ).set_index("year")

early = rows.loc[2014:2024]
late = rows.loc[2025:2026]
print("\n  2014-2024 mean:  Open-Meteo %.2f   METAR %.2f" %
      (early["om"].mean(), early["metar"].mean()))
print("  2025-2026 mean:  Open-Meteo %.2f   METAR %.2f" %
      (late["om"].mean(), late["metar"].mean()))
print("  drop 2025-26 vs 2014-24:  Open-Meteo %+.2f m/s (%.0f%%)   "
      "METAR %+.2f m/s (%.0f%%)" % (
          late["om"].mean() - early["om"].mean(),
          100 * (late["om"].mean() / early["om"].mean() - 1),
          late["metar"].mean() - early["metar"].mean(),
          100 * (late["metar"].mean() / early["metar"].mean() - 1),
      ))

# Correlation of the two series, early vs late - a drop in correlation
# would also flag a product change.
print("\n  Hourly correlation Open-Meteo vs METAR:")
for label, sub in [("2014-2024", df[(df.year <= 2024)]),
                   ("2025-2026", df[(df.year >= 2025)])]:
    s = sub.dropna(subset=["wind_om", "wind_metar"])
    r = np.corrcoef(s["wind_om"], s["wind_metar"])[0, 1]
    bias = (s["wind_om"] - s["wind_metar"]).mean()
    print(f"    {label}:  r = {r:.3f}   mean(OM - METAR) = {bias:+.2f} m/s   "
          f"(n={len(s):,})")
