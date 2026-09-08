"""
scripts/train_layer1_v2_nwp.py

Layer 1 v2: TRUE NWP bias-correction. For each lead (24/48/72 h) we have
the weather that was actually FORECAST for hour t by the run issued ~24N h
earlier. From it we build a forecast WBGT. The model learns the systematic
error  truth_WBGT(t) - forecast_WBGT_N(t)  and outputs a corrected WBGT.

Truth = WBGT from the patched reanalysis (METAR-corrected wind), joined on
time. The primary baseline to beat is the RAW forecast WBGT (uncorrected):
if the model can't beat that, bias-correction isn't adding value.

Also compared: persistence (WBGT known at forecast-issue time) and
walk-forward climatology. Same harness metrics, expanding-window
walk-forward, then a decision-threshold sweep vs the raw forecast.

Run:  python scripts/train_layer1_v2_nwp.py
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

from eval.harness import evaluate, walk_forward_splits
from src.solar import cos_solar_zenith_angle
from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C as THR
from src.wbgt import wbgt_liljegren_c
from train_layer1_v1 import leak_safe_climatology

warnings.filterwarnings("ignore", category=UserWarning)

DOHA_LAT, DOHA_LON = 25.27, 51.61
LEADS = [1, 2, 3]          # forecast-day leads => 24 / 48 / 72 h
TAUS = np.round(np.arange(27.0, 32.6, 0.1), 1)
TARGET_MISS = [0.20, 0.10, 0.05]

LGB = dict(objective="regression_l1", n_estimators=1200, learning_rate=0.02,
           num_leaves=63, subsample=0.8, subsample_freq=1,
           colsample_bytree=0.8, min_child_samples=40, n_jobs=-1, verbose=-1)


def wbgt_from(df, suffix):
    """Liljegren WBGT from a set of columns (suffix '' = analysis, '_fc1'..)."""
    g = lambda base: df[f"{base}{suffix}"].to_numpy()
    return wbgt_liljegren_c(
        temp_c=g("temperature_2m"), rh_pct=g("relative_humidity_2m"),
        pressure_hpa=g("surface_pressure"), wind_speed_10m_ms=g("wind_speed_10m"),
        shortwave_wm2=np.nan_to_num(g("shortwave_radiation")),
        direct_wm2=np.nan_to_num(g("direct_radiation")),
        cos_zenith=df["cos_zenith"].to_numpy(),
    )


def sweep(y_true, y_pred):
    te = y_true > THR
    ne = ~te
    rows = [(t, (te & ~(y_pred > t)).sum() / te.sum(),
                (ne & (y_pred > t)).sum() / ne.sum(),
                (y_pred > t).mean()) for t in TAUS]
    return pd.DataFrame(rows, columns=["tau", "miss", "fp", "alarm"])


def at_target(curve, target):
    ok = curve[curve["miss"] <= target]
    return None if ok.empty else ok.sort_values("tau", ascending=False).iloc[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fc", default="data/doha_forecast_archive.csv")
    ap.add_argument("--truth", default="data/doha_wbgt_16yr.csv")
    args = ap.parse_args()

    fc = pd.read_csv(REPO / args.fc)
    fc["time"] = pd.to_datetime(fc["time"], utc=True)
    fc["cos_zenith"] = cos_solar_zenith_angle(pd.DatetimeIndex(fc["time"]),
                                              DOHA_LAT, DOHA_LON)

    tr = pd.read_csv(REPO / args.truth)[["time", "wbgt_c"]]
    tr["time"] = pd.to_datetime(tr["time"], utc=True)
    tr = tr.rename(columns={"wbgt_c": "wbgt_truth"})

    df = fc.merge(tr, on="time", how="inner").sort_values("time").reset_index(drop=True)
    df["wbgt_analysis"] = wbgt_from(df, "")            # WBGT from the analysis fields
    clim = leak_safe_climatology(df.rename(columns={"wbgt_truth": "wbgt_c"}))

    def clim_at(times, cut_year):
        key = times.dt.strftime("%m-%d-%H").to_numpy()
        return clim.reindex(pd.MultiIndex.from_arrays([key, cut_year.to_numpy()])).to_numpy()

    results, curves = {}, []
    for n in LEADS:
        h = 24 * n
        d = df.copy()
        d[f"wbgt_fc{n}"] = wbgt_from(d, f"_fc{n}")

        t = d["time"]
        y = d["wbgt_truth"].to_numpy()                         # target: truth at t
        raw_fc = d[f"wbgt_fc{n}"].to_numpy()                   # baseline: raw forecast
        persist = d["wbgt_truth"].shift(h).to_numpy()          # known at issue time
        clim_tgt = clim_at(t, t.dt.year)

        f = pd.DataFrame(index=d.index)
        f["fc_wbgt"] = raw_fc
        for b, nm in [("temperature_2m", "temp"), ("relative_humidity_2m", "rh"),
                      ("wind_speed_10m", "wind"), ("shortwave_radiation", "solar"),
                      ("surface_pressure", "pres")]:
            f[f"fc_{nm}"] = d[f"{b}_fc{n}"]
        # what we knew when the forecast was issued (t - h)
        for k in (0, 24, 48):
            f[f"obs_wbgt_lag{k}"] = d["wbgt_truth"].shift(h + k)
        f["obs_trend_24"] = d["wbgt_truth"].shift(h) - d["wbgt_truth"].shift(h + 24)
        f["obs_anom_issue"] = d["wbgt_truth"].shift(h).to_numpy() - clim_at(
            t - pd.Timedelta(hours=h), t.dt.year)
        # climatology + calendar of the TARGET hour
        f["clim_target"] = clim_tgt
        f["fc_minus_clim"] = raw_fc - clim_tgt
        f["fc_minus_persist"] = raw_fc - d["wbgt_truth"].shift(h).to_numpy()
        hod = t.dt.hour + t.dt.minute / 60
        doy = t.dt.dayofyear
        f["hour_sin"] = np.sin(2 * np.pi * hod / 24)
        f["hour_cos"] = np.cos(2 * np.pi * hod / 24)
        f["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
        f["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

        ok = f.notna().all(axis=1) & ~np.isnan(y) & ~np.isnan(raw_fc) & ~np.isnan(persist)
        idx = np.where(ok.to_numpy())[0]
        Xv, yv = f.to_numpy()[idx], y[idx]

        oos = np.full(len(idx), np.nan)
        imps = []
        for a, b in walk_forward_splits(len(idx), n_folds=4, min_train_frac=0.4):
            cut = int(len(a) * 0.85)
            m = lgb.LGBMRegressor(**LGB)
            m.fit(Xv[a[:cut]], yv[a[:cut]], eval_set=[(Xv[a[cut:]], yv[a[cut:]])],
                  callbacks=[lgb.early_stopping(60), lgb.log_evaluation(0)])
            oos[b] = m.predict(Xv[b])
            imps.append(pd.Series(m.booster_.feature_importance("gain"), index=f.columns))

        s = ~np.isnan(oos)
        gi = idx[s]
        yt = yv[s]
        results[(n, "raw_forecast")] = evaluate(yt, raw_fc[gi], THR, f"raw_forecast_{h}h")
        results[(n, "persistence")] = evaluate(yt, persist[gi], THR, f"persistence_{h}h")
        results[(n, "climatology")] = evaluate(yt, clim_tgt[gi], THR, f"climatology_{h}h")
        results[(n, "layer1_v2")] = evaluate(yt, oos[s], THR, f"layer1_v2_{h}h")
        results[(n, "_imp")] = pd.concat(imps, axis=1).mean(axis=1).sort_values(ascending=False)
        results[(n, "_bias")] = float(np.mean(yt - raw_fc[gi]))

        for name, p in [("raw_forecast", raw_fc[gi]), ("layer1_v2", oos[s])]:
            c = sweep(yt, p)
            c["method"], c["lead_h"] = name, h
            curves.append(c)

        pd.DataFrame({"time": df["time"].to_numpy()[gi], "y_truth": yt,
                      "raw_forecast": raw_fc[gi], "layer1_v2": oos[s],
                      "persistence": persist[gi], "climatology": clim_tgt[gi],
                      "lead_h": h}).to_csv(REPO / f"data/layer1_v2_oos_{h}h.csv", index=False)

    # ---------------- report ----------------
    hdr = (f"{'model':<20}{'RMSE':>7}{'MAE':>7}{'hit%':>8}{'MISS%':>8}"
           f"{'FP%':>7}{'nExc':>7}")
    for n in LEADS:
        h = 24 * n
        print(f"\n============  LEAD {h}h   (raw-forecast WBGT bias: "
              f"{results[(n,'_bias')]:+.2f} C)  ============")
        print(hdr + "\n" + "-" * len(hdr))
        for kind in ("persistence", "climatology", "raw_forecast", "layer1_v2"):
            r = results[(n, kind)]
            print(f"{r.name:<20}{r.rmse:7.2f}{r.mae:7.2f}{r.hit_rate*100:8.1f}"
                  f"{r.false_negative_rate*100:8.1f}{r.false_positive_rate*100:7.1f}"
                  f"{r.n_exceedance_hours:7d}")
        print("  top features:", ", ".join(results[(n, "_imp")].head(6).index))

    print("\n--- decision-threshold sweep: raw forecast vs corrected ---")
    hh = f"{'lead':>5} {'target MISS':>11} {'method':<13} {'thr':>6} {'FP%':>7} {'alarm%':>8}"
    print(hh + "\n" + "-" * len(hh))
    for c in curves:
        for tgt in TARGET_MISS:
            row = at_target(c, tgt)
            lead = c["lead_h"].iloc[0]
            meth = c["method"].iloc[0]
            if row is None:
                print(f"{lead:>5} {tgt*100:>10.0f}% {meth:<13} {'--':>6} {'--':>7} {'--':>8}")
            else:
                print(f"{lead:>5} {tgt*100:>10.0f}% {meth:<13} {row.tau:>6.1f} "
                      f"{row.fp*100:>7.1f} {row.alarm*100:>8.1f}")
        if c["method"].iloc[0] == "layer1_v2":
            print()

    pd.concat(curves, ignore_index=True).to_csv(
        REPO / "data/layer1_v2_threshold_curves.csv", index=False)


if __name__ == "__main__":
    main()
