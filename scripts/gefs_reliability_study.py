"""
scripts/gefs_reliability_study.py

The multi-year forecast-reliability study the technical report lists
as blocked for want of a homogeneous forecast archive. The question:

    Can we predict, at forecast-issue time, that the day's peak-WBGT
    forecast will be badly wrong?

Label  big_error(init, fday) = | EMOS mean peak - observed peak | > tau,
       tau = the 90th percentile of that absolute error over the training
       years (about a 10% base rate, defined causally).
Obs    = peak of patched-reanalysis WBGT over 12-18 local (its own ~1 C
       error, worse on dry-transition days - carried caveat from S5, so
       this predicts "GEFS-vs-reanalysis surprise", not "vs truth").

Features are issue-time only: ensemble peak level and its anomaly vs a
walk-forward day-of-year GEFS climatology, ensemble spread and member
range, GEFS RH mean and its anomaly (dry-advection proxy), wind, the
day-over-day change in the forecast, month and day-of-year.

Model = LightGBM classifier, held out by year (train on years strictly
before the scored year, >= 3). Baselines: climatological base rate and a
spread-only decile rule. PR-AUC is primary (imbalanced); block-bootstrap
95 % CI.

Run:  python scripts/gefs_reliability_study.py
"""

import pathlib
import sys
import warnings

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

warnings.filterwarnings("ignore")
import lightgbm as lgb
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss

from fetch_gefs_reforecast import compute_gefs_wbgt, load_gefs

RNG = np.random.default_rng(13)
MIN_TRAIN_YEARS = 3
LGB = dict(objective="binary", n_estimators=400, learning_rate=0.03,
           num_leaves=31, subsample=0.8, colsample_bytree=0.8,
           min_child_samples=25, n_jobs=-1, verbose=-1)


def block_ci(x, stat, block=7, n=1500):
    x = np.asarray(x)
    idx = np.arange(len(x))
    if len(x) < block * 3:
        return (np.nan, np.nan)
    starts = np.arange(0, len(x) - block + 1)
    nb = int(np.ceil(len(x) / block))
    vals = []
    for _ in range(n):
        take = np.concatenate([idx[a:a + block] for a in RNG.choice(starts, nb)])[:len(x)]
        try:
            vals.append(stat(take))
        except ValueError:
            pass
    return tuple(np.percentile(vals, [2.5, 97.5])) if vals else (np.nan, np.nan)


def build_table():
    gefs = load_gefs()
    gefs["wbgt"], _ = compute_gefs_wbgt(gefs)
    gefs["local"] = gefs["valid_time"] + pd.Timedelta(hours=3)
    gefs["ldate"] = gefs["local"].dt.date

    # per (init, fday): ensemble-mean over members, then day-peak across leads
    per_lead = (gefs.groupby(["init_time", "fday", "lead_h", "valid_time"])
                    .agg(wbgt_m=("wbgt", "mean"), wbgt_sd=("wbgt", "std"),
                         wbgt_min=("wbgt", "min"), wbgt_max=("wbgt", "max"),
                         rh_m=("rh_pct", "mean"), wind_m=("wind_ms", "mean"))
                    .reset_index())
    rows = []
    for (it, fd), g in per_lead.groupby(["init_time", "fday"]):
        pk = g.loc[g["wbgt_m"].idxmax()]
        rows.append(dict(
            init_time=it, fday=int(fd),
            ldate=(pd.Timestamp(it) + pd.Timedelta(days=int(fd))).date(),
            fc_peak=pk.wbgt_m, ens_spread=g["wbgt_sd"].max(),
            ens_range=(g["wbgt_max"] - g["wbgt_min"]).max(),
            rh_mean=g["rh_m"].mean(), wind_mean=g["wind_m"].mean(),
        ))
    F = pd.DataFrame(rows)
    F["month"] = pd.to_datetime(F["ldate"]).dt.month
    F["year"] = pd.to_datetime(F["ldate"]).dt.year
    F["doy"] = pd.to_datetime(F["ldate"]).dt.dayofyear

    # observed peak WBGT 12-18 local from patched reanalysis
    tr = pd.read_csv(REPO / "data" / "doha_wbgt_16yr.csv", usecols=["time", "wbgt_c"])
    tr["t"] = pd.to_datetime(tr["time"], utc=True).dt.tz_convert("Asia/Qatar")
    tr = tr[(tr["t"].dt.hour >= 12) & (tr["t"].dt.hour <= 18)]
    obs = tr.groupby(tr["t"].dt.date)["wbgt_c"].max().rename("obs_peak")
    F = F.merge(obs, left_on="ldate", right_index=True, how="inner")

    # walk-forward day-of-year climatologies (expanding, leak-free) of the
    # GEFS forecast peak and RH for the anomaly features
    F = F.sort_values("ldate").reset_index(drop=True)
    for col, out in [("fc_peak", "fc_peak_anom"), ("rh_mean", "rh_anom")]:
        clim = np.full(len(F), np.nan)
        seen = {}
        for i, r in F.iterrows():
            k = (r["fday"], pd.Timestamp(r["ldate"]).dayofyear)
            if k in seen and seen[k]:
                clim[i] = np.mean(seen[k])
            seen.setdefault(k, []).append(r[col])
        F[out] = F[col] - clim
    # day-over-day change in the forecast peak, same fday
    F["dfc_prevday"] = F.groupby("fday")["fc_peak"].diff()
    F["abs_err"] = (F["fc_peak"] - F["obs_peak"]).abs()
    return F.dropna(subset=["fc_peak_anom", "rh_anom", "dfc_prevday"]).reset_index(drop=True)


