"""
scripts/build_regime_dataset.py

Build the DAILY table for the forecast-reliability study: for each warm-
season day (Apr-Oct, 2022-2026) and each lead L in {24,48,72} h,

  LABEL   d_wetbulb_L = daytime-mean | Tw(forecast issued L h earlier)
                        - Tw(OTHH METAR) |   over 10:00-17:00 local.
          Binary  hi_uncertainty_L = d_wetbulb_L > tau  (tau set in the
          study; this file stores the continuous value).

  FEATURES  are all computable at forecast-issue time (day d's fields from
  the run issued L days before, plus that run's own previous-day values,
  plus METAR observed up to issue time, plus walk-forward climatology).
  Nothing derived from day d's outcome is a feature.

  VALIDATION-ONLY columns (dust fraction, min visibility, RH drop) are
  observed on day d and must not be used as predictors - they exist to
  physically check what the label is capturing.

Output: data/regime_daily.csv  (one row per day x lead)

Run:  python scripts/build_regime_dataset.py
"""

import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.psychro import wet_bulb_from_dewpoint, wet_bulb_stull
from src.solar import cos_solar_zenith_angle
from src.wbgt import wbgt_liljegren_c

DOHA_LAT, DOHA_LON = 25.27, 51.61
LEADS = [1, 2, 3]
DAY_LO, DAY_HI = 10, 17            # local-hour window for the label
WARM_MONTHS = [4, 5, 6, 7, 8, 9, 10]


def _fc_wbgt(df, n):
    g = lambda b: df[f"{b}_fc{n}"].to_numpy()
    return wbgt_liljegren_c(
        temp_c=g("temperature_2m"), rh_pct=g("relative_humidity_2m"),
        pressure_hpa=g("surface_pressure"), wind_speed_10m_ms=g("wind_speed_10m"),
        shortwave_wm2=np.nan_to_num(g("shortwave_radiation")),
        direct_wm2=np.nan_to_num(g("direct_radiation")),
        cos_zenith=df["cos_zenith"].to_numpy())


def daytime_agg(series_by_hour, local_hour, lo=DAY_LO, hi=DAY_HI):
    m = (local_hour >= lo) & (local_hour <= hi)
    return series_by_hour[m]


