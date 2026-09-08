"""
scripts/regime_climatology_study.py

STUDY B - Dry-transition ("Shamal") regime climatology for Doha, and the
error a gridded reanalysis carries during that regime.

Thesis under test: on most warm-season days a gridded product (here the
Open-Meteo reanalysis blend) represents Doha near-surface conditions well;
on the recurring dry-transition regime it does not, and the residual error
is large enough to flip an occupational-heat work/rest decision. Because
the regime days are few and clustered, an operational heat-safety system
driven only by gridded data inherits a concentrated, systematic blind spot
that only local observation resolves.

Data (all homogeneous, 2014-2026 overlap):
  - OTHH METAR hourly  - station truth (temp, dewpoint->RH, wind, dir,
    MSLP, visibility, dust/haze present-weather flags)
  - Open-Meteo reanalysis, patched  - the gridded product under test
    (temp, RH, wind, pressure, shortwave/direct radiation, Liljegren WBGT)

Method
  1. Daily daytime (10-17 local) aggregates for both sources, warm season
     (Apr-Oct).
  2. Regime label = daytime-mean RH anomaly (vs a LEAVE-CURRENT-YEAR-OUT
     day-of-year climatology from the station record) below -DELTA points.
     Primary DELTA = 8; robustness at 6/10/12 and with a NW-wind gate.
  3. Regime climatology: days/yr, monthly, run lengths, interannual,
     physical validation vs METAR dust/haze and NW wind fraction.
  4. Error budget: reanalysis-minus-station daily daytime-mean error in
     temp, RH, wind, wet-bulb, and (common-radiation) WBGT, stratified by
     regime. Mean bias with 95% moving-block-bootstrap CIs; RMSE; share of
     days |WBGT error| > 1 C.
  5. Operational translation: ACGIH work/rest band assigned from the
     reanalysis vs from the station - misclassification rate by regime.

Caveats are printed at the end and belong in any write-up.

Run:  python scripts/regime_climatology_study.py
"""

import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.heat_stress import allowable_work_fraction
from src.psychro import wet_bulb_from_dewpoint, wet_bulb_stull
from src.wbgt import wbgt_liljegren_c

RNG = np.random.default_rng(20260908)
DAY_LO, DAY_HI = 10, 17
WARM_MONTHS = [4, 5, 6, 7, 8, 9, 10]
NW_LO, NW_HI = 290.0, 350.0        # Shamal wind sector
PRIMARY_DELTA = 8.0
BLOCK = 5                          # moving-block bootstrap block length (days)
N_BOOT = 2000


# ---------------------------------------------------------------- helpers
def moving_block_ci(values: np.ndarray, stat=np.mean, n_boot=N_BOOT,
                    block=BLOCK, alpha=0.05):
    """95% CI for `stat` under serial dependence (moving-block bootstrap)."""
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    n = len(v)
    if n < block * 2:
        return (np.nan, np.nan)
    n_blocks = int(np.ceil(n / block))
    starts_pool = np.arange(0, n - block + 1)
    out = np.empty(n_boot)
    for i in range(n_boot):
        s = RNG.choice(starts_pool, size=n_blocks, replace=True)
        samp = np.concatenate([v[a:a + block] for a in s])[:n]
        out[i] = stat(samp)
    return tuple(np.percentile(out, [100 * alpha / 2, 100 * (1 - alpha / 2)]))


def diff_in_means_ci(series_full: np.ndarray, mask_regime: np.ndarray,
                     n_boot=N_BOOT, block=BLOCK):
    """CI for mean(regime) - mean(non-regime) with block resampling that
    preserves the day ordering (mask is resampled with the values)."""
    v = np.asarray(series_full, dtype=float)
    m = np.asarray(mask_regime, dtype=bool)
    ok = ~np.isnan(v)
    v, m = v[ok], m[ok]
    n = len(v)
    if n < block * 4 or m.sum() < 10 or (~m).sum() < 10:
        return (np.nan, (np.nan, np.nan))
    n_blocks = int(np.ceil(n / block))
    starts = np.arange(0, n - block + 1)
    out = np.empty(n_boot)
    for i in range(n_boot):
        s = RNG.choice(starts, size=n_blocks, replace=True)
        idx = np.concatenate([np.arange(a, a + block) for a in s])[:n]
        vs, ms = v[idx], m[idx]
        if ms.sum() < 5 or (~ms).sum() < 5:
            out[i] = np.nan
            continue
        out[i] = vs[ms].mean() - vs[~ms].mean()
    out = out[~np.isnan(out)]
    return float(np.mean(out)), tuple(np.percentile(out, [2.5, 97.5]))


