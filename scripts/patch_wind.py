"""
Build a clean 16-year Doha weather file by patching the one known defect
in the Open-Meteo archive: from 2024-11 onward its 10 m wind is biased
~1.5-2.5 m/s low (confirmed against OTHH airport measurements in
compare_wind_sources.py - a change in Open-Meteo's underlying model, not
weather). Everything else in Open-Meteo agrees with the measured station
data to ~0.03 m/s over 2010-2024 and is left untouched.

For the patch window we substitute measured METAR wind, filling the small
METAR gaps by time interpolation. A `wind_source` column records, per row,
where the wind came from: 'openmeteo', 'metar', 'metar_interp'.

Output schema matches data/doha_openmeteo_16yr.csv (+ wind_source), so it
is a drop-in for run_first_result.py.

Run:  python scripts/patch_wind.py
"""

import pathlib
import sys

import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
PATCH_START = pd.Timestamp("2024-11-01", tz="UTC")
MAX_GAP_H = 6   # interpolate METAR across gaps up to this many hours


def main() -> None:
    om = pd.read_csv(REPO / "data" / "doha_openmeteo_16yr.csv")
    om["time"] = pd.to_datetime(om["time"], utc=True)
    om = om.sort_values("time").reset_index(drop=True)

    mt = pd.read_csv(REPO / "data" / "othh_metar_hourly.csv")
    mt["time"] = pd.to_datetime(mt["time"], utc=True)
    mt = mt[["time", "wind_speed_ms"]].rename(columns={"wind_speed_ms": "metar_wind"})

    df = om.merge(mt, on="time", how="left")

    # METAR interpolated onto the full hourly index (short gaps only).
    metar_filled = (
        df.set_index("time")["metar_wind"]
        .interpolate(method="time", limit=MAX_GAP_H, limit_area="inside")
        .to_numpy()
    )

    in_window = df["time"] >= PATCH_START
    src = pd.Series("openmeteo", index=df.index)
    new_wind = df["wind_speed_10m"].to_numpy().copy()

    have_raw = in_window & df["metar_wind"].notna()
    have_interp = in_window & df["metar_wind"].isna() & pd.notna(metar_filled)

    new_wind[have_raw.to_numpy()] = df.loc[have_raw, "metar_wind"].to_numpy()
    new_wind[have_interp.to_numpy()] = metar_filled[have_interp.to_numpy()]
    src[have_raw] = "metar"
    src[have_interp] = "metar_interp"

    df["wind_speed_10m"] = new_wind
    df["wind_source"] = src
    df = df.drop(columns=["metar_wind"])

    n_win = int(in_window.sum())
    n_om_left = int((src[in_window] == "openmeteo").sum())
    print(f"patch window: {PATCH_START.date()} .. {df['time'].max().date()}  "
          f"({n_win} h)", file=sys.stderr)
    print(f"  metar        : {int((src=='metar').sum()):>6}", file=sys.stderr)
    print(f"  metar_interp : {int((src=='metar_interp').sum()):>6}", file=sys.stderr)
    print(f"  openmeteo (gap fallback in window): {n_om_left}", file=sys.stderr)

    out = REPO / "data" / "doha_weather_16yr_patched.csv"
    df.to_csv(out, index=False)
    print(f"wrote {len(df)} rows -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
