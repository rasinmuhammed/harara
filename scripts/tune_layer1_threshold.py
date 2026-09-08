"""
scripts/tune_layer1_threshold.py

Two levers to cut the dangerous error (missed threshold crossings), which
the plain MAE-minimising Layer 1 v1 did NOT improve:

  1. Decision threshold. The event is always WBGT > 32.1 C (the legal
     line). But we can raise an alarm whenever the *forecast* exceeds a
     lower value tau. Lowering tau catches more true exceedances (fewer
     MISSES) at the cost of more false alarms (FP). Sweep tau, plot the
     trade-off. No retraining.

  2. Quantile objective. Retrain the model to predict the 75th / 90th
     conditional percentile instead of the median. It then deliberately
     forecasts high, so exceedances are caught - a model-side version of
     the same trade-off, and it should shift the whole curve favourably.

Output: for each lead and method, the decision threshold that hits a set
of target MISS rates, and the false-positive cost there. Plus the full
curves to data/ for plotting.

Run:  python scripts/tune_layer1_threshold.py --data data/doha_wbgt_16yr.csv
"""

import argparse
import pathlib
import sys
import warnings

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import lightgbm as lgb

from eval.harness import walk_forward_splits
from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C as THR
from train_layer1_v1 import build_features, leak_safe_climatology, per_lead_matrix

warnings.filterwarnings("ignore", category=UserWarning)

LEADS = [24, 48, 72]
TAUS = np.round(np.arange(27.0, 32.6, 0.1), 1)
TARGET_MISS = [0.20, 0.15, 0.10, 0.05]

BASE = dict(n_estimators=1200, learning_rate=0.02, num_leaves=63,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
            min_child_samples=40, n_jobs=-1, verbose=-1)
QUANTILE_CFGS = {
    "gbm_q75": dict(objective="quantile", alpha=0.75, **BASE),
    "gbm_q90": dict(objective="quantile", alpha=0.90, **BASE),
}


def walkforward_oos(Xv: np.ndarray, yv: np.ndarray, params: dict) -> np.ndarray:
    oos = np.full(len(Xv), np.nan)
    for tr, te in walk_forward_splits(len(Xv), n_folds=5, min_train_frac=0.4):
        cut = int(len(tr) * 0.85)
        m = lgb.LGBMRegressor(**params)
        m.fit(Xv[tr[:cut]], yv[tr[:cut]],
              eval_set=[(Xv[tr[cut:]], yv[tr[cut:]])],
              callbacks=[lgb.early_stopping(60), lgb.log_evaluation(0)])
        oos[te] = m.predict(Xv[te])
    return oos


def sweep(y_true: np.ndarray, y_pred: np.ndarray) -> pd.DataFrame:
    true_exc = y_true > THR
    non_exc = ~true_exc
    n_exc, n_non = true_exc.sum(), non_exc.sum()
    rows = []
    for tau in TAUS:
        alarm = y_pred > tau
        rows.append((
            tau,
            (true_exc & ~alarm).sum() / n_exc,      # MISS rate
            (non_exc & alarm).sum() / n_non,        # FP rate
            alarm.mean(),                           # overall alarm rate
        ))
    return pd.DataFrame(rows, columns=["tau", "miss", "fp", "alarm"])


def at_target(curve: pd.DataFrame, target: float):
    """Lowest tau (fewest false alarms) whose MISS rate <= target."""
    ok = curve[curve["miss"] <= target]
    if ok.empty:
        return None
    return ok.sort_values("tau", ascending=False).iloc[0]


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

    all_curves = []
    for lead in LEADS:
        X, y, persist, clim_tgt = per_lead_matrix(df, feat, clim, lead)
        ok = X.notna().all(axis=1) & y.notna()
        idx = np.where(ok.to_numpy())[0]
        Xv, yv = X.to_numpy()[idx], y.to_numpy()[idx]

        # reuse the saved median-model OOS predictions if present
        med_path = REPO / f"data/layer1_v1_oos_{lead}h.csv"
        preds = {}
        if med_path.exists():
            # this file already IS the walk-forward scored set, in order
            s = pd.read_csv(med_path)
            preds["gbm_median"] = s["pred_layer1"].to_numpy()
            preds["persistence"] = s["pred_persistence"].to_numpy()
            yt = s["y_true"].to_numpy()
        else:
            oos = walkforward_oos(Xv, yv, dict(objective="regression_l1", **BASE))
            m = ~np.isnan(oos)
            yt = yv[m]
            preds["gbm_median"] = oos[m]
            preds["persistence"] = persist[idx][m]

        # quantile models (train fresh)
        scored_mask = None
        for name, cfg in QUANTILE_CFGS.items():
            oos = walkforward_oos(Xv, yv, cfg)
            m = ~np.isnan(oos)
            scored_mask = m
            preds[name] = oos[m]
        if len(yt) != scored_mask.sum():
            yt = yv[scored_mask]
            preds["persistence"] = persist[idx][scored_mask]

        print(f"\n================  LEAD {lead}h  (n_exceed = "
              f"{int((yt > THR).sum())}, n = {len(yt)})  ================")
        hdr = f"{'target MISS':>11} {'method':<13} {'dec.thr':>8} {'FP%':>7} {'alarm%':>8}"
        print(hdr + "\n" + "-" * len(hdr))
        for name, p in preds.items():
            curve = sweep(yt, p)
            curve["method"], curve["lead"] = name, lead
            all_curves.append(curve)
            for tgt in TARGET_MISS:
                row = at_target(curve, tgt)
                if row is None:
                    print(f"{tgt*100:>10.0f}% {name:<13} {'--':>8} "
                          f"{'--':>7} {'--':>8}   (unreachable)")
                else:
                    print(f"{tgt*100:>10.0f}% {name:<13} {row.tau:>8.1f} "
                          f"{row.fp*100:>7.1f} {row.alarm*100:>8.1f}")
            print()

    out = REPO / "data/layer1_threshold_curves.csv"
    pd.concat(all_curves, ignore_index=True).to_csv(out, index=False)
    print(f"Full miss/FP curves -> {out}")


if __name__ == "__main__":
    main()
