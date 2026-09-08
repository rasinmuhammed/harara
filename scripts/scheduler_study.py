"""
scripts/scheduler_study.py

Walk-forward simulation: does RISK-OPTIMAL (CVaR) work/rest scheduling
under an uncertain WBGT forecast beat the alternatives, out of sample?

Policies, each given only information available at planning time:
  calendar        Qatar 17/2021 style fixed midday ban
  reactive        smart-reactive: coolest safe hours first (point forecast)
  deterministic   the CVaR LP with ONE scenario = the point forecast
  stochastic      the CVaR LP with K analog forecast scenarios
  clairvoyant     the CVaR LP with the TRUE realized WBGT  (oracle bound)

Each planned schedule is scored against the ACTUAL realized hourly WBGT
for that day (patched reanalysis). We report, per policy:
  - mean and 90th-pct peak thermal load  (lower = safer)
  - regret vs clairvoyant
  - % of days the work requirement was not met
with moving-block-bootstrap 95% CIs, for lead times of 24 / 48 / 72 h.

With --uncertainty gefs the scenarios come from the calibrated GEFS v12
reforecast lagged ensemble (src.forecast_uncertainty.GEFSEnsembleModel +
data/gefs_emos.json) instead of analog resampling, evaluated on the
GEFS x patched-WBGT overlap years. This answers the open question from
technical_report S8: does the STOCHASTIC (CVaR) layer beat the
deterministic optimiser once forecast spread grows honestly with lead?

Run:  python scripts/scheduler_study.py                       # analog (default)
      python scripts/scheduler_study.py --uncertainty gefs
"""

import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from src.forecast_uncertainty import AnalogResidualModel, GEFSEnsembleModel
from src.scheduler import (
    PHI_DEFAULT, WBGT_REF_DEFAULT,
    policy_calendar, policy_cvar, policy_deterministic,
    policy_clairvoyant, policy_reactive, realized_strain,
)
from src.solar import cos_solar_zenith_angle
from src.wbgt import wbgt_liljegren_c

DOHA_LAT, DOHA_LON = 25.27, 51.61
HOURS = np.arange(5, 20)                 # local working window 05:00-19:00
H = len(HOURS)
W_REQ = 9.0                              # required effective work-hours/day
WARM_MONTHS = [5, 6, 7, 8, 9]
K_SCEN = 120
BETA = 0.90
LEADS = [1, 2, 3]
RNG = np.random.default_rng(11)


def _fc_wbgt(df, n):
    g = lambda b: df[f"{b}_fc{n}"].to_numpy()
    return wbgt_liljegren_c(
        temp_c=g("temperature_2m"), rh_pct=g("relative_humidity_2m"),
        pressure_hpa=g("surface_pressure"), wind_speed_10m_ms=g("wind_speed_10m"),
        shortwave_wm2=np.nan_to_num(g("shortwave_radiation")),
        direct_wm2=np.nan_to_num(g("direct_radiation")),
        cos_zenith=df["cos_zenith"].to_numpy())


def load_day_grids():
    fc = pd.read_csv(REPO / "data" / "doha_forecast_archive.csv")
    fc["time"] = pd.to_datetime(fc["time"], utc=True)
    fc["cos_zenith"] = cos_solar_zenith_angle(pd.DatetimeIndex(fc["time"]),
                                              DOHA_LAT, DOHA_LON)
    tr = pd.read_csv(REPO / "data" / "doha_wbgt_16yr.csv")[["time", "wbgt_c"]]
    tr["time"] = pd.to_datetime(tr["time"], utc=True)
    df = fc.merge(tr.rename(columns={"wbgt_c": "truth"}), on="time", how="inner")
    for n in LEADS:
        df[f"fcw{n}"] = _fc_wbgt(df, n)
    df["local"] = df["time"].dt.tz_convert("Asia/Qatar")
    df["date"] = df["local"].dt.normalize().dt.tz_localize(None)
    df["lh"] = df["local"].dt.hour
    df["month"] = df["local"].dt.month
    d = df[df["lh"].isin(HOURS) & df["month"].isin(WARM_MONTHS)]

    # pivot to one row per day with H-length vectors
    days = {}
    for date, g in d.groupby("date"):
        g = g.set_index("lh").reindex(HOURS)
        if g["truth"].isna().any():
            continue
        rec = {"date": date, "month": int(g["month"].dropna().iloc[0]),
               "truth": g["truth"].to_numpy(),
               "local_hour": HOURS.astype(float)}
        okall = True
        for n in LEADS:
            fv = g[f"fcw{n}"].to_numpy()
            if np.isnan(fv).any():
                okall = False
                break
            rec[f"fc{n}"] = fv
        if okall:
            days[date] = rec
    return pd.DataFrame(list(days.values())).sort_values("date").reset_index(drop=True)