def run_lengths(dates_sorted, flag):
    """Distribution of consecutive-day run lengths where flag is True."""
    lens = []
    cur = 0
    prev = None
    for dt, f in zip(dates_sorted, flag):
        if f and (prev is None or (dt - prev).days == 1):
            cur += 1
        elif f:
            lens.append(cur) if cur else None
            cur = 1
        else:
            if cur:
                lens.append(cur)
            cur = 0
        prev = dt
    if cur:
        lens.append(cur)
    return np.array(lens)


# ---------------------------------------------------------------- load
def load_daily():
    mt = pd.read_csv(REPO / "data" / "othh_metar_hourly.csv")
    mt["time"] = pd.to_datetime(mt["time"], utc=True)
    mt["tw"] = wet_bulb_from_dewpoint(mt["temp_c"].to_numpy(),
                                      mt["dewpoint_c"].to_numpy())

    rn = pd.read_csv(REPO / "data" / "doha_wbgt_16yr.csv")
    rn["time"] = pd.to_datetime(rn["time"], utc=True)
    rn["tw"] = wet_bulb_stull(rn["temperature_2m"].to_numpy(),
                              rn["relative_humidity_2m"].to_numpy())
    # station WBGT using COMMON (reanalysis) radiation + geometry, so the
    # station-vs-grid WBGT gap reflects T/RH/wind/pressure only.
    j = mt.merge(rn[["time", "solar_wm2", "direct_wm2", "cos_zenith",
                     "wbgt_c", "temperature_2m", "relative_humidity_2m",
                     "wind_speed_ms", "surface_pressure", "tw"]],
                 on="time", how="inner", suffixes=("_mt", "_rn"))
    # station WBGT uses reanalysis surface pressure (METAR MSLP has many
    # gaps; pressure changes WBGT by <0.1 C so this is immaterial and
    # keeps T/RH/wind as the only station-vs-grid difference).
    j["wbgt_station"] = wbgt_liljegren_c(
        temp_c=j["temp_c"].to_numpy(), rh_pct=j["rh_pct"].to_numpy(),
        pressure_hpa=j["surface_pressure"].to_numpy(),
        wind_speed_10m_ms=j["wind_speed_ms_mt"].to_numpy(),
        shortwave_wm2=np.nan_to_num(j["solar_wm2"].to_numpy()),
        direct_wm2=np.nan_to_num(j["direct_wm2"].to_numpy()),
        cos_zenith=j["cos_zenith"].to_numpy())

    j["local"] = j["time"].dt.tz_convert("Asia/Qatar")
    j["date"] = j["local"].dt.date
    j["lh"] = j["local"].dt.hour
    j["nw"] = j["wind_dir_deg"].between(NW_LO, NW_HI)
    d = j[(j["lh"] >= DAY_LO) & (j["lh"] <= DAY_HI)
          & j["local"].dt.month.isin(WARM_MONTHS)]

    g = d.groupby("date")
    daily = pd.DataFrame({
        # station daytime means
        "st_rh": g["rh_pct"].mean(), "st_t": g["temp_c"].mean(),
        "st_tw": g["tw_mt"].mean(), "st_wind": g["wind_speed_ms_mt"].mean(),
        "st_tmax": g["temp_c"].max(), "st_twmax": g["tw_mt"].max(),
        "nw_frac": g["nw"].mean(),
        "dust_frac": g["is_dust"].mean(), "haze_frac": g["is_haze"].mean(),
        "min_vis": g["visibility_km"].min(),
        # reanalysis daytime means
        "rn_rh": g["relative_humidity_2m"].mean(), "rn_t": g["temperature_2m"].mean(),
        "rn_tw": g["tw_rn"].mean(), "rn_wind": g["wind_speed_ms_rn"].mean(),
        # WBGT (common radiation)
        "wbgt_rn": g["wbgt_c"].mean(), "wbgt_st": g["wbgt_station"].mean(),
    }).dropna(subset=["st_rh", "rn_rh"])
    daily.index = pd.to_datetime(daily.index)
    return daily.sort_index()


