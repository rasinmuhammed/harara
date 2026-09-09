"""
scripts/aiwp_humid_heat_study.py

Do AI weather prediction models under-forecast Gulf humid-heat extremes?

H-E (adversarial): "AI weather models degrade humid-heat stop-work
decisions relative to conventional NWP." arXiv 2504.21195 reports a
consistent regional COLD bias in 2 m temperature in the days before
CONUS heat-wave onset for GraphCast, Pangu and GEFS. Cold bias before
extreme heat is the dangerous direction. This tests the same idea for
Doha WBGT and the 32.1 C stop-work threshold.

Two tracks (GraphCast serves only 2 m temperature on the public feed):
  WBGT track   IFS, AIFS, GFS      -- Liljegren WBGT, miss rate at 32.1 C
  temp track   + GraphCast         -- 2 m T bias, miss rate at a prior-
                                      years hot-hour percentile

Scored with eval/harness.py conventions: walk-forward against the
METAR-patched observational truth, miss rate as the headline, signed bias
stratified by lead and by truth band, and the bias in the days before a
local heat-wave onset. Moving-block bootstrap (one local day = one block)
95% CIs on every headline number.

The headline tables score every model on the COMMON window (the
intersection of valid hours across the models on that track and lead), so
AIFS -- which only starts 2025-02 on this feed -- is compared like for
like. A full-window appendix reports IFS and GFS over all their data.
AIFS carries ~1.5 warm seasons regardless and is flagged throughout; the
repo's 2000-2019 GEFS reforecast is the decade-scale complement for the
GFS family (gefs_calibration.py).

Run:
    python scripts/aiwp_humid_heat_study.py
    python scripts/aiwp_humid_heat_study.py --quick     # N_BOOT=250
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from eval.harness import evaluate
from src.forecast_wbgt import wbgt_from_forecast_frame
from src.heatwave import daily_max, heatwave_onsets, preonset_mask
from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C

DOHA_LAT, DOHA_LON = 25.27, 51.61
TZ = "Asia/Qatar"
THR = QATAR_WBGT_STOP_WORK_THRESHOLD_C            # 32.1 C
LEADS = (1, 2, 3, 4, 5, 6, 7)
CORE_MONTHS = (5, 6, 7, 8, 9)
SHOULDER_MONTHS = (4, 10)
DAYLIGHT = (7, 18)                                # local hour, inclusive
BANDS = [(-np.inf, 28), (28, 30), (30, 32), (32, 34), (34, np.inf)]
BAND_LABELS = ["<28", "28-30", "30-32", "32-34", ">34"]
PREONSET_WINDOWS = (3, 5, 7)
HEADLINE_W = 5
HEADLINE_LEAD = 5
ONSET_PCTL = 90.0
THOT_PCTL = 95.0
MIN_SHOULDER_EXC = 50

PREV = REPO / "data" / "previous_runs"
TRUTH_CSV = REPO / "data" / "doha_wbgt_16yr.csv"
PATCHED_CSV = REPO / "data" / "doha_weather_16yr_patched.csv"

WBGT_MODELS = {"ecmwf_ifs025": "IFS",
               "ecmwf_aifs025_single": "AIFS",
               "gfs_seamless": "GFS"}
TEMP_MODELS = {**WBGT_MODELS, "gfs_graphcast025": "GraphCast"}
SMALL_SAMPLE = {"AIFS"}

RNG = np.random.default_rng(20260909)
N_BOOT = 2000


# --------------------------------------------------------------------------
# masks / alignment
# --------------------------------------------------------------------------
def _local(t) -> pd.Series:
    return pd.to_datetime(pd.Series(np.asarray(t)), utc=True).dt.tz_convert(TZ)


def _season_daylight(t, months) -> np.ndarray:
    lt = _local(t)
    lo, hi = DAYLIGHT
    return (lt.dt.month.isin(months) & lt.dt.hour.between(lo, hi)).to_numpy()


def load_truth() -> pd.DataFrame:
    t = pd.read_csv(TRUTH_CSV, usecols=["time", "temperature_2m", "wbgt_c"])
    t["time"] = pd.to_datetime(t["time"], utc=True)
    return t.sort_values("time").reset_index(drop=True)


def forecast_wbgt_frame(model: str, lead: int) -> tuple[pd.DataFrame, bool]:
    df = pd.read_csv(PREV / f"{model}__lead{lead}d.csv")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    w = wbgt_from_forecast_frame(df, DOHA_LAT, DOHA_LON)
    out = pd.DataFrame({"time": df["time"].to_numpy(),
                        "wbgt_pred": np.asarray(w),
                        "t_pred": df["temperature_2m"].to_numpy()})
    return out, bool(getattr(w, "used_erbs_direct", False))


def forecast_temp_frame(model: str, lead: int) -> pd.DataFrame:
    df = pd.read_csv(PREV / f"{model}__lead{lead}d.csv",
                     usecols=lambda c: c in ("time", "temperature_2m"))
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return pd.DataFrame({"time": df["time"].to_numpy(),
                         "t_pred": df["temperature_2m"].to_numpy()})


def align(truth: pd.DataFrame, fc: pd.DataFrame, true_col: str, pred_col: str,
          months, restrict_times: pd.Index | None = None) -> pd.DataFrame:
    m = truth[["time", true_col]].merge(fc[["time", pred_col]], on="time",
                                        how="inner")
    m = m[_season_daylight(m["time"], months)].dropna(subset=[true_col, pred_col])
    if restrict_times is not None:
        m = m[m["time"].isin(restrict_times)]
    lt = _local(m["time"])
    return pd.DataFrame({
        "time": m["time"].to_numpy(),
        "day": lt.dt.strftime("%Y-%m-%d").to_numpy(),
        "true_": m[true_col].to_numpy(dtype=float),
        "pred_": m[pred_col].to_numpy(dtype=float),
    })


# --------------------------------------------------------------------------
# fast moving-block (one local day) bootstrap: every metric is a ratio of
# per-day sums, so resample day rows and re-aggregate.
# --------------------------------------------------------------------------
def _day_sums(d: pd.DataFrame, thr_col: str | None = None):
    diff = d["pred_"].to_numpy() - d["true_"].to_numpy()
    thr = d[thr_col].to_numpy() if thr_col else np.full(len(d), THR)
    te = d["true_"].to_numpy() > thr if thr_col is None else \
        d["true_"].to_numpy() >= thr
    pred_below = d["pred_"].to_numpy() <= thr if thr_col is None else \
        d["pred_"].to_numpy() < thr
    frame = pd.DataFrame({
        "day": d["day"].to_numpy(),
        "cnt": 1.0,
        "err": diff,
        "abse": np.abs(diff),
        "sqe": diff ** 2,
        "exc": te.astype(float),
        "miss": (te & pred_below).astype(float),
        "nonexc": (~te).astype(float),
        "fp": ((~te) & ~pred_below).astype(float),
    })
    return frame.groupby("day", sort=True).sum()


def _boot_ratio(num_day: np.ndarray, den_day: np.ndarray, n_boot: int,
                sqrt: bool = False, alpha: float = 0.05):
    D = len(num_day)
    point = num_day.sum() / den_day.sum() if den_day.sum() else np.nan
    if sqrt:
        point = np.sqrt(point) if np.isfinite(point) else point
    if D < 4 or not np.isfinite(point):
        return float(point), (np.nan, np.nan)
    draws = RNG.integers(0, D, size=(n_boot, D))
    nb = num_day[draws].sum(axis=1)
    db = den_day[draws].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = nb / db
    if sqrt:
        r = np.sqrt(np.clip(r, 0, None))
    r = r[np.isfinite(r)]
    lo, hi = np.percentile(r, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(point), (float(lo), float(hi))


def score_cell(d: pd.DataFrame, track, model, lead, season, n_boot,
               thr_col=None) -> list[dict]:
    if len(d) < 100:
        return []
    s = _day_sums(d, thr_col)
    er = evaluate(d["true_"].to_numpy(), d["pred_"].to_numpy(), threshold_c=THR,
                  name=f"{model}_l{lead}")
    specs = [
        ("bias", s["err"].to_numpy(), s["cnt"].to_numpy(), False),
        ("mae", s["abse"].to_numpy(), s["cnt"].to_numpy(), False),
        ("rmse", s["sqe"].to_numpy(), s["cnt"].to_numpy(), True),
        ("miss_rate", s["miss"].to_numpy(), s["exc"].to_numpy(), False),
        ("fpr", s["fp"].to_numpy(), s["nonexc"].to_numpy(), False),
    ]
    rows = []
    for metric, num, den, sq in specs:
        pt, (lo, hi) = _boot_ratio(num, den, n_boot, sqrt=sq)
        rows.append(dict(track=track, model=model, lead=lead, season=season,
                         metric=metric, value=round(pt, 4),
                         ci_lo=round(lo, 4), ci_hi=round(hi, 4),
                         n=int(len(d)), n_exc=int(er.n_exceedance_hours)))
    return rows


def band_bias(d: pd.DataFrame, model, lead) -> list[dict]:
    out = []
    for (lo, hi), lab in zip(BANDS, BAND_LABELS):
        sub = d[(d["true_"] >= lo) & (d["true_"] < hi)]
        out.append(dict(model=model, lead=lead, band=lab, n=int(len(sub)),
                        bias=round(float((sub["pred_"] - sub["true_"]).mean()), 3)
                        if len(sub) else np.nan))
    return out


def preonset_rows(d, onsets, track, model, lead, n_boot) -> list[dict]:
    all_bias = float((d["pred_"] - d["true_"]).mean()) if len(d) else np.nan
    rows = []
    for w in PREONSET_WINDOWS:
        sub = d[preonset_mask(pd.Series(d["time"]), onsets, w)]
        if len(sub) < 24:
            rows.append(dict(track=track, model=model, lead=lead, window_days=w,
                             bias=np.nan, ci_lo=np.nan, ci_hi=np.nan,
                             n_hours=int(len(sub)), n_events=len(onsets),
                             all_days_bias=round(all_bias, 3)))
            continue
        s = _day_sums(sub)
        pt, (lo, hi) = _boot_ratio(s["err"].to_numpy(), s["cnt"].to_numpy(),
                                   n_boot)
        rows.append(dict(track=track, model=model, lead=lead, window_days=w,
                         bias=round(pt, 3), ci_lo=round(lo, 3),
                         ci_hi=round(hi, 3), n_hours=int(len(sub)),
                         n_events=len(onsets), all_days_bias=round(all_bias, 3)))
    return rows


def paired_ci(da: pd.DataFrame, db: pd.DataFrame, kind: str, n_boot: int):
    """kind='miss' -> (miss_rate_A - miss_rate_B) over common exceedance
    hours; kind='bias' -> mean(pred_A - pred_B)."""
    m = da.merge(db[["time", "pred_"]], on="time", suffixes=("_a", "_b"))
    if len(m) < 100:
        return np.nan, (np.nan, np.nan), 0
    te = m["true_"].to_numpy() > THR
    day = m["day_a"].to_numpy() if "day_a" in m else m["day"].to_numpy()
    if kind == "miss":
        num = (te & (m["pred__a"].to_numpy() <= THR)).astype(float) \
            - (te & (m["pred__b"].to_numpy() <= THR)).astype(float)
        den = te.astype(float)
    else:
        num = (m["pred__a"].to_numpy() - m["pred__b"].to_numpy())
        den = np.ones(len(m))
    g = pd.DataFrame({"day": day, "num": num, "den": den}).groupby("day").sum()
    pt, ci = _boot_ratio(g["num"].to_numpy(), g["den"].to_numpy(), n_boot)
    return pt, ci, int(te.sum())


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out-scores", type=pathlib.Path,
                    default=REPO / "data" / "aiwp_scores.csv")
    ap.add_argument("--out-preonset", type=pathlib.Path,
                    default=REPO / "data" / "aiwp_preheatwave.csv")
    args = ap.parse_args()
    nb = 250 if args.quick else N_BOOT

    truth = load_truth()
    dmax_w = daily_max(truth, "wbgt_c", months=CORE_MONTHS, hours=DAYLIGHT)
    onsets_w = heatwave_onsets(dmax_w, percentile=ONSET_PCTL, min_run_days=2)
    dmax_t = daily_max(truth, "temperature_2m", months=CORE_MONTHS, hours=DAYLIGHT)
    onsets_t = heatwave_onsets(dmax_t, percentile=ONSET_PCTL, min_run_days=2)
    print(f"heat-wave onsets (>= 2024): WBGT "
          f"{sorted(str(o.date()) for o in onsets_w if o.year >= 2024)}")
    print(f"                            temp "
          f"{sorted(str(o.date()) for o in onsets_t if o.year >= 2024)}")

    scores: list[dict] = []
    preonset: list[dict] = []
    bands: list[dict] = []
    erbs: list[str] = []

    # ================= WBGT TRACK, COMMON WINDOW ========================
    print("\n" + "=" * 78)
    print("WBGT track -- headline, common window across IFS/AIFS/GFS per lead")
    print("=" * 78)
    hdr = (f"{'model':>10} {'lead':>4} {'n':>6} {'n_exc':>6} {'MAE':>6} "
           f"{'RMSE':>6} {'bias':>7}  {'miss@32.1 (95% CI)':>22}  {'FPR':>5}")

    wbgt_aln: dict[tuple[str, int], pd.DataFrame] = {}
    for lead in LEADS:
        raw = {}
        for model, nice in WBGT_MODELS.items():
            fc, used = forecast_wbgt_frame(model, lead)
            if used:
                erbs.append(f"{nice} L{lead}")
            raw[nice] = align(truth, fc, "wbgt_c", "wbgt_pred", CORE_MONTHS)
        common = None
        for a in raw.values():
            s = set(a["time"])
            common = s if common is None else (common & s)
        common = pd.Index(sorted(common))
        for nice in WBGT_MODELS.values():
            d = raw[nice][raw[nice]["time"].isin(common)].reset_index(drop=True)
            wbgt_aln[(nice, lead)] = d
            cell = score_cell(d, "wbgt_common", nice, lead, "core", nb)
            scores.extend(cell)
        if lead in (1, HEADLINE_LEAD, 7):
            print(f"\nlead {lead} d   (common n = {len(common)} hours)")
            print(hdr)
            for nice in WBGT_MODELS.values():
                g = {r["metric"]: r for r in scores
                     if r["model"] == nice and r["lead"] == lead
                     and r["track"] == "wbgt_common"}
                if not g:
                    continue
                flag = " *" if nice in SMALL_SAMPLE else ""
                print(f"{nice:>10} {lead:>4} {g['bias']['n']:>6} "
                      f"{g['miss_rate']['n_exc']:>6} {g['mae']['value']:>6.2f} "
                      f"{g['rmse']['value']:>6.2f} {g['bias']['value']:>+7.2f}  "
                      f"{g['miss_rate']['value']:>6.2f} "
                      f"[{g['miss_rate']['ci_lo']:.2f},{g['miss_rate']['ci_hi']:.2f}]"
                      f"      {g['fpr']['value']:>5.2f}{flag}")
        for nice in WBGT_MODELS.values():
            preonset.extend(preonset_rows(wbgt_aln[(nice, lead)], onsets_w,
                                          "wbgt", nice, lead, nb))
    print("\n  * AIFS: ~1.5 warm seasons on this feed; wide intervals.")

    # per-band bias at the headline lead (common window)
    print(f"\nsigned WBGT bias by truth band, lead {HEADLINE_LEAD} d, common "
          f"window (C, forecast - truth):")
    print(f"{'model':>10} " + " ".join(f"{b:>8}" for b in BAND_LABELS))
    for nice in WBGT_MODELS.values():
        d = wbgt_aln.get((nice, HEADLINE_LEAD))
        if d is None or len(d) < 100:
            continue
        bb = band_bias(d, nice, HEADLINE_LEAD)
        bands.extend(bb)
        print(f"{nice:>10} " + " ".join(
            f"{r['bias']:>+8.2f}" if np.isfinite(r['bias']) else f"{'-':>8}"
            for r in bb))

    # pre-heat-wave WBGT bias (headline window), common
    print(f"\npre-heat-wave WBGT bias, {HEADLINE_W} d before onset "
          f"(C; all-days bias in parens), common window:")
    print(f"{'model':>10} " + " ".join(f"{f'L{n}':>15}" for n in LEADS))
    for nice in WBGT_MODELS.values():
        cells = []
        for lead in LEADS:
            r = next((x for x in preonset if x["track"] == "wbgt"
                      and x["model"] == nice and x["lead"] == lead
                      and x["window_days"] == HEADLINE_W), None)
            cells.append(f"{r['bias']:+.2f}({r['all_days_bias']:+.2f})"
                         if r and np.isfinite(r["bias"]) else "-")
        print(f"{nice:>10} " + " ".join(f"{c:>15}" for c in cells))

    # paired comparisons (common by construction)
    print("\npaired WBGT miss rate at 32.1 C  (positive => first model misses "
          "MORE true exceedance hours):")
    for a, b in (("AIFS", "IFS"), ("AIFS", "GFS"), ("IFS", "GFS")):
        line = [f"  {a:>4} - {b:<4}:"]
        for lead in LEADS:
            da, db = wbgt_aln.get((a, lead)), wbgt_aln.get((b, lead))
            if da is None or db is None:
                continue
            pt, (lo, hi), _ = paired_ci(da, db, "miss", nb)
            mark = "+" if lo > 0 else ("-" if hi < 0 else " ")
            scores.append(dict(track="wbgt_paired", model=f"{a}-{b}", lead=lead,
                               season="core", metric="paired_miss_diff",
                               value=round(pt, 4), ci_lo=round(lo, 4),
                               ci_hi=round(hi, 4), n=0, n_exc=0))
            line.append(f"L{lead} {pt:+.2f}[{lo:+.2f},{hi:+.2f}]{mark}")
        print(" ".join(line))

    # component bias: why a cold air-temperature bias need not be a cold
    # WBGT bias. Common AIFS window, lead 1, core daylight.
    print("\ncomponent bias vs METAR-patched truth (AIFS window, lead 1 d, "
          "core daylight) -- the wet-bulb term is 0.7 of WBGT:")
    print(f"{'model':>10} {'dT (C)':>8} {'dRH (%)':>9} {'dWind (m/s)':>12}")
    tc = pd.read_csv(PATCHED_CSV,
                     usecols=["time", "temperature_2m", "relative_humidity_2m",
                              "wind_speed_10m"])
    tc["time"] = pd.to_datetime(tc["time"], utc=True)
    aifs_start = pd.read_csv(PREV / "ecmwf_aifs025_single__lead1d.csv",
                             usecols=["time"])
    aifs_start = pd.to_datetime(aifs_start["time"], utc=True).min()
    for model, nice in WBGT_MODELS.items():
        fc = pd.read_csv(PREV / f"{model}__lead1d.csv",
                         usecols=["time", "temperature_2m",
                                  "relative_humidity_2m", "wind_speed_10m"])
        fc["time"] = pd.to_datetime(fc["time"], utc=True)
        j = tc.merge(fc, on="time", suffixes=("_t", "_f"))
        j = j[_season_daylight(j["time"], CORE_MONTHS)]
        j = j[j["time"] >= aifs_start].dropna()
        dT = float((j["temperature_2m_f"] - j["temperature_2m_t"]).mean())
        dRH = float((j["relative_humidity_2m_f"]
                     - j["relative_humidity_2m_t"]).mean())
        dW = float((j["wind_speed_10m_f"] - j["wind_speed_10m_t"]).mean())
        for metric, val in (("dT_c", dT), ("dRH_pct", dRH), ("dWind_ms", dW)):
            scores.append(dict(track="component_bias", model=nice, lead=1,
                               season="core", metric=metric,
                               value=round(val, 3), ci_lo=np.nan, ci_hi=np.nan,
                               n=int(len(j)), n_exc=0))
        print(f"{nice:>10} {dT:>+8.2f} {dRH:>+9.1f} {dW:>+12.2f}")

    # ================= WBGT TRACK, FULL WINDOW APPENDIX =================
    print("\n" + "-" * 78)
    print("appendix: IFS and GFS on their full window (all data, not the "
          "AIFS-limited common window)")
    print("-" * 78)
    print(hdr)
    for model, nice in (("ecmwf_ifs025", "IFS"), ("gfs_seamless", "GFS")):
        for lead in LEADS:
            fc, _ = forecast_wbgt_frame(model, lead)
            d = align(truth, fc, "wbgt_c", "wbgt_pred", CORE_MONTHS)
            cell = score_cell(d, "wbgt_full", nice, lead, "core", nb)
            scores.extend(cell)
            if lead in (1, HEADLINE_LEAD, 7):
                g = {r["metric"]: r for r in cell}
                print(f"{nice:>10} {lead:>4} {g['bias']['n']:>6} "
                      f"{g['miss_rate']['n_exc']:>6} {g['mae']['value']:>6.2f} "
                      f"{g['rmse']['value']:>6.2f} {g['bias']['value']:>+7.2f}  "
                      f"{g['miss_rate']['value']:>6.2f} "
                      f"[{g['miss_rate']['ci_lo']:.2f},{g['miss_rate']['ci_hi']:.2f}]"
                      f"      {g['fpr']['value']:>5.2f}")

    # shoulder-season stratum (Apr + Oct), full window, headline lead
    print(f"\nshoulder season (Apr + Oct), lead {HEADLINE_LEAD} d, full window:")
    for model, nice in WBGT_MODELS.items():
        fc, _ = forecast_wbgt_frame(model, HEADLINE_LEAD)
        ds = align(truth, fc, "wbgt_c", "wbgt_pred", SHOULDER_MONTHS)
        n_exc = int((ds["true_"] > THR).sum())
        if n_exc >= MIN_SHOULDER_EXC:
            cell = score_cell(ds, "wbgt_shoulder", nice, HEADLINE_LEAD,
                              "shoulder", nb)
            scores.extend(cell)
            g = {r["metric"]: r for r in cell}
            print(f"{nice:>10}: n={len(ds)} n_exc={n_exc} "
                  f"bias={g['bias']['value']:+.2f} "
                  f"miss={g['miss_rate']['value']:.2f} "
                  f"[{g['miss_rate']['ci_lo']:.2f},{g['miss_rate']['ci_hi']:.2f}]")
        else:
            print(f"{nice:>10}: only {n_exc} exceedance hours in Apr+Oct "
                  f"daylight -- not scored")

    # ================= TEMPERATURE TRACK ===============================
    print("\n" + "=" * 78)
    print("Temperature track -- 2 m T, GraphCast included, common window per "
          "lead across whichever models have data")
    print("=" * 78)
    tt = truth[_season_daylight(truth["time"], CORE_MONTHS)].copy()
    tt["year"] = _local(tt["time"]).dt.year.to_numpy()
    thot = {}
    for y in sorted(tt["year"].unique()):
        prior = tt.loc[tt["year"] < y, "temperature_2m"].to_numpy()
        thot[y] = float(np.percentile(prior, THOT_PCTL)) if len(prior) else np.nan
    print("hot-hour T thresholds (prior-years 95th pct):",
          {int(k): round(v, 1) for k, v in thot.items() if k >= 2024})

    thdr = (f"{'model':>10} {'lead':>4} {'n':>6} {'n_hot':>6} {'MAE':>6} "
            f"{'bias':>7}  {'miss_hot (95% CI)':>20}")
    temp_aln: dict[tuple[str, int], pd.DataFrame] = {}
    for lead in LEADS:
        raw = {}
        for model, nice in TEMP_MODELS.items():
            fc = forecast_temp_frame(model, lead)
            a = align(truth, fc, "temperature_2m", "t_pred", CORE_MONTHS)
            yr = _local(a["time"]).dt.year.to_numpy()
            a["thr_row"] = np.array([thot.get(y, np.nan) for y in yr])
            raw[nice] = a.dropna(subset=["thr_row"]).reset_index(drop=True)
        common = set.intersection(*[set(a["time"]) for a in raw.values()])
        common = pd.Index(sorted(common))
        print(f"\nlead {lead} d   (common n = {len(common)} hours -- GraphCast "
              f"gaps bind this)")
        print(thdr)
        for nice in TEMP_MODELS.values():
            d = raw[nice][raw[nice]["time"].isin(common)].reset_index(drop=True)
            temp_aln[(nice, lead)] = d
            cell = score_cell(d, "temp_common", nice, lead, "core", nb,
                              thr_col="thr_row")
            scores.extend(cell)
            g = {r["metric"]: r for r in cell}
            n_hot = int((d["true_"] >= d["thr_row"]).sum())
            flag = " *" if nice in SMALL_SAMPLE else \
                (" g" if nice == "GraphCast" else "")
            if g:
                print(f"{nice:>10} {lead:>4} {g['bias']['n']:>6} {n_hot:>6} "
                      f"{g['mae']['value']:>6.2f} {g['bias']['value']:>+7.2f}  "
                      f"{g['miss_rate']['value']:>6.2f} "
                      f"[{g['miss_rate']['ci_lo']:.2f},{g['miss_rate']['ci_hi']:.2f}]"
                      f"{flag}")
            preonset.extend(preonset_rows(d, onsets_t, "temp", nice, lead, nb))
    print("\n  * AIFS small sample.   g GraphCast: sparse feed, common window "
          "is small; read with care.")

    print(f"\npre-heat-wave 2 m T bias, {HEADLINE_W} d before onset "
          f"(C; all-days in parens):")
    print(f"{'model':>10} " + " ".join(f"{f'L{n}':>15}" for n in LEADS))
    for nice in TEMP_MODELS.values():
        cells = []
        for lead in LEADS:
            r = next((x for x in preonset if x["track"] == "temp"
                      and x["model"] == nice and x["lead"] == lead
                      and x["window_days"] == HEADLINE_W), None)
            cells.append(f"{r['bias']:+.2f}({r['all_days_bias']:+.2f})"
                         if r and np.isfinite(r["bias"]) else "-")
        print(f"{nice:>10} " + " ".join(f"{c:>15}" for c in cells))

    # ---- GraphCast hybrid WBGT (time-boxed appendix) -----------------
    # GraphCast serves no humidity or radiation, so a GraphCast WBGT cannot
    # be built. As a bound: splice GraphCast 2 m T into IFS humidity, wind
    # and radiation at the same valid hours and score the stop-work miss
    # rate. This is a synthetic hybrid, not any real system's output.
    print("\n" + "-" * 78)
    print("appendix (synthetic): WBGT from GraphCast 2 m T + IFS humidity/"
          "wind/radiation -- not a real forecast, a bound on GraphCast's T "
          "error at the 32.1 C decision")
    print("-" * 78)
    print(f"{'lead':>4} {'n':>6} {'n_exc':>6} {'bias':>7}  "
          f"{'miss@32.1 (95% CI)':>22}")
    for lead in LEADS:
        gc = pd.read_csv(PREV / f"gfs_graphcast025__lead{lead}d.csv",
                         usecols=["time", "temperature_2m"])
        gc["time"] = pd.to_datetime(gc["time"], utc=True)
        ifs = pd.read_csv(PREV / f"ecmwf_ifs025__lead{lead}d.csv")
        ifs["time"] = pd.to_datetime(ifs["time"], utc=True)
        h = ifs.drop(columns=["temperature_2m"]).merge(
            gc, on="time", how="inner").dropna()
        if len(h) < 200:
            print(f"{lead:>4}   (only {len(h)} hybrid rows)")
            continue
        w = wbgt_from_forecast_frame(h, DOHA_LAT, DOHA_LON)
        fc = pd.DataFrame({"time": h["time"].to_numpy(),
                           "wbgt_pred": np.asarray(w)})
        d = align(truth, fc, "wbgt_c", "wbgt_pred", CORE_MONTHS)
        if len(d) < 100:
            print(f"{lead:>4}   (only {len(d)} aligned rows)")
            continue
        cell = score_cell(d, "graphcast_hybrid_wbgt", "GraphCast+IFS", lead,
                          "core", nb)
        scores.extend(cell)
        g = {r["metric"]: r for r in cell}
        print(f"{lead:>4} {g['bias']['n']:>6} {g['miss_rate']['n_exc']:>6} "
              f"{g['bias']['value']:>+7.2f}  {g['miss_rate']['value']:>6.2f} "
              f"[{g['miss_rate']['ci_lo']:.2f},{g['miss_rate']['ci_hi']:.2f}]")

    # ---- wind check ------------------------------------------------
    print("\nforecast wind minus truth (METAR-patched) wind, core-season "
          "daylight, lead 1 d  [low forecast wind inflates forecast WBGT, "
          "masking a cold bias]:")
    tw = pd.read_csv(PATCHED_CSV, usecols=["time", "wind_speed_10m"])
    tw["time"] = pd.to_datetime(tw["time"], utc=True)
    for model, nice in WBGT_MODELS.items():
        fc = pd.read_csv(PREV / f"{model}__lead1d.csv",
                         usecols=["time", "wind_speed_10m"])
        fc["time"] = pd.to_datetime(fc["time"], utc=True)
        m = tw.merge(fc, on="time", suffixes=("_t", "_f"))
        m = m[_season_daylight(m["time"], CORE_MONTHS)].dropna()
        dw = float((m["wind_speed_10m_f"] - m["wind_speed_10m_t"]).mean())
        scores.append(dict(track="wind_check", model=nice, lead=1, season="core",
                           metric="fc_minus_truth_wind_ms", value=round(dw, 3),
                           ci_lo=np.nan, ci_hi=np.nan, n=int(len(m)), n_exc=0))
        print(f"  {nice:>10}: {dw:+.2f} m/s  (n={len(m)})")

    print(f"\nErbs direct-beam fallback: "
          + (f"used for {erbs}" if erbs else "not triggered (all WBGT-track "
             "models serve direct_radiation)."))

    pd.DataFrame(scores).to_csv(args.out_scores, index=False)
    pd.DataFrame(preonset).to_csv(args.out_preonset, index=False)
    pd.DataFrame(bands).to_csv(
        args.out_scores.with_name("aiwp_band_bias.csv"), index=False)
    print(f"\nwrote {args.out_scores} ({len(scores)}), "
          f"{args.out_preonset} ({len(preonset)}), aiwp_band_bias.csv "
          f"({len(bands)})")


if __name__ == "__main__":
    main()