def block_ci(x, stat=np.mean, block=7, n=2000):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    m = len(x)
    if m < block * 3:
        return (np.nan, np.nan)
    starts = np.arange(0, m - block + 1)
    nb = int(np.ceil(m / block))
    out = [stat(np.concatenate([x[a:a + block]
           for a in RNG.choice(starts, nb)])[:m]) for _ in range(n)]
    return tuple(np.percentile(out, [2.5, 97.5]))


def main():
    days = load_day_grids()
    n_days = len(days)
    split = int(n_days * 0.45)                 # walk-forward: test on later 55%
    test = days.iloc[split:].reset_index(drop=True)
    print(f"days: {n_days} warm-season (May-Sep), test on {len(test)} "
          f"({test['date'].min().date()}..{test['date'].max().date()})\n")

    allowed = np.ones(H, dtype=bool)           # every window hour is workable

    for lead in LEADS:
        recs = []
        model = AnalogResidualModel(HOURS)
        for i, row in test.iterrows():
            d = row["date"]
            # (re)fit analog model on ALL days strictly before d
            hist = days[days["date"] < d]
            tab = {"date": hist["date"].values, "month": hist["month"].values}
            for h_i, h in enumerate(HOURS):
                tab[f"fc_{h}"] = np.array([r[h_i] for r in hist[f"fc{lead}"]])
                tab[f"resid_{h}"] = np.array([t[h_i] - r[h_i] for t, r
                                              in zip(hist["truth"], hist[f"fc{lead}"])])
            model._days = []
            model.fit(pd.DataFrame(tab))

            fc = row[f"fc{lead}"]
            truth = row["truth"]
            scen = model.scenarios(np.datetime64(d), row["month"], fc,
                                   k=K_SCEN, month_window=1)

            pol_w = {
                "calendar": policy_calendar(row["local_hour"], allowed),
                "reactive": policy_reactive(fc, allowed, W_REQ),
                "deterministic": policy_deterministic(fc, allowed, W_REQ, beta=BETA),
                "stochastic": policy_cvar(scen, allowed, W_REQ, beta=BETA),
                "clairvoyant": policy_clairvoyant(truth, allowed, W_REQ, beta=BETA),
            }
            row_out = {"date": d}
            for name, w in pol_w.items():
                row_out[f"strain_{name}"] = realized_strain(w, truth)
                row_out[f"short_{name}"] = max(0.0, W_REQ - w.sum())
            recs.append(row_out)
        R = pd.DataFrame(recs)

        clair = R["strain_clairvoyant"].to_numpy()
        print(f"================  LEAD {24*lead}h  (n={len(R)} test days)  ================")
        print(f"  {'policy':<14}{'mean strain':>13}{'  [95% CI]':<18}"
              f"{'p90 strain':>12}{'mean regret':>13}{'unmet %':>9}")
        for name in ["calendar", "reactive", "deterministic", "stochastic", "clairvoyant"]:
            s = R[f"strain_{name}"].to_numpy()
            lo, hi = block_ci(s)
            regret = np.nanmean(s - clair)
            unmet = np.mean(R[f"short_{name}"].to_numpy() > 0.05) * 100
            print(f"  {name:<14}{np.nanmean(s):>13.2f}"
                  f"{f'  [{lo:.2f},{hi:.2f}]':<18}"
                  f"{np.nanpercentile(s,90):>12.2f}{regret:>13.2f}{unmet:>8.0f}%")
        # paired improvement: stochastic vs deterministic and vs calendar
        for base in ["deterministic", "calendar", "reactive"]:
            dpair = R[f"strain_{base}"] - R["strain_stochastic"]
            lo, hi = block_ci(dpair.to_numpy())
            print(f"    stochastic vs {base:<13}: mean strain reduction "
                  f"{dpair.mean():+.2f}  [{lo:+.2f},{hi:+.2f}]  "
                  f"({dpair.mean()/R[f'strain_{base}'].mean()*100:+.0f}%)")
        print()

    print("=== LIMITATIONS ===")
    for L in [
        "Uncertainty from analog residual resampling of one 4-yr archive; "
        "run --uncertainty gefs for the calibrated GEFS ensemble.",
        "Single crew, single workload class, fixed acclimatization; "
        "thermal load is a 1-state passive-retention integrator, not a "
        "multi-node physiological model.",
        "Work requirement, WBGT_ref, phi and beta are fixed here; a "
        "sensitivity sweep belongs in the full study.",
        "Realized strain scored against the patched reanalysis WBGT (its "
        "own ~1 C uncertainty applies equally to all policies).",
        "No intraday re-planning (MPC): each day is planned once at the "
        "given lead. MPC is expected to widen the stochastic advantage.",
        "Warm season May-Sep only; the calendar policy is evaluated on the "
        "days its ban window actually applies.",
    ]:
        print(f"  - {L}")


