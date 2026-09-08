"""
scripts/gefs_ensemble_check.py

Two checks on the GEFS v12 reforecast lagged ensemble
(src.forecast_uncertainty.GEFSEnsembleModel), against the patched
reanalysis WBGT as truth:

  1. SPREAD-SKILL. A well-calibrated ensemble has ensemble spread
     (across-member SD) approximately equal to the RMSE of its mean. We
     report both, by forecast day, plus the rank-histogram flatness
     (fraction of truth values in the outer ranks).

  2. SCHEDULER. Feed the GEFS ensemble vs the analog model vs the
     deterministic point forecast into the CVaR scheduler on the same
     days; compare realised peak thermal load.

Small-sample: this runs on whatever GEFS summers have been fetched
(scripts/fetch_gefs_reforecast.py). The full 2000-2019 backfill turns
this from a wiring check into a result.

Run:  python scripts/gefs_ensemble_check.py --gefs data/gefs_2015.csv data/gefs_2018.csv
"""

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.forecast_uncertainty import GEFSEnsembleModel, AnalogResidualModel
from src.scheduler import policy_cvar, policy_deterministic, realized_strain
from src.solar import cos_solar_zenith_angle
from src.wbgt import wbgt_liljegren_c

HOURS = np.arange(5, 20)
H = len(HOURS)
W_REQ = 9.0
DOHA_LAT, DOHA_LON = 25.27, 51.61


def truth_grid(valid_date, wbgt_df):
    """Realised WBGT on the HOURS local grid for one date, or None."""
    lo = pd.Timestamp(valid_date)
    m = (wbgt_df["local_date"] == lo.date())
    g = wbgt_df.loc[m].set_index("lhour").reindex(HOURS)
    if g["wbgt_c"].isna().any():
        return None
    return g["wbgt_c"].to_numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gefs", nargs="+", default=["data/gefs_2015.csv"])
    args = ap.parse_args()

    gefs_files = [REPO / f for f in args.gefs if (REPO / f).exists()]
    if not gefs_files:
        raise SystemExit("No GEFS files found - run scripts/fetch_gefs_reforecast.py")
    gefs = pd.concat([pd.read_csv(f, parse_dates=["init_time", "valid_time"])
                      for f in gefs_files], ignore_index=True)
    tmp = REPO / "data" / "_gefs_concat.csv"
    gefs.to_csv(tmp, index=False)
    ens = GEFSEnsembleModel(tmp)

    w = pd.read_csv(REPO / "data" / "doha_wbgt_16yr.csv", usecols=["time", "wbgt_c"])
    w["time"] = pd.to_datetime(w["time"], utc=True)
    w["local"] = w["time"].dt.tz_convert("Asia/Qatar")
    w["local_date"] = w["local"].dt.date
    w["lhour"] = w["local"].dt.hour + w["local"].dt.minute / 60.0

    dates = sorted(ens.df["vdate"].unique())
    print(f"GEFS ensemble check: {len(dates)} working days "
          f"({dates[0]} .. {dates[-1]})\n")

    # ---- 1. spread-skill ----
    by_fday = {1: [], 2: [], 3: []}
    ranks = []
    sched_rows = []
    for d in dates:
        tr = truth_grid(d, w)
        if tr is None:
            continue
        # per-forecast-day ensemble (members of one init only)
        sub = ens.df[ens.df["vdate"] == d]
        for fday in (1, 2, 3):
            gg = sub[sub["fday"] == fday]
            if gg["member"].nunique() < 3:
                continue
            # member trajectories on the grid
            rows = []
            for _, m in gg.groupby("member"):
                m = m.sort_values("lhour")
                if len(m) < 2:
                    continue
                rows.append(np.interp(HOURS, m["lhour"], m["wbgt"]))
            if len(rows) < 3:
                continue
            E = np.vstack(rows)                       # (members, H)
            emean = E.mean(0)
            # daytime window 9-17 for scoring
            win = (HOURS >= 9) & (HOURS <= 17)
            rmse = np.sqrt(np.mean((emean[win] - tr[win]) ** 2))
            spread = np.mean(E[:, win].std(0))
            by_fday[fday].append((rmse, spread))
            # rank of truth among members at 14:00
            i14 = int(np.argmin(np.abs(HOURS - 14)))
            ranks.append((np.sum(E[:, i14] < tr[i14]), E.shape[0]))

        # ---- 2. scheduler on this day (forecast day +1 ensemble) ----
        scen = ens.scenarios(d, HOURS)
        if scen.shape[0] >= 3:
            point = scen.mean(0)
            allowed = np.ones(H, bool)
            w_gefs = policy_cvar(scen, allowed, W_REQ, beta=0.9)
            w_det = policy_deterministic(point, allowed, W_REQ, beta=0.9)
            sched_rows.append(dict(
                date=d,
                strain_gefs_cvar=realized_strain(w_gefs, tr),
                strain_deterministic=realized_strain(w_det, tr),
            ))

    print("Spread-skill by forecast day  (well-calibrated: spread ~ RMSE):")
    print(f"  {'fday':>5}{'n':>5}{'RMSE(mean)':>12}{'spread':>10}{'ratio':>8}")
    for fday in (1, 2, 3):
        v = np.array(by_fday[fday])
        if len(v):
            r, s = v[:, 0].mean(), v[:, 1].mean()
            print(f"  {fday:>5}{len(v):>5}{r:>12.2f}{s:>10.2f}{s / r:>8.2f}")

    if ranks:
        R = np.array([r / (n) for r, n in ranks])
        outer = np.mean((R < 0.15) | (R > 0.85))
        print(f"\n  rank histogram: {len(ranks)} cases, truth in outer 30% of "
              f"the ensemble {outer*100:.0f}% of the time "
              f"(flat calibration ~ 30%)")

    S = pd.DataFrame(sched_rows)
    if len(S):
        d = S["strain_deterministic"] - S["strain_gefs_cvar"]
        print(f"\nScheduler on {len(S)} days (forecast day +1):")
        print(f"  deterministic point forecast : mean realised strain "
              f"{S['strain_deterministic'].mean():.2f}")
        print(f"  GEFS-ensemble CVaR           : mean realised strain "
              f"{S['strain_gefs_cvar'].mean():.2f}  "
              f"(Δ {d.mean():+.2f}, {d.mean()/S['strain_deterministic'].mean()*100:+.0f}%)")
        print("  (small sample; the full backfill makes this a result, not a check)")

    tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
