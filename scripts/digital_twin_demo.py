"""
scripts/digital_twin_demo.py

Proof-of-concept for the individual heat-strain digital twin, on SYNTHETIC
physiology (no pilot data yet). Over many real Doha summer days:

  1. Estimation: generate ground-truth core temperature + HR with the
     two-node model for a worker on a work/rest schedule; add realistic
     sensor noise; recover core temperature with the physics particle
     filter (HR + noisy activity estimate). Compare to an ECTemp-style
     HR-only Kalman filter whose HR<->core curve is fit on the same data.
     Report bias, RMSE, and 95%-interval coverage.

  2. Anticipation: part-way through each day, run the filter's forward
     prediction under an ensemble of same-day WBGT scenarios and score
     "core will exceed 38.5 C within 60 min": precision/recall, lead time,
     probability calibration.

Everything here is synthetic and is a method check, not a validated
result - the pilot supplies the ground truth (ingestible capsules) that
turns this into evidence.

Run:  python scripts/digital_twin_demo.py
"""

import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.heat_strain_filter import HeatStrainParticleFilter
from src.thermoreg import Subject, ThermoState, simulate

RNG = np.random.default_rng(2026)
THRESH = 38.5
N_DAYS = 30
PRED_HORIZON_MIN = 60
CHECK_EVERY = 20            # run the forward prediction this often (min)


def load_summer_days():
    w = pd.read_csv(REPO / "data" / "doha_weather_16yr_patched.csv")
    w["time"] = pd.to_datetime(w["time"], utc=True)
    w["local"] = w["time"].dt.tz_convert("Asia/Qatar")
    w = w[w["local"].dt.month.isin([6, 7, 8]) & w["local"].dt.hour.between(5, 18)]
    w["date"] = w["local"].dt.date
    days = []
    for d, g in w.groupby("date"):
        g = g.sort_values("local")
        if len(g) < 13:
            continue
        days.append(dict(
            date=d,
            hour=g["local"].dt.hour.to_numpy() + g["local"].dt.minute.to_numpy() / 60,
            t_air=g["temperature_2m"].to_numpy(),
            rh=g["relative_humidity_2m"].to_numpy(),
            wind=g["wind_speed_10m"].to_numpy(),
        ))
    RNG.shuffle(days)
    return days[:N_DAYS]


def minute_grid(day):
    """Interpolate the hourly day onto a 1-min grid, 06:00-17:00 local."""
    mins = np.arange(6 * 60, 17 * 60 + 1, 1.0)
    hh = mins / 60.0
    return dict(
        mins=mins - 6 * 60,
        t_air=np.interp(hh, day["hour"], day["t_air"]),
        rh=np.interp(hh, day["hour"], day["rh"]),
        wind=np.clip(np.interp(hh, day["hour"], day["wind"]), 0.2, None),
    )


def work_schedule(n_min):
    """A moderate-heavy crew: 40 min work / 20 min rest, met in W/m2."""
    t = np.arange(n_min)
    return np.where((t % 60) < 40, 315.0, 75.0)


def ectemp_fit_run(hr_train, ct_train, hr_run):
    """Fit HR = b0+b1*CT+b2*CT^2 on (hr,ct)_train, then EKF over hr_run."""
    A = np.vstack([np.ones_like(ct_train), ct_train, ct_train ** 2]).T
    b0, b1, b2 = np.linalg.lstsq(A, hr_train, rcond=None)[0]
    resid = hr_train - A @ np.array([b0, b1, b2])
    s2 = float(np.var(resid)) + 1e-6
    g = 0.000484                                    # Buller 2013 process var
    ct, p = 37.0, 0.0
    out = []
    for h in hr_run:
        p += g
        c = b1 + 2 * b2 * ct
        k = p * c / (c * c * p + s2)
        ct = ct + k * (h - (b0 + b1 * ct + b2 * ct * ct))
        p = (1 - k * c) * p
        out.append(ct)
    return np.array(out)