# ---------------------------------------------------------------- regime
def add_regime(daily: pd.DataFrame, delta: float, wind_gate: bool) -> pd.Series:
    doy = daily.index.dayofyear.to_numpy()
    yr = daily.index.year.to_numpy()
    rh = daily["st_rh"].to_numpy()
    clim = np.full(len(daily), np.nan)
    for u in np.unique(doy):
        m = doy == u
        ys, vs = yr[m], rh[m]
        for k in range(len(ys)):                 # leave-current-year-out mean
            other = vs[ys != ys[k]]
            if len(other):
                clim[np.where(m)[0][k]] = other.mean()
    anom = rh - clim
    flag = anom < -delta
    if wind_gate:
        flag = flag & (daily["st_wind"].to_numpy() > daily["st_wind"].median())
    return pd.Series(flag, index=daily.index, name="regime"), pd.Series(anom, index=daily.index)


# ---------------------------------------------------------------- report
def main():
    daily = load_daily()
    yrs = sorted(daily.index.year.unique())
    print(f"Daily warm-season records: {len(daily)}  ({yrs[0]}-{yrs[-1]}, "
          f"{daily.index.year.nunique()} yr)\n")

    regime, anom = add_regime(daily, PRIMARY_DELTA, wind_gate=False)
    daily["regime"] = regime.values
    n_reg = int(regime.sum())
    print(f"=== 1. Regime definition & climatology  (RH anomaly < -{PRIMARY_DELTA:.0f} pts "
          f"vs leave-year-out day-of-year climatology) ===")
    print(f"  regime days: {n_reg}  ({n_reg/daily.index.year.nunique():.1f}/yr, "
          f"{n_reg/len(daily)*100:.1f}% of warm-season days)")
    by_m = daily.groupby(daily.index.month)["regime"].agg(["sum", "mean"])
    print("  by month:  " + "  ".join(
        f"{pd.Timestamp(2020, m, 1):%b}:{int(r['sum'])}" for m, r in by_m.iterrows()))
    by_y = daily.groupby(daily.index.year)["regime"].sum()
    print("  by year:   " + "  ".join(f"{y}:{int(c)}" for y, c in by_y.items()))
    rl = run_lengths(list(daily.index), daily["regime"].to_numpy())
    if len(rl):
        print(f"  episodes: {len(rl)}  (mean {rl.mean():.1f} d, max {rl.max()} d, "
              f"single-day {int((rl==1).sum())})")

    print("\n=== 2. Physical validation (regime vs normal warm-season days) ===")
    r, nr = daily[daily.regime], daily[~daily.regime]
    for col, lab, f in [("dust_frac", "hrs with dust (%)", 100),
                        ("haze_frac", "hrs with haze (%)", 100),
                        ("min_vis", "min visibility (km)", 1),
                        ("nw_frac", "daytime hrs wind NW (%)", 100),
                        ("st_wind", "station wind (m/s)", 1),
                        ("st_rh", "station RH (%)", 1),
                        ("st_tmax", "station Tmax (C)", 1),
                        ("st_twmax", "station wet-bulb max (C)", 1)]:
        print(f"  {lab:<26} regime {r[col].mean()*f:6.1f}   normal {nr[col].mean()*f:6.1f}")

    print("\n=== 3. Gridded-product error budget  (reanalysis minus station, "
          "daily daytime mean) ===")
    print(f"  {'variable':<16}{'regime bias [95% CI]':<28}{'normal bias':<16}"
          f"{'Δ (regime-normal) [95% CI]':<30}{'RMSE r/n':>12}")
    for col_rn, col_st, lab, unit in [
        ("rn_t", "st_t", "air temp", "C"),
        ("rn_rh", "st_rh", "rel. humidity", "%"),
        ("rn_wind", "st_wind", "wind speed", "m/s"),
        ("rn_tw", "st_tw", "wet-bulb", "C"),
        ("wbgt_rn", "wbgt_st", "WBGT*", "C"),
    ]:
        err = (daily[col_rn] - daily[col_st]).to_numpy()
        rb = err[daily.regime.to_numpy()]
        nb = err[~daily.regime.to_numpy()]
        rlo, rhi = moving_block_ci(rb)
        dmean, (dlo, dhi) = diff_in_means_ci(err, daily.regime.to_numpy())
        rmse_r = np.sqrt(np.nanmean(rb ** 2))
        rmse_n = np.sqrt(np.nanmean(nb ** 2))
        print(f"  {lab:<16}{f'{np.nanmean(rb):+.2f} [{rlo:+.2f},{rhi:+.2f}]':<28}"
              f"{f'{np.nanmean(nb):+.2f}':<16}"
              f"{f'{dmean:+.2f} [{dlo:+.2f},{dhi:+.2f}]':<30}"
              f"{f'{rmse_r:.2f}/{rmse_n:.2f}':>12}")
    we = np.abs(daily["wbgt_rn"] - daily["wbgt_st"]).to_numpy()
    print(f"\n  |WBGT* error| > 1.0 C:  regime {np.mean(we[daily.regime.to_numpy()]>1)*100:.0f}% "
          f"of days   normal {np.mean(we[~daily.regime.to_numpy()]>1)*100:.0f}%")
    print(f"  |WBGT* error| > 1.5 C:  regime {np.mean(we[daily.regime.to_numpy()]>1.5)*100:.0f}% "
          f"   normal {np.mean(we[~daily.regime.to_numpy()]>1.5)*100:.0f}%")

    print("\n=== 4. Operational translation: ACGIH work/rest band "
          "(moderate work, acclimatized) ===")
    band_rn = allowable_work_fraction(daily["wbgt_rn"].to_numpy(), "moderate", True)
    band_st = allowable_work_fraction(daily["wbgt_st"].to_numpy(), "moderate", True)
    mis = band_rn != band_st
    over = band_rn > band_st                      # reanalysis too permissive (unsafe)
    for lab, m in [("regime days", daily.regime.to_numpy()),
                   ("normal days", ~daily.regime.to_numpy())]:
        print(f"  {lab:<12}  band misclassified {np.mean(mis[m])*100:4.1f}%   "
              f"of which reanalysis TOO PERMISSIVE {np.mean(over[m])*100:4.1f}%")

    print("\n=== 5. Robustness ===")
    for dlt in (6, 8, 10, 12):
        rg, _ = add_regime(daily, float(dlt), wind_gate=False)
        err = (daily["wbgt_rn"] - daily["wbgt_st"]).to_numpy()
        dmean, (dlo, dhi) = diff_in_means_ci(err, rg.to_numpy())
        print(f"  DELTA={dlt:<3} -> {int(rg.sum()):3d} regime days, "
              f"WBGT* bias gap {dmean:+.2f} C [{dlo:+.2f},{dhi:+.2f}]")
    rg_w, _ = add_regime(daily, PRIMARY_DELTA, wind_gate=True)
    err = (daily["wbgt_rn"] - daily["wbgt_st"]).to_numpy()
    dmean, (dlo, dhi) = diff_in_means_ci(err, rg_w.to_numpy())
    print(f"  +NW-wind gate -> {int(rg_w.sum())} regime days, "
          f"WBGT* bias gap {dmean:+.2f} C [{dlo:+.2f},{dhi:+.2f}]")
    print("  leave-one-year-out regime frequency (days/yr):")
    freqs = daily.groupby(daily.index.year)["regime"].sum()
    print("   " + "  ".join(f"{y}:{int(c)}" for y, c in freqs.items())
          + f"   | mean {freqs.mean():.1f}  sd {freqs.std():.1f}")

    print("\n=== LIMITATIONS (carry into any write-up) ===")
    for line in [
        "Single station (OTHH) and one metro; not spatially general.",
        "Wet-bulb via Stull(2011): ~0.3 C RMS, up to ~1 C bias near 42 C; "
        "partly cancels in the reanalysis-minus-station difference.",
        "WBGT* uses common (reanalysis) radiation & solar geometry, so the "
        "error attributed here is the T/RH/wind/pressure component only "
        "(the dominant and regime-sensitive term).",
        "'Gridded product' = Open-Meteo reanalysis blend; ERA5 not yet "
        "cross-checked at this scale (targeted pull is the next robustness "
        "step).",
        "Regime defined by an RH-anomaly threshold; it is a screening "
        "proxy for Shamal / dry-advection episodes, validated against dust "
        "& NW wind but not against a synoptic catalogue.",
        "MSLP used as surface pressure for station WBGT (OTHH ~10 m; "
        "<1 hPa effect).",
        "12-year record: ~15 regime days/yr -> episode counts have wide "
        "sampling error; CIs are block-bootstrap and should be read as "
        "such.",
    ]:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
