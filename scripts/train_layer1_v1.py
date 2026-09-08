"""
scripts/train_layer1_v1.py

Layer 1, first version: a gradient-boosted model that forecasts Doha WBGT
24 / 48 / 72 h ahead from OBSERVATIONS ONLY (no NWP forecast input yet).

It must beat the run_first_result.py baselines - persistence and
walk-forward climatology - on the SAME out-of-sample rows, with the same
harness metrics. Evaluation is expanding-window walk-forward: every test
fold is strictly in the future of its training data.

Idea: don't predict WBGT from scratch. Decompose
    WBGT(T+h) ~= climatology(T+h) + persisted_anomaly(T) + correction
and let the model learn the correction (and how much anomaly persists),
given climatology, today's anomaly, recent trends, weather state, and the
target's calendar position as features.

What this is NOT yet: true NWP bias-correction (needs an archive of past
forecast runs). This obs-only model is the honest floor and later becomes
a component / fallback of the NWP version.

Run:  python scripts/train_layer1_v1.py --data data/doha_wbgt_16yr.csv
"""

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import lightgbm as lgb

from eval.harness import evaluate, walk_forward_splits
from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C as THR

LEADS = [24, 48, 72]

LGB_PARAMS = dict(
    objective="regression_l1",     # optimise MAE; robust to the heat tail
    n_estimators=1500,
    learning_rate=0.02,
    num_leaves=63,
    subsample=0.8, subsample_freq=1,
    colsample_bytree=0.8,
    min_child_samples=40,
    n_jobs=-1, verbose=-1,
)


# --------------------------------------------------------------------------
# Leak-safe climatology: for a given clock slot (mm-dd-HH) and year Y, the
# mean WBGT at that slot over all years STRICTLY BEFORE Y. Never sees Y or
# later, so it is safe to use as a feature at any row in year Y.
# --------------------------------------------------------------------------
def leak_safe_climatology(df: pd.DataFrame) -> pd.Series:
    key = df["time"].dt.strftime("%m-%d-%H")
    yr = df["time"].dt.year
    per = (pd.DataFrame({"key": key, "yr": yr, "w": df["wbgt_c"].to_numpy()})
           .groupby(["key", "yr"], as_index=False)["w"].mean()
           .sort_values(["key", "yr"]))
    csum = per.groupby("key")["w"].cumsum() - per["w"]     # sum over earlier yrs
    ccnt = per.groupby("key").cumcount()                   # count of earlier yrs
    per["clim"] = csum / ccnt.replace(0, np.nan)
    return per.set_index(["key", "yr"])["clim"]


def _clim_at(clim: pd.Series, times: pd.Series, cut_year: pd.Series) -> np.ndarray:
    """Climatology value for each `times` clock slot, using only years < the
    matching `cut_year` (we pass year(T) for both 'now' and 'target')."""
    key = times.dt.strftime("%m-%d-%H").to_numpy()
    mi = pd.MultiIndex.from_arrays([key, cut_year.to_numpy()])
    return clim.reindex(mi).to_numpy()


# --------------------------------------------------------------------------
# Features known at time T (no look-ahead).
# --------------------------------------------------------------------------
def build_features(df: pd.DataFrame, clim: pd.Series) -> pd.DataFrame:
    t = df["time"]
    w = df["wbgt_c"]
    f = pd.DataFrame(index=df.index)

    # persistence anchor + recent WBGT history
    for k in [0, 1, 3, 6, 12, 24, 48]:
        f[f"wbgt_lag{k}"] = w.shift(k)
    f["wbgt_chg_24"] = w - w.shift(24)
    f["wbgt_chg_prev24"] = w.shift(24) - w.shift(48)
    f["wbgt_roll24_mean"] = w.shift(1).rolling(24).mean()
    f["wbgt_roll24_max"] = w.shift(1).rolling(24).max()
    f["wbgt_roll24_min"] = w.shift(1).rolling(24).min()

    # recent weather drivers and their 24 h change
    for col, nm in [("temperature_2m", "temp"), ("relative_humidity_2m", "rh"),
                    ("wind_speed_ms", "wind"), ("solar_wm2", "solar")]:
        f[f"{nm}_lag0"] = df[col]
        f[f"{nm}_chg24"] = df[col] - df[col].shift(24)

    # anomaly of NOW vs its own climatology (years < year(T))
    clim_now = _clim_at(clim, t, t.dt.year)
    f["clim_now"] = clim_now
    f["anom_now"] = w.to_numpy() - clim_now
    return f