def main():
    # ---- hourly forecast archive ----
    fc = pd.read_csv(REPO / "data" / "doha_forecast_archive.csv")
    fc["time"] = pd.to_datetime(fc["time"], utc=True)
    fc["cos_zenith"] = cos_solar_zenith_angle(pd.DatetimeIndex(fc["time"]),
                                              DOHA_LAT, DOHA_LON)
    for n in LEADS:
        fc[f"tw_fc{n}"] = wet_bulb_stull(fc[f"temperature_2m_fc{n}"].to_numpy(),
                                         fc[f"relative_humidity_2m_fc{n}"].to_numpy())
        fc[f"wbgt_fc{n}"] = _fc_wbgt(fc, n)
    fc["local"] = fc["time"].dt.tz_convert("Asia/Qatar")
    fc["date"] = fc["local"].dt.date
    fc["lhour"] = fc["local"].dt.hour

    # ---- hourly METAR truth ----
    mt = pd.read_csv(REPO / "data" / "othh_metar_hourly.csv")
    mt["time"] = pd.to_datetime(mt["time"], utc=True)
    mt["tw_obs"] = wet_bulb_from_dewpoint(mt["temp_c"].to_numpy(),
                                          mt["dewpoint_c"].to_numpy())
    mt["local"] = mt["time"].dt.tz_convert("Asia/Qatar")
    mt["date"] = mt["local"].dt.date
    mt["lhour"] = mt["local"].dt.hour

    m = fc.merge(mt[["time", "tw_obs", "rh_pct", "wind_speed_ms", "wind_dir_deg",
                     "temp_c", "mslp_hpa", "visibility_km", "is_dust", "is_haze"]],
                 on="time", how="inner", suffixes=("", "_obs"))
    day = (m["lhour"] >= DAY_LO) & (m["lhour"] <= DAY_HI)
    md = m.loc[day].copy()

    # ---- daily aggregation ----
    g = md.groupby("date")
    daily = pd.DataFrame(index=sorted(md["date"].unique()))
    daily.index.name = "date"

    # validation-only (outcome-side; never a feature)
    daily["dust_frac"] = g["is_dust"].mean()
    daily["haze_frac"] = g["is_haze"].mean()
    daily["min_vis_km"] = g["visibility_km"].min()
    daily["obs_rh_mean"] = g["rh_pct"].mean()
    daily["obs_tw_mean"] = g["tw_obs"].mean()
    daily["obs_wind_mean"] = g["wind_speed_ms"].mean()

    # observed previous-day RH drop (validation-only descriptor)
    daily["obs_rh_drop_vs_prev"] = daily["obs_rh_mean"].shift(1) - daily["obs_rh_mean"]

    # ---- per-lead label + features ----
    # forecast daily daytime aggregates, per lead
    for n in LEADS:
        gg = md.groupby("date")
        # LABEL: daytime-mean absolute wet-bulb error, forecast vs METAR
        md[f"_abstw_{n}"] = (md[f"tw_fc{n}"] - md["tw_obs"]).abs()
        daily[f"lbl_dtw_{n}"] = gg[f"_abstw_{n}"].mean()
        fcw = gg[f"wbgt_fc{n}"].mean()
        # --- features known at issue time (forecast fields for day d) ---
        daily[f"fc_rh_mean_{n}"] = gg[f"relative_humidity_2m_fc{n}"].mean()
        daily[f"fc_rh_min_{n}"] = gg[f"relative_humidity_2m_fc{n}"].min()
        daily[f"fc_t_mean_{n}"] = gg[f"temperature_2m_fc{n}"].mean()
        daily[f"fc_t_max_{n}"] = gg[f"temperature_2m_fc{n}"].max()
        daily[f"fc_wind_mean_{n}"] = gg[f"wind_speed_10m_fc{n}"].mean()
        daily[f"fc_wind_max_{n}"] = gg[f"wind_speed_10m_fc{n}"].max()
        daily[f"fc_pres_mean_{n}"] = gg[f"surface_pressure_fc{n}"].mean()
        daily[f"fc_wbgt_mean_{n}"] = fcw
        daily[f"fc_sw_mean_{n}"] = gg[f"shortwave_radiation_fc{n}"].mean()
        # day-over-day forecast change (the run's own prev-day daytime mean)
        for col in ["fc_rh_mean", "fc_t_mean", "fc_wind_mean", "fc_pres_mean"]:
            daily[f"{col}_chg_{n}"] = daily[f"{col}_{n}"] - daily[f"{col}_{n}"].shift(1)

    # inter-lead forecast spread for day d (fc1 vs fc2 vs fc3 daytime WBGT)
    daily["fc_interlead_sd"] = daily[[f"fc_wbgt_mean_{n}" for n in LEADS]].std(axis=1)
    daily["fc_interlead_rh_sd"] = daily[[f"fc_rh_mean_{n}" for n in LEADS]].std(axis=1)

    # observed wet-bulb volatility available at issue time: std of daily
    # obs_tw_mean over the 5 days ending 24h*L before day d -> approximate
    # with a lead-agnostic 5-day trailing std shifted by 1 day (safe: it
    # ends the day before d, i.e. before any lead's issue for d).
    daily["obs_tw_vol_5d"] = daily["obs_tw_mean"].shift(1).rolling(5).std()
    daily["obs_rh_5d_mean"] = daily["obs_rh_mean"].shift(1).rolling(5).mean()

    # walk-forward climatological RH for the calendar day (years strictly
    # before) -> anomaly feature. Uses obs_rh_mean history only.
    dd = daily.reset_index()
    dd["doy"] = pd.to_datetime(dd["date"]).dt.dayofyear
    dd["yr"] = pd.to_datetime(dd["date"]).dt.year
    clim = {}
    rh_clim = np.full(len(dd), np.nan)
    for i in range(len(dd)):
        key = dd.loc[i, "doy"]
        hist = clim.get(key, [])
        if hist:
            rh_clim[i] = np.mean(hist)
        clim.setdefault(key, []).append(dd.loc[i, "obs_rh_mean"])
    dd["rh_clim"] = rh_clim
    daily = dd.set_index("date")
    for n in LEADS:
        daily[f"fc_rh_anom_{n}"] = daily[f"fc_rh_mean_{n}"] - daily["rh_clim"]

    # ---- reshape to one row per (date, lead) ----
    rows = []
    feat_cols_base = [
        "fc_rh_mean", "fc_rh_min", "fc_t_mean", "fc_t_max", "fc_wind_mean",
        "fc_wind_max", "fc_pres_mean", "fc_wbgt_mean", "fc_sw_mean",
        "fc_rh_mean_chg", "fc_t_mean_chg", "fc_wind_mean_chg", "fc_pres_mean_chg",
        "fc_rh_anom",
    ]
    shared = ["fc_interlead_sd", "fc_interlead_rh_sd", "obs_tw_vol_5d",
              "obs_rh_5d_mean", "rh_clim"]
    valcols = ["dust_frac", "haze_frac", "min_vis_km", "obs_rh_mean",
               "obs_tw_mean", "obs_wind_mean", "obs_rh_drop_vs_prev"]
    d = daily.reset_index()
    d["month"] = pd.to_datetime(d["date"]).dt.month
    d = d[d["month"].isin(WARM_MONTHS)]
    for _, r in d.iterrows():
        for n in LEADS:
            row = {"date": r["date"], "lead_h": 24 * n,
                   "label_dtw": r[f"lbl_dtw_{n}"]}
            for b in feat_cols_base:
                row[b] = r[f"{b}_{n}"]
            for s in shared:
                row[s] = r[s]
            for v in valcols:
                row[v] = r[v]
            rows.append(row)
    out = pd.DataFrame(rows).dropna(subset=["label_dtw"]).reset_index(drop=True)

    p = REPO / "data" / "regime_daily.csv"
    out.to_csv(p, index=False)
    print(f"wrote {len(out)} (date x lead) rows -> {p}", file=sys.stderr)
    print(f"date span: {out['date'].min()} .. {out['date'].max()}", file=sys.stderr)
    for tau in (1.0, 1.5, 2.0):
        pr = (out["label_dtw"] > tau).mean()
        print(f"  base rate at tau={tau} C wet-bulb: {pr*100:5.1f}% "
              f"({int((out['label_dtw']>tau).sum())}/{len(out)})", file=sys.stderr)


if __name__ == "__main__":
    main()