def run_gefs():
    """Scheduler comparison with the calibrated GEFS ensemble, on the
    GEFS x patched-WBGT overlap. Answers: does stochastic beat
    deterministic once spread grows honestly with lead?"""
    from src.emos import EMOS

    emos_path = REPO / "data" / "gefs_emos.json"
    emos = EMOS.from_dict(json.loads(emos_path.read_text())) if emos_path.exists() else None
    if emos is None:
        print("no data/gefs_emos.json - run scripts/gefs_calibration.py first "
              "(using RAW ensemble)", file=sys.stderr)
    ens = GEFSEnsembleModel(REPO / "data" / "gefs", emos=emos)

    # truth grid: patched WBGT 12-18 local, extrapolated across HOURS
    w = pd.read_csv(REPO / "data" / "doha_wbgt_16yr.csv", usecols=["time", "wbgt_c"])
    w["local"] = pd.to_datetime(w["time"], utc=True).dt.tz_convert("Asia/Qatar")
    w["d"] = w["local"].dt.date
    w["lh"] = w["local"].dt.hour + w["local"].dt.minute / 60.0
    wd = w[(w["lh"] >= 5) & (w["lh"] < 20)]

    dates = sorted(set(ens.df["vdate"]) & set(wd["d"]))
    if len(dates) < 20:
        print(f"only {len(dates)} GEFS x truth days - let the backfill run",
              file=sys.stderr)
        if not dates:
            return
    split = int(len(dates) * 0.45)
    test = dates[split:]
    print(f"GEFS scheduler: {len(dates)} overlap days, test on {len(test)} "
          f"({test[0]}..{test[-1]})\n")
    allowed = np.ones(H, dtype=bool)

    for fday in (1, 2, 3):
        rows = []
        for d in test:
            g = wd[wd["d"] == d].set_index("lh").reindex(HOURS)
            if g["wbgt_c"].isna().any():
                continue
            truth = g["wbgt_c"].to_numpy()
            scen = ens.scenarios(d, HOURS, fday=fday)
            if scen.shape[0] < 3:
                continue
            point = scen.mean(0)
            pol = {
                "calendar": policy_calendar(HOURS.astype(float), allowed),
                "reactive": policy_reactive(point, allowed, W_REQ),
                "deterministic": policy_deterministic(point, allowed, W_REQ, beta=BETA),
                "stochastic": policy_cvar(scen, allowed, W_REQ, beta=BETA),
                "clairvoyant": policy_clairvoyant(truth, allowed, W_REQ, beta=BETA),
            }
            rows.append({n: realized_strain(wv, truth) for n, wv in pol.items()})
        R = pd.DataFrame(rows)
        if R.empty:
            print(f"fday +{fday}: no scorable days"); continue
        clair = R["clairvoyant"].to_numpy()
        print(f"====  forecast day +{fday}  (n={len(R)})  ====")
        for name in ["calendar", "reactive", "deterministic", "stochastic", "clairvoyant"]:
            s = R[name].to_numpy()
            lo, hi = block_ci(s)
            print(f"  {name:<14}{np.nanmean(s):>8.2f}  [{lo:.2f},{hi:.2f}]"
                  f"   p90 {np.nanpercentile(s,90):>6.2f}   "
                  f"regret {np.nanmean(s-clair):+.2f}")
        d = R["deterministic"] - R["stochastic"]
        lo, hi = block_ci(d.to_numpy())
        verdict = ("stochastic BETTER" if lo > 0 else
                   "no significant difference" if lo <= 0 <= hi else
                   "stochastic WORSE")
        print(f"  stochastic vs deterministic: {d.mean():+.2f} "
              f"[{lo:+.2f},{hi:+.2f}]  -> {verdict}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--uncertainty", choices=["analog", "gefs"], default="analog")
    args = ap.parse_args()
    if args.uncertainty == "gefs":
        run_gefs()
    else:
        main()