FEATS = ["fday", "fc_peak", "ens_spread", "ens_range", "rh_mean", "rh_anom",
         "wind_mean", "fc_peak_anom", "dfc_prevday", "month",
         "doy_sin", "doy_cos"]


def main():
    F = build_table()
    if len(F) == 0 or F["year"].nunique() < 2:
        n_yr = 0 if len(F) == 0 else F["year"].nunique()
        print(f"reliability study needs >= 2 GEFS x patched-WBGT overlap years "
              f"for the anomaly features ({n_yr} present) - let the backfill run.")
        return
    F["doy_sin"] = np.sin(2 * np.pi * F["doy"] / 365.25)
    F["doy_cos"] = np.cos(2 * np.pi * F["doy"] / 365.25)
    years = sorted(F["year"].unique())
    print(f"reliability table: {len(F)} (init x fday) rows, years "
          f"{years[0]}-{years[-1]} ({len(years)})")
    scored = [y for y in years if sum(z < y for z in years) >= MIN_TRAIN_YEARS]
    if not scored:
        print(f"\n< {MIN_TRAIN_YEARS+1} overlap years classifier not run. "
              f"Descriptive feature/target association instead:")
        tau = F["abs_err"].quantile(0.9)
        F["big"] = (F["abs_err"] > tau).astype(int)
        for c in ["ens_spread", "rh_anom", "fc_peak_anom", "dfc_prevday"]:
            r = F[[c, "big"]].corr().iloc[0, 1]
            print(f"  corr({c:<14}, big_error) = {r:+.2f}")
        print(f"  base rate (|err|>{tau:.1f} C) = {F['big'].mean()*100:.0f}%")
        return

    preds, labels, groups = [], [], []
    spread_pred = []
    for y in scored:
        tr = F[F["year"] < y].copy()
        te = F[F["year"] == y].copy()
        tau = tr["abs_err"].quantile(0.9)
        tr["big"] = (tr["abs_err"] > tau).astype(int)
        te_big = (te["abs_err"] > tau).astype(int).to_numpy()
        m = lgb.LGBMClassifier(**LGB)
        m.fit(tr[FEATS], tr["big"])
        p = m.predict_proba(te[FEATS])[:, 1]
        # spread-only decile rule
        thr = tr["ens_spread"].quantile(0.9)
        sp = (te["ens_spread"] > thr).astype(float).to_numpy()
        preds.append(p); labels.append(te_big); spread_pred.append(sp)
        groups.append(np.full(len(te), y))
    P = np.concatenate(preds); Y = np.concatenate(labels)
    SP = np.concatenate(spread_pred)
    base = Y.mean()

    def _ap(idx):
        return average_precision_score(Y[idx], P[idx])
    def _ap_sp(idx):
        return average_precision_score(Y[idx], SP[idx])

    ap = average_precision_score(Y, P)
    lo, hi = block_ci(np.arange(len(Y)), lambda ix: average_precision_score(Y[ix], P[ix]))
    ap_sp = average_precision_score(Y, SP)
    auc = roc_auc_score(Y, P)
    brier = brier_score_loss(Y, P)

    print(f"\nscored years: {scored}   n={len(Y)}   positives={int(Y.sum())} "
          f"(base rate {base*100:.0f}%)\n")
    print(f"  LightGBM classifier   PR-AUC {ap:.3f}  [{lo:.3f}, {hi:.3f}]   "
          f"ROC-AUC {auc:.3f}   Brier {brier:.3f}")
    print(f"  spread-decile rule    PR-AUC {ap_sp:.3f}")
    print(f"  climatological base   PR-AUC {base:.3f}")
    # recall at a usable precision
    order = np.argsort(-P)
    for target_prec in (0.5, 0.35, 0.25):
        k = 0
        for k in range(1, len(order) + 1):
            if Y[order[:k]].mean() < target_prec:
                break
        rec = Y[order[:max(k - 1, 1)]].sum() / Y.sum()
        print(f"  at precision ~{target_prec:.2f}: recall {rec:.2f} "
              f"(flags {max(k-1,1)}/{len(Y)} days)")

    # calibration
    print("  calibration (pred prob -> observed frequency):")
    bins = pd.cut(P, [0, .05, .1, .2, .4, 1.01])
    for b in bins.categories:
        mask = bins == b
        if mask.sum() > 10:
            print(f"    {str(b):<12} pred~{P[mask].mean():.2f}  obs {Y[mask].mean():.2f}  (n={mask.sum()})")

    print("\n=== LIMITATIONS ===")
    for L in [
        f"Only {len(years)} GEFS x patched-WBGT overlap years; {len(scored)} "
        f"scored -> PR-AUC CI is wide and one bad summer moves it.",
        "Label uses patched-reanalysis WBGT as 'truth' (S5 caveat): this "
        "predicts GEFS-vs-reanalysis divergence, not GEFS-vs-observation.",
        "tau is the 90th error percentile per training set -> the positive "
        "rate drifts slightly year to year by construction.",
        "Peak-of-day framing (12-18 local); a per-hour reliability model is "
        "the natural extension once more years are in.",
    ]:
        print(f"  - {L}")


if __name__ == "__main__":
    main()
