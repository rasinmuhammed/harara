"""
scripts/twin_external_validation.py

External validation of the heat-strain particle filter (src.heat_strain_filter)
on REAL physiology, against a rectal-temperature gold standard.

Dataset: PROSPIE (Loughborough University), figshare
    DOI 10.17028/rd.lboro.26076577.v1  (CC BY-NC 4.0)
    file: data/prospie/prospie.xlsx  ("Data" sheet)
Havenith, Davey, Downie, Griggs, Richmond. Treadmill walking in a climate
chamber, 1-min resolution: rectal temperature (10 cm probe, the stated gold
standard), heart rate, 11-site skin temperature, insulated skin temperature,
microclimate T/RH, treadmill speed and grade, permeable / impermeable
clothing, some trials with 600 W/m^2 radiant load.

What is compared, on the SAME trials:
  ECTemp-class HR-only EKF   population HR<->core curve fit leave-one-subject-out,
                             Buller (2013) process variance. The conventional
                             baseline.
  PF (HR only)               src.heat_strain_filter with heart rate only.
  PF (HR + skin)             same, plus the mean-skin-temperature channel.

Nothing is tuned on the scored subject: the particle filter runs on library
defaults (no fitting anywhere), and the ECTemp curve for subject s is fit on
every OTHER subject only.

Metrics (per trial, then aggregated as a mixed model with subject as the
random effect): bias = mean(pred - rectal), RMSE, MAE, and for the PF the
95% credible-interval coverage. Bland-Altman for repeated measures (Bland &
Altman 1999): bias and 95% limits of agreement from between- plus
within-subject variance. 95% CIs by cluster bootstrap over subjects
(seed 0, 2000 resamples).

Run:  python scripts/twin_external_validation.py
Out:  data/twin_external_validation.json  + a printed table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import urllib.request

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.heat_strain_filter import HeatStrainParticleFilter
from src.thermoreg import Subject

XLSX = REPO / "data" / "prospie" / "prospie.xlsx"
OUT = REPO / "data" / "twin_external_validation.json"
FIGSHARE_URL = "https://ndownloader.figshare.com/files/47227096"
FIGSHARE_MD5 = "cdbdb0795d3c5d2923d199466513c163"


def fetch() -> None:
    XLSX.parent.mkdir(parents=True, exist_ok=True)
    if XLSX.exists() and hashlib.md5(XLSX.read_bytes()).hexdigest() == FIGSHARE_MD5:
        return
    print(f"downloading PROSPIE ({FIGSHARE_URL}) ...")
    req = urllib.request.Request(FIGSHARE_URL, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=120).read()  # noqa: S310
    got = hashlib.md5(data).hexdigest()
    if got != FIGSHARE_MD5:
        sys.exit(f"md5 mismatch: got {got}, expected {FIGSHARE_MD5}")
    XLSX.write_bytes(data)
    print(f"wrote {XLSX} ({len(data) / 1e6:.1f} MB)")
MISSING = 9999.0
BURN_IN_MIN = 8            # discard while the filter converges from its prior
MIN_SCORED_MIN = 20        # a trial must have this many scored minutes
SEED = 0
N_BOOT = 2000

# ISO 9886 area weights for a mean skin temperature from the 11 sites present.
SKIN_WEIGHTS = {
    "SkinTemp|head": 0.07, "SkinTemp|abdomen": 0.175, "SkinTemp|chest": 0.175,
    "SkinTemp|upper back": 0.0, "SkinTemp|lower back": 0.0,
    "SkinTemp|upper arm": 0.07, "SkinTemp|lower arm": 0.07, "SkinTemp|hand": 0.05,
    "SkinTemp|thigh": 0.19, "SkinTemp|calf": 0.20, "SkinTemp|foot": 0.05,
}


# --------------------------------------------------------------------- load
def _columns(raw: pd.DataFrame) -> list[str]:
    top = raw.iloc[0].ffill()
    sub = raw.iloc[1]
    out = []
    for a, b in zip(top, sub):
        a = "" if pd.isna(a) else str(a).strip()
        b = "" if pd.isna(b) else str(b).strip()
        out.append((a + "|" + b).strip("|"))
    return out


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").replace(MISSING, np.nan)


def _met_wm2(speed_kmh: np.ndarray, grade_pct: np.ndarray,
             workrest: np.ndarray, vo2_meas: np.ndarray) -> np.ndarray:
    """Metabolic rate in W/m^2. Prefer the measured VO2; otherwise the ACSM
    walking equation from treadmill speed and grade; rest = 1.2 MET."""
    v_mmin = np.nan_to_num(speed_kmh, nan=0.0) * 1000.0 / 60.0
    g = np.nan_to_num(grade_pct, nan=0.0) / 100.0
    vo2_acsm = 3.5 + 0.1 * v_mmin + 1.8 * v_mmin * g          # ml/kg/min
    resting = (np.nan_to_num(workrest, nan=1.0) <= 0) | (v_mmin < 1.0)
    vo2_acsm = np.where(resting, 4.2, vo2_acsm)
    vo2 = np.where(np.isfinite(vo2_meas) & (vo2_meas > 3.0), vo2_meas, vo2_acsm)
    return np.clip(vo2 / 3.5 * 58.15, 55.0, 550.0)             # 1 MET = 58.15 W/m^2


def load_trials() -> list[dict]:
    raw = pd.read_excel(XLSX, sheet_name="Data", header=None)
    cols = _columns(raw)
    df = raw.iloc[2:].reset_index(drop=True)
    df.columns = cols

    cond, pid = cols[0], "Participant"
    skin_cols = [c for c in cols if c.startswith("SkinTemp|")]
    trials = []
    for (c, p), g in df.groupby([cond, pid]):
        g = g.reset_index(drop=True)
        core = _num(g["Corerectal"]).to_numpy()
        hr = _num(g["InsulatedskinTemp|HR"]).to_numpy()
        t_air = _num(g["Environmental temperature (chamber or cooling area outside chamber)|Temp"]).to_numpy()
        rh = _num(g["Environmental temperature (chamber or cooling area outside chamber)|Humidity"]).to_numpy()
        wind = _num(g["Environmental temperature (chamber or cooling area outside chamber)|Wind"]).to_numpy()
        solar = _num(g["Solar radiation (W.m2)|Overall (1.00-1.70m)"]).to_numpy()
        speed = _num(g["Treadmillsettings|Speedkm.hr-1"]).to_numpy()
        grade = _num(g["Treadmillsettings|Gradient%"]).to_numpy()
        workrest = _num(g["Activity|workrest"]).to_numpy()
        vo2 = _num(g["OxygenConsumption|ml.kg.min"]).to_numpy()

        sk = np.array([_num(g[cn]).to_numpy() for cn in skin_cols], dtype=float)
        wts = np.array([SKIN_WEIGHTS.get(cn, 0.0) for cn in skin_cols])
        with np.errstate(invalid="ignore"):
            ok = np.isfinite(sk)
            wsum = (ok * wts[:, None]).sum(axis=0)
            tsk_mean = np.where(wsum > 0.4,
                                np.nansum(sk * wts[:, None], axis=0) / np.where(wsum > 0, wsum, np.nan),
                                np.nanmean(np.where(ok, sk, np.nan), axis=0))

        n = len(g)
        minute = np.arange(n, dtype=float)

        mass = float(_num(g["Bodymasskg"]).dropna().median())
        height = float(_num(g["Heightcm"]).dropna().median()) / 100.0
        age = float(_num(g["Age"]).dropna().median())
        sex = int(_num(g["Sex"]).dropna().median()) if _num(g["Sex"]).notna().any() else 0
        clothing = int(_num(g["Clothing"]).dropna().median()) if _num(g["Clothing"]).notna().any() else 1

        # environment: forward/back fill short gaps, clamp wind
        def fill(a, lo=None, hi=None):
            s = pd.Series(a).ffill(limit=3).bfill(limit=3)
            if lo is not None:
                s = s.clip(lower=lo)
            if hi is not None:
                s = s.clip(upper=hi)
            return s.to_numpy()

        t_air = fill(t_air)
        rh = fill(rh, 2.0, 100.0)
        wind = fill(wind, 0.1, 5.0)
        hr = pd.Series(hr).interpolate(limit=3, limit_area="inside").to_numpy()
        tsk_mean = pd.Series(tsk_mean).interpolate(limit=3, limit_area="inside").to_numpy()

        # chamber wind is often not logged; default to near-still air. Any
        # remaining env gap gets a physiologically neutral default so the
        # filter never sees a NaN forcing (these are not the scored quantity).
        t_air = np.where(np.isfinite(t_air), t_air, np.nanmedian(t_air) if np.isfinite(np.nanmedian(t_air)) else 30.0)
        rh = np.where(np.isfinite(rh), rh, np.nanmedian(rh) if np.isfinite(np.nanmedian(rh)) else 40.0)
        wind = np.where(np.isfinite(wind), wind, 0.3)

        met = _met_wm2(speed, grade, workrest, vo2)
        met = np.where(np.isfinite(met), met, 75.0)
        solar_on = np.isfinite(solar) & (solar > 50.0)
        # radiant temperature: chamber walls ~ air; add a globe rise under solar
        t_rad = np.where(solar_on, t_air + np.clip(solar, 0, 900) / 90.0, t_air)

        valid = np.isfinite(core) & np.isfinite(hr) & np.isfinite(t_air) & np.isfinite(met)
        if valid.sum() < BURN_IN_MIN + MIN_SCORED_MIN:
            continue
        if np.isfinite(t_air).mean() < 0.5:
            continue

        # resting HR estimate: 5th percentile of the first 10 valid minutes
        first = hr[valid][:10]
        hr_rest = float(np.nanpercentile(first, 5)) if first.size else 60.0
        hr_rest = float(np.clip(hr_rest, 40.0, 90.0))

        trials.append(dict(
            condition=int(c), pid=int(p), sex=sex, clothing=clothing,
            mass_kg=mass if np.isfinite(mass) else 74.0,
            height_m=height if np.isfinite(height) else 1.75,
            age=age if np.isfinite(age) else 30.0,
            hr_rest=hr_rest,
            solar=bool(solar_on.mean() > 0.2),
            minute=minute, valid=valid,
            core=core, hr=hr, tsk=tsk_mean,
            t_air=t_air, rh=rh, wind=wind, t_rad=t_rad, met=met,
        ))
    return trials


# ----------------------------------------------------------------- filters
def run_ectemp(hr_run: np.ndarray, curve, g_proc: float = 0.000484) -> np.ndarray:
    """ECTemp-class HR-only extended Kalman filter (Buller 2013 form) with a
    supplied population HR = b0 + b1*CT + b2*CT^2 curve and residual variance."""
    (b0, b1, b2), resid_s2 = curve
    ct, p = 37.0, 0.0
    out = np.empty(len(hr_run))
    for i, h in enumerate(hr_run):
        p += g_proc
        c = b1 + 2 * b2 * ct
        k = p * c / (c * c * p + resid_s2)
        ct = ct + k * (h - (b0 + b1 * ct + b2 * ct * ct))
        p = (1.0 - k * c) * p
        ct = min(max(ct, 34.0), 41.5)
        out[i] = ct
    return out


def fit_ectemp_curve(hr: np.ndarray, core: np.ndarray):
    """Population HR<->core curve: returns ((b0, b1, b2), residual_variance)."""
    m = np.isfinite(hr) & np.isfinite(core)
    ct = core[m]
    A = np.vstack([np.ones_like(ct), ct, ct ** 2]).T
    coef, *_ = np.linalg.lstsq(A, hr[m], rcond=None)
    resid = hr[m] - A @ coef
    return tuple(float(x) for x in coef), float(np.var(resid)) + 1e-6


def run_pf(tr: dict, use_skin: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    sub = Subject(mass_kg=float(tr["mass_kg"]), height_m=float(tr["height_m"]),
                  clo=0.9 if tr["clothing"] == 1 else 1.15,
                  hr_rest=float(tr["hr_rest"]),
                  hr_max=float(np.clip(211.0 - 0.64 * tr["age"], 160.0, 205.0)))
    pf = HeatStrainParticleFilter(sub, n=400, seed=SEED)
    n = len(tr["minute"])
    est = np.full(n, np.nan)
    lo = np.full(n, np.nan)
    hi = np.full(n, np.nan)
    hr_sd0, tsk_sd0 = pf.hr_sd, pf.tsk_sd
    K = 4                       # propagation sub-steps: assimilate once per minute,
    big = 1e12                  # integrate the two-node model in 15 s steps so the
    last_t = None               # skin node stays stable in hot-dry forcing
    for i in range(n):
        if not tr["valid"][i]:
            continue
        span = 1.0 if last_t is None else min(5.0, i - last_t)
        last_t = i
        tsk_obs = tr["tsk"][i] if (use_skin and np.isfinite(tr["tsk"][i])) else None
        for k in range(K):
            final = k == K - 1
            pf.hr_sd = hr_sd0 if final else big
            pf.tsk_sd = tsk_sd0 if final else big
            pf.update(span * 60.0 / K, float(tr["t_air"][i]), float(tr["rh"][i]),
                      float(tr["wind"][i]), float(tr["t_rad"][i]),
                      float(tr["met"][i]), float(tr["hr"][i]),
                      tsk_obs if final else None)
        pf.hr_sd, pf.tsk_sd = hr_sd0, tsk_sd0
        est[i] = pf.core_mean
        lo[i], hi[i] = pf.core_ci()
    return est, lo, hi


# ----------------------------------------------------------------- scoring
def trial_scores(core, est, lo, hi, scored) -> dict:
    d = est[scored] - core[scored]
    out = dict(n=int(scored.sum()),
               bias=float(np.mean(d)),
               rmse=float(np.sqrt(np.mean(d ** 2))),
               mae=float(np.mean(np.abs(d))))
    if lo is not None:
        cov = (core[scored] >= lo[scored]) & (core[scored] <= hi[scored])
        out["coverage95"] = float(np.mean(cov))
        out["ci_width"] = float(np.mean(hi[scored] - lo[scored]))
    return out


def _subject_means(rows: list[dict], key: str) -> dict[int, float]:
    by = {}
    for r in rows:
        by.setdefault(r["pid"], []).append(r[key])
    return {p: float(np.mean(v)) for p, v in by.items()}


def aggregate(rows: list[dict]) -> dict:
    """Mixed-model style aggregate: mean of per-subject means, plus a
    repeated-measures Bland-Altman, with cluster-bootstrap 95% CIs."""
    rng = np.random.default_rng(SEED)
    pids = sorted({r["pid"] for r in rows})
    by_pid = {p: [r for r in rows if r["pid"] == p] for p in pids}

    def point(sample_rows):
        sm = _subject_means(sample_rows, "bias")
        subj_bias = np.array(list(sm.values()))
        within_var = np.mean([np.var([r["bias"] for r in by], ddof=0)
                              for by in _group(sample_rows).values()])
        bias = float(np.mean(subj_bias))
        sd_tot = float(np.sqrt(np.var(subj_bias, ddof=0) + within_var))
        return dict(
            bias=bias,
            loa_lo=bias - 1.96 * sd_tot,
            loa_hi=bias + 1.96 * sd_tot,
            rmse=float(np.mean(list(_subject_means(sample_rows, "rmse").values()))),
            mae=float(np.mean(list(_subject_means(sample_rows, "mae").values()))),
            coverage95=(float(np.mean(list(_subject_means(sample_rows, "coverage95").values())))
                        if "coverage95" in sample_rows[0] else None),
        )

    est = point(rows)
    boots = {k: [] for k in est}
    for _ in range(N_BOOT):
        pick = rng.choice(pids, size=len(pids), replace=True)
        sample = [r for p in pick for r in by_pid[p]]
        b = point(sample)
        for k, v in b.items():
            if v is not None:
                boots[k].append(v)
    ci = {k: ([float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]
              if v else None) for k, v in boots.items()}
    return {"point": est, "ci95": ci, "n_subjects": len(pids),
            "n_trials": len(rows)}


def _group(rows):
    g = {}
    for r in rows:
        g.setdefault((r["pid"], r["condition"]), []).append(r)
    return g


# -------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true",
                    help="do not download the dataset if it is missing")
    args = ap.parse_args()
    if not args.no_fetch:
        fetch()
    if not XLSX.exists():
        sys.exit(f"missing {XLSX} - download from "
                 "https://doi.org/10.17028/rd.lboro.26076577")
    trials = load_trials()
    pids = sorted({t["pid"] for t in trials})
    print(f"PROSPIE: {len(trials)} usable trials, {len(pids)} subjects, "
          f"1-min resolution, rectal reference\n")

    # leave-one-subject-out ECTemp population curves
    curves = {}
    for p in pids:
        hr = np.concatenate([t["hr"][t["valid"]] for t in trials if t["pid"] != p])
        ct = np.concatenate([t["core"][t["valid"]] for t in trials if t["pid"] != p])
        curves[p] = fit_ectemp_curve(hr, ct)

    rows = {"ectemp": [], "pf_hr": [], "pf_hr_skin": []}
    per_trial = []
    for t in trials:
        v = t["valid"]
        scored = v.copy()
        idx = np.where(v)[0]
        if idx.size:
            scored[idx[idx < idx[0] + BURN_IN_MIN]] = False
        if scored.sum() < MIN_SCORED_MIN:
            continue

        ec = np.full(len(v), np.nan)
        ec[idx] = run_ectemp(t["hr"][idx], curves[t["pid"]])
        s_ec = trial_scores(t["core"], ec, None, None, scored)

        e1, l1, h1 = run_pf(t, use_skin=False)
        s1 = trial_scores(t["core"], e1, l1, h1, scored)

        has_skin = np.isfinite(t["tsk"][scored]).mean() > 0.5
        if has_skin:
            e2, l2, h2 = run_pf(t, use_skin=True)
            s2 = trial_scores(t["core"], e2, l2, h2, scored)
        else:
            s2 = None

        for tag, s in (("ectemp", s_ec), ("pf_hr", s1), ("pf_hr_skin", s2)):
            if s is None:
                continue
            s |= dict(pid=t["pid"], condition=t["condition"],
                      solar=t["solar"], clothing=t["clothing"])
            rows[tag].append(s)
        per_trial.append(dict(pid=t["pid"], condition=t["condition"],
                              n=int(scored.sum()),
                              ectemp_rmse=s_ec["rmse"], pf_hr_rmse=s1["rmse"],
                              pf_hr_skin_rmse=(s2["rmse"] if s2 else None)))

    report = {
        "dataset": {
            "name": "PROSPIE (Loughborough)",
            "doi": "10.17028/rd.lboro.26076577.v1",
            "licence": "CC BY-NC 4.0",
            "reference": "rectal probe (10 cm), stated gold standard",
            "resolution_min": 1,
            "n_subjects": len(pids),
            "n_trials_usable": len(trials),
        },
        "protocol": {
            "burn_in_min": BURN_IN_MIN,
            "loso": "ECTemp HR<->core curve fit on all other subjects; "
                    "particle filter on library defaults (no fitting)",
            "bootstrap": f"cluster over subjects, {N_BOOT} resamples, seed {SEED}",
        },
        "results": {tag: aggregate(rs) for tag, rs in rows.items() if rs},
    }

    # split: solar vs none, permeable vs impermeable (PF HR+skin)
    splits = {}
    for tag in ("pf_hr", "pf_hr_skin", "ectemp"):
        rs = rows[tag]
        for name, sel in (("solar", [r for r in rs if r["solar"]]),
                          ("no_solar", [r for r in rs if not r["solar"]]),
                          ("permeable", [r for r in rs if r["clothing"] == 1]),
                          ("impermeable", [r for r in rs if r["clothing"] != 1])):
            if len({r["pid"] for r in sel}) >= 4:
                splits.setdefault(tag, {})[name] = aggregate(sel)["point"]
    report["splits"] = splits

    OUT.write_text(json.dumps(report, indent=2))

    def line(tag, label):
        a = report["results"].get(tag)
        if not a:
            print(f"  {label:<22} (no trials)")
            return
        p, c = a["point"], a["ci95"]
        cov = f"  cov95 {p['coverage95']:.2f}" if p.get("coverage95") is not None else ""
        print(f"  {label:<22} bias {p['bias']:+.3f} "
              f"[{c['bias'][0]:+.3f},{c['bias'][1]:+.3f}]  "
              f"RMSE {p['rmse']:.3f} [{c['rmse'][0]:.3f},{c['rmse'][1]:.3f}]  "
              f"MAE {p['mae']:.3f}  "
              f"LoA [{p['loa_lo']:+.2f},{p['loa_hi']:+.2f}]{cov}")

    print(f"scored on {report['results']['pf_hr']['n_trials']} trials, "
          f"{report['results']['pf_hr']['n_subjects']} subjects "
          f"(deg C; bias = estimate minus rectal)\n")
    line("ectemp", "ECTemp HR-only EKF")
    line("pf_hr", "PF (HR only)")
    line("pf_hr_skin", "PF (HR + skin)")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