def main():
    days = load_summer_days()
    print(f"synthetic runs on {len(days)} real Doha summer days "
          f"(Jun-Aug), 06:00-17:00 local\n")

    pf_err, ec_err, cov = [], [], []
    pf2_err, cov2 = [], []                 # HR + skin-temp patch variant
    pred_rows = []
    lead_times = []                        # min between first alarm and true crossing

    for di, day in enumerate(days):
        env = minute_grid(day)
        n = len(env["mins"])
        met = work_schedule(n)
        sub = Subject(mass_kg=float(RNG.normal(72, 7)),
                      height_m=float(RNG.normal(1.72, 0.06)),
                      hr_rest=float(RNG.normal(68, 6)))

        truth = simulate(sub, env["mins"], env["t_air"], env["rh"], env["wind"],
                         met, st0=ThermoState(36.9, 34.5))
        ct_true, hr_true = truth["t_cr"], truth["hr"]

        hr_obs = hr_true + RNG.normal(0, 4.0, n)
        drop = RNG.random(n) < 0.03
        hr_obs[drop] = np.nan
        met_est = met * RNG.lognormal(0, 0.18, n)
        tsk_obs = truth["t_sk"] + RNG.normal(0, 0.4, n)      # skin-patch reading

        # ---- physics particle filter, two sensor configs ----
        pf = HeatStrainParticleFilter(sub, n=500, seed=di)          # HR only
        pf2 = HeatStrainParticleFilter(sub, n=500, seed=di + 999)   # HR + skin
        est, lo, hi = np.empty(n), np.empty(n), np.empty(n)
        est2, lo2, hi2 = np.empty(n), np.empty(n), np.empty(n)
        est[0], lo[0], hi[0] = pf.core_mean, *pf.core_ci()
        est2[0], lo2[0], hi2[0] = pf2.core_mean, *pf2.core_ci()
        last_hr = hr_obs[0] if np.isfinite(hr_obs[0]) else hr_true[0]
        alarm_min = None
        for i in range(1, n):
            h = hr_obs[i] if np.isfinite(hr_obs[i]) else last_hr
            last_hr = h
            pf.update(60.0, env["t_air"][i], env["rh"][i], env["wind"][i], None,
                      met_est[i], h)
            pf2.update(60.0, env["t_air"][i], env["rh"][i], env["wind"][i], None,
                       met_est[i], h, tsk_obs=tsk_obs[i])
            est[i], (lo[i], hi[i]) = pf.core_mean, pf.core_ci()
            est2[i], (lo2[i], hi2[i]) = pf2.core_mean, pf2.core_ci()

            # ---- anticipation checkpoints ----
            if i >= 75 and i % CHECK_EVERY == 0 and i + PRED_HORIZON_MIN < n:
                H = PRED_HORIZON_MIN
                step = 5
                idx = np.arange(i, i + H, step)
                nS = 24
                scn = {
                    "t_air": env["t_air"][idx][None, :] + RNG.normal(0, 1.8, (nS, 1)),
                    "rh": np.clip(env["rh"][idx][None, :]
                                  + RNG.normal(0, 9, (nS, 1)), 3, 100),
                    "wind": np.clip(env["wind"][idx][None, :]
                                    * RNG.lognormal(0, 0.30, (nS, 1)), 0.2, None),
                }
                met_blocks = np.array([met[i + j:i + j + step].mean()
                                       for j in range(0, H, step)])
                pr = pf2.predict_forward(scn, met_blocks, dt_s=step * 60.0,
                                         threshold=THRESH, n_sub=40)
                win = ct_true[i:i + H]
                actual = win.max() >= THRESH
                # minutes from this checkpoint to the first crossing anywhere
                # later in the day (np.inf if none)
                later = np.where(ct_true[i:] >= THRESH)[0]
                t_to_cross = float(later[0]) if len(later) else np.inf
                pred_rows.append(dict(p=pr.p_exceed, actual=actual,
                                      t_to_cross=t_to_cross))

        e = est[1:] - ct_true[1:]
        pf_err.append(e)
        pf2_err.append(est2[1:] - ct_true[1:])
        cov.append(np.mean((ct_true[1:] >= lo[1:]) & (ct_true[1:] <= hi[1:])))
        cov2.append(np.mean((ct_true[1:] >= lo2[1:]) & (ct_true[1:] <= hi2[1:])))

        # ECTemp: fit on the first 40% of THIS day, run on the rest
        cut = int(n * 0.4)
        ec = ectemp_fit_run(hr_true[:cut], ct_true[:cut], hr_obs[cut:])
        ec = np.where(np.isfinite(ec), ec, np.nan)
        ec_err.append(ec - ct_true[cut:])

    pf_e = np.concatenate(pf_err)
    pf2_e = np.concatenate(pf2_err)
    ec_e = np.concatenate([x[np.isfinite(x)] for x in ec_err])
    print("=== 1. Core-temperature estimation (pooled over all runs) ===")
    print(f"  {'method':<32}{'bias':>8}{'RMSE':>8}{'MAE':>8}{'95% cover':>11}")
    print(f"  {'ECTemp-style HR-only EKF':<32}{np.nanmean(ec_e):>+8.3f}"
          f"{np.sqrt(np.nanmean(ec_e**2)):>8.3f}{np.nanmean(np.abs(ec_e)):>8.3f}"
          f"{'--':>11}")
    print(f"  {'physics PF, HR + activity':<32}{np.nanmean(pf_e):>+8.3f}"
          f"{np.sqrt(np.nanmean(pf_e**2)):>8.3f}{np.nanmean(np.abs(pf_e)):>8.3f}"
          f"{np.mean(cov)*100:>10.0f}%")
    print(f"  {'physics PF, HR + activity + skin':<32}{np.nanmean(pf2_e):>+8.3f}"
          f"{np.sqrt(np.nanmean(pf2_e**2)):>8.3f}{np.nanmean(np.abs(pf2_e)):>8.3f}"
          f"{np.mean(cov2)*100:>10.0f}%")

    P = pd.DataFrame(pred_rows)
    print(f"\n=== 2. Anticipation: 'core > {THRESH} C within {PRED_HORIZON_MIN} min' "
          f"({len(P)} checkpoints, base rate {P['actual'].mean()*100:.0f}%) ===")
    for thr in (0.2, 0.35, 0.5):
        pos = P["p"] >= thr
        tp = (pos & P["actual"]).sum()
        print(f"  alarm if p>={thr:.2f}:  precision {tp/max(pos.sum(),1)*100:4.0f}%   "
              f"recall {tp/max(P['actual'].sum(),1)*100:4.0f}%   "
              f"alarms on {pos.mean()*100:3.0f}% of checks")
    print("  calibration (predicted p vs observed frequency):")
    P["bin"] = pd.cut(P["p"], [0, .1, .3, .5, .7, 1.01])
    for b, g in P.groupby("bin", observed=True):
        if len(g):
            print(f"    p in {str(b):<12}: predicted ~{g['p'].mean():.2f}  "
                  f"observed {g['actual'].mean():.2f}  (n={len(g)})")
    # time-resolved: mean forward p_exceed vs how long until the real crossing
    print("  forward p_exceed vs minutes-until-true-crossing (event days only):")
    ev = P[np.isfinite(P["t_to_cross"])].copy()
    ev["ttc_bin"] = pd.cut(ev["t_to_cross"], [-1, 15, 30, 45, 60, 90, 1e9],
                           labels=["0-15", "15-30", "30-45", "45-60", "60-90", ">90"])
    for b, g in ev.groupby("ttc_bin", observed=True):
        if len(g):
            print(f"    {b:>6} min out: mean p {g['p'].mean():.2f}  (n={len(g)})")

    print("\n=== LIMITATIONS ===")
    for L in [
        "All physiology is synthetic (two-node rational model); no pilot "
        "core-temperature data. Absolute error numbers are indicative, not "
        "validated.",
        "The forward model and the filter's process model are the SAME "
        "family -> real-world error will be larger; the pilot quantifies the "
        "model-mismatch gap.",
        "Activity input is a lognormal-perturbed truth; real accelerometry "
        "-> metabolic-rate mapping is noisier and biased.",
        "Same-day WBGT scenario ensemble is a hand-tuned perturbation, not "
        "a real forecast ensemble (couple to forecast_uncertainty / GEFS).",
        "One clothing / hydration state; no circadian, no illness, no "
        "individual acclimatization trajectory.",
        "ECTemp baseline uses generic process variance and a per-day fit; a "
        "population-calibrated ECTemp would do better than shown.",
    ]:
        print(f"  - {L}")


if __name__ == "__main__":
    main()