def per_lead_matrix(df, feat, clim, lead):
    t = df["time"]
    tgt_time = t + pd.Timedelta(hours=lead)

    X = feat.copy()
    clim_tgt = _clim_at(clim, tgt_time, t.dt.year)     # cut at year(T): safe
    X["clim_target"] = clim_tgt
    X["clim_target_minus_now"] = clim_tgt - X["clim_now"]

    hod = tgt_time.dt.hour + tgt_time.dt.minute / 60.0
    doy = tgt_time.dt.dayofyear
    X["tgt_hour_sin"] = np.sin(2 * np.pi * hod / 24)
    X["tgt_hour_cos"] = np.cos(2 * np.pi * hod / 24)
    X["tgt_doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    X["tgt_doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

    y = df["wbgt_c"].shift(-lead)              # WBGT at T+lead (the target)
    persist = df["wbgt_c"].to_numpy()          # persistence prediction = WBGT at T
    return X, y, persist, clim_tgt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/doha_wbgt_16yr.csv")
    args = ap.parse_args()
    path = pathlib.Path(args.data)
    if not path.is_absolute():
        path = REPO / path

    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)

    clim = leak_safe_climatology(df)
    feat = build_features(df, clim)

    results = {}          # (lead, kind) -> EvalResult
    importances = []

    for lead in LEADS:
        X, y, persist, clim_tgt = per_lead_matrix(df, feat, clim, lead)
        ok = X.notna().all(axis=1) & y.notna()
        idx = np.where(ok.to_numpy())[0]                 # global rows we can use
        Xv, yv = X.to_numpy()[idx], y.to_numpy()[idx]

        oos = np.full(len(idx), np.nan)
        for tr, te in walk_forward_splits(len(idx), n_folds=5, min_train_frac=0.4):
            cut = int(len(tr) * 0.85)                    # time-ordered val tail
            m = lgb.LGBMRegressor(**LGB_PARAMS)
            m.fit(Xv[tr[:cut]], yv[tr[:cut]],
                  eval_set=[(Xv[tr[cut:]], yv[tr[cut:]])],
                  callbacks=[lgb.early_stopping(60), lgb.log_evaluation(0)])
            oos[te] = m.predict(Xv[te])
            importances.append(pd.Series(
                m.booster_.feature_importance("gain"), index=X.columns))

        scored = ~np.isnan(oos)
        gi = idx[scored]                                 # global rows actually scored
        yt = yv[scored]
        results[(lead, "persistence")] = evaluate(yt, persist[gi], THR, f"persistence_{lead}h")
        results[(lead, "climatology")] = evaluate(yt, clim_tgt[gi], THR, f"climatology_{lead}h")
        results[(lead, "layer1")] = evaluate(yt, oos[scored], THR, f"layer1_{lead}h")

        pd.DataFrame({
            "time": df["time"].to_numpy()[gi], "y_true": yt,
            "pred_layer1": oos[scored], "pred_persistence": persist[gi],
            "pred_climatology": clim_tgt[gi], "lead_h": lead,
        }).to_csv(REPO / f"data/layer1_v1_oos_{lead}h.csv", index=False)

    # ---------------- report ----------------
    hdr = (f"{'model':<22}{'RMSE':>7}{'MAE':>7}{'hit%':>8}{'MISS%':>8}"
           f"{'FP%':>7}{'nExc':>8}")
    print("\n" + hdr + "\n" + "-" * len(hdr))
    for lead in LEADS:
        for kind in ("persistence", "climatology", "layer1"):
            r = results[(lead, kind)]
            print(f"{r.name:<22}{r.rmse:7.2f}{r.mae:7.2f}{r.hit_rate*100:8.1f}"
                  f"{r.false_negative_rate*100:8.1f}"
                  f"{r.false_positive_rate*100:7.1f}{r.n_exceedance_hours:8d}")
        print()

    print("Layer 1 vs persistence  (the number that matters):")
    for lead in LEADS:
        rm, rp = results[(lead, "layer1")], results[(lead, "persistence")]
        print(f"  {lead:>2}h:  MAE {rp.mae:.2f} -> {rm.mae:.2f} "
              f"({100*(1-rm.mae/rp.mae):+.0f}%)   "
              f"RMSE skill {100*(1-rm.rmse/rp.rmse):+.0f}%   "
              f"MISS {rp.false_negative_rate*100:.1f}% -> "
              f"{rm.false_negative_rate*100:.1f}%")

    imp = pd.concat(importances, axis=1).mean(axis=1).sort_values(ascending=False)
    print("\nTop 15 features (mean gain over folds & leads):")
    for k, v in imp.head(15).items():
        print(f"  {k:<24}{v:12.0f}")


if __name__ == "__main__":
    main()
