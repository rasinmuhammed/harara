"""
Extend the patched 16-year Doha weather file with the second known Open-Meteo
defect: from 2018 onward its summer dewpoint (moisture content, not relative
humidity, which also moves with temperature) drifts dry against the OTHH
station, and its temperature drifts warm - confirmed independently by ERA5,
which tracks the station on both throughout (`scripts/humidity_defect_study.py`,
technical_report.md section 5.8). Unlike the wind defect this is a gradual,
seasonal, decade-scale drift, not a sharp step at one date, so there is no
single cutover to gate on; instead the same principle as patch_wind.py
applies without a date window: prefer the measurement wherever you have it.

Temperature and dewpoint are patched TOGETHER from METAR and relative
humidity is recomputed from the (possibly patched) pair, so a hazard-relevant
row never mixes an Open-Meteo temperature with a METAR dewpoint or vice
versa - the two must come from the same source to stay thermodynamically
consistent. Wind (already patched by patch_wind.py) is untouched. A
`humidity_source` column records, per row, where temperature and relative
humidity came from: 'openmeteo', 'metar', 'metar_interp'.

This changes the input to nearly everything in technical_report.md sections
4 through 9. Downstream numbers are refreshed by re-running the affected
scripts (run_first_result.py first, to rebuild data/doha_wbgt_16yr.csv, then
the studies that read it) - see docs/results_ledger.md row 35 and
run_all.sh.

Run:  python scripts/patch_humidity.py
      python scripts/run_first_result.py --data data/doha_weather_16yr_patched.csv
"""

import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
MAX_GAP_H = 6   # interpolate METAR across gaps up to this many hours, same as patch_wind.py


def rh_from_dewpoint(t_c: np.ndarray, td_c: np.ndarray) -> np.ndarray:
    """Relative humidity [%] from temperature and dewpoint (both C), Magnus
    formula over water - the same formula era5_to_csv.py uses."""
    a, b = 17.625, 243.04
    e = np.exp(a * td_c / (b + td_c))
    es = np.exp(a * t_c / (b + t_c))
    return np.clip(100.0 * e / es, 0.0, 100.0)


def main() -> None:
    df = pd.read_csv(REPO / "data" / "doha_weather_16yr_patched.csv")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    if "wind_source" not in df.columns:
        raise SystemExit("run patch_wind.py first - this extends its output")

    mt = pd.read_csv(REPO / "data" / "othh_metar_hourly.csv")
    mt["time"] = pd.to_datetime(mt["time"], utc=True)
    mt = mt[["time", "temp_c", "dewpoint_c"]].rename(
        columns={"temp_c": "metar_t", "dewpoint_c": "metar_td"})

    df = df.merge(mt, on="time", how="left")

    # METAR interpolated onto the full hourly index (short gaps only). T and
    # Td are interpolated independently but only BOTH being present (raw or
    # filled) qualifies a row for the patch, so they always travel together.
    idx = df.set_index("time")
    t_filled = idx["metar_t"].interpolate(
        method="time", limit=MAX_GAP_H, limit_area="inside").to_numpy()
    td_filled = idx["metar_td"].interpolate(
        method="time", limit=MAX_GAP_H, limit_area="inside").to_numpy()

    have_raw = df["metar_t"].notna().to_numpy() & df["metar_td"].notna().to_numpy()
    have_interp = (~have_raw) & pd.notna(t_filled) & pd.notna(td_filled)

    new_t = df["temperature_2m"].to_numpy(dtype=float).copy()
    new_rh = df["relative_humidity_2m"].to_numpy(dtype=float).copy()
    src = pd.Series("openmeteo", index=df.index)

    for mask, t_src, td_src, label in (
        (have_raw, df["metar_t"].to_numpy(), df["metar_td"].to_numpy(), "metar"),
        (have_interp, t_filled, td_filled, "metar_interp"),
    ):
        new_t[mask] = t_src[mask]
        new_rh[mask] = rh_from_dewpoint(t_src[mask], td_src[mask])
        src[mask] = label

    df["temperature_2m"] = new_t
    df["relative_humidity_2m"] = new_rh
    df["humidity_source"] = src
    df = df.drop(columns=["metar_t", "metar_td"])

    n = len(df)
    print(f"humidity patch: {df['time'].min().date()} .. {df['time'].max().date()}  "
          f"({n} h)", file=sys.stderr)
    print(f"  metar        : {int((src == 'metar').sum()):>7}  "
          f"({(src == 'metar').mean() * 100:.1f}%)", file=sys.stderr)
    print(f"  metar_interp : {int((src == 'metar_interp').sum()):>7}  "
          f"({(src == 'metar_interp').mean() * 100:.1f}%)", file=sys.stderr)
    print(f"  openmeteo    : {int((src == 'openmeteo').sum()):>7}  "
          f"({(src == 'openmeteo').mean() * 100:.1f}%)  (no METAR row for this hour)",
          file=sys.stderr)

    out = REPO / "data" / "doha_weather_16yr_patched.csv"
    df.to_csv(out, index=False)
    print(f"wrote {len(df)} rows -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
