"""
scripts/gefs_calibration.py

Walk-forward EMOS (nonhomogeneous Gaussian regression, CRPS-fit, per
lead x month) for the GEFS v12 reforecast WBGT at the Doha point, with
before/after diagnostics.

Target y  = patched-reanalysis WBGT at the valid time (data/doha_wbgt_16yr.csv).
Ensemble  = 5-member GEFS reforecast WBGT (Liljegren), per (init, lead).
Split     = expanding-window walk-forward by YEAR: year Y is scored using
            EMOS fit only on GEFS years strictly before Y (>= 3 needed),
            leak-free by construction.

Diagnostics per forecast day (pooling its 3 leads) and per lead:
  raw ensemble against EMOS-calibrated:
    RMSE of the (ensemble/EMOS) mean, mean spread, spread/RMSE ratio,
    mean CRPS, and the rank/PIT-histogram outer-bin mass.
  CRPSS(EMOS vs raw) with a moving-block-bootstrap 95% CI.
Open-Meteo blend MAE (~0.80 C at fday +1, technical_report S5) is printed
as a non-paired external reference - the two archives do not overlap in
time.

Writes the EMOS fit on all available years to data/gefs_emos.json for the
scheduler and the reliability study.

Run:  python scripts/gefs_calibration.py
"""

import json
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from src.emos import EMOS, gaussian_crps
from fetch_gefs_reforecast import compute_gefs_wbgt, load_gefs

RNG = np.random.default_rng(7)
MIN_TRAIN_YEARS = 3
BLENDS_REF_MAE = {1: 0.80, 2: 0.93, 3: 1.00}     # Open-Meteo blend, report S5


def block_ci(x, stat=np.mean, block=7, n=2000):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < block * 3:
        return (np.nan, np.nan)
    starts = np.arange(0, len(x) - block + 1)
    nb = int(np.ceil(len(x) / block))
    out = [stat(np.concatenate([x[a:a + block]
           for a in RNG.choice(starts, nb)])[:len(x)]) for _ in range(n)]
    return tuple(np.percentile(out, [2.5, 97.5]))


def rank_outer_mass(members, y, n_bins=None):
    """Fraction of obs falling in the outer 2 rank bins of an M-member
    ensemble (flat calibration -> 2/(M+1))."""
    M = members.shape[1]
    r = (members < y[:, None]).sum(1)                       # 0..M
    return np.mean((r == 0) | (r == M)), 2.0 / (M + 1)


def pit_outer_mass(mu, sigma, y):
    from scipy.stats import norm
    p = norm.cdf((y - mu) / np.maximum(sigma, 1e-6))
    return np.mean((p < 0.1) | (p > 0.9)), 0.2


def main():
    gefs = load_gefs()
    gefs["wbgt"], _ = compute_gefs_wbgt(gefs)
    gefs["local"] = gefs["valid_time"] + pd.Timedelta(hours=3)
    gefs["month"] = gefs["local"].dt.month
    gefs["year"] = gefs["local"].dt.year

    # ensemble moments per (init_time, lead_h)
    g = (gefs.groupby(["init_time", "valid_time", "lead_h", "fday", "month", "year"])
             ["wbgt"].agg(ens_mean="mean", ens_var=lambda s: s.var(ddof=1),
                          n_mem="count").reset_index())
    g = g[g["n_mem"] >= 2]

    # truth: patched reanalysis WBGT at the valid hour
    tr = pd.read_csv(REPO / "data" / "doha_wbgt_16yr.csv", usecols=["time", "wbgt_c"])
    tr["valid_time"] = pd.to_datetime(tr["time"], utc=True).dt.tz_localize(None)
    g = g.merge(tr[["valid_time", "wbgt_c"]].rename(columns={"wbgt_c": "obs"}),
                on="valid_time", how="inner").dropna(subset=["obs", "ens_mean", "ens_var"])
    if g.empty:
        raise SystemExit("no GEFS/patched-WBGT overlap yet - let the backfill run")

    years = sorted(g["year"].unique())
    print(f"GEFS x patched-WBGT overlap: {len(g)} (init,lead) rows, "
          f"years {years[0]}-{years[-1]} ({len(years)})")
    scored_years = [y for y in years if sum(yy < y for yy in years) >= MIN_TRAIN_YEARS]
    if not scored_years:
        print(f"  < {MIN_TRAIN_YEARS+1} years present -> walk-forward not possible "
              f"yet; showing a single leave-last-year fit as a preview.")
        scored_years = years[-1:]
        train_years_for = lambda y: [yy for yy in years if yy != y]
    else:
        train_years_for = lambda y: [yy for yy in years if yy < y]

    rows = []
    emos_last = None
    for y in scored_years:
        tr_df = g[g["year"].isin(train_years_for(y))]
        te_df = g[g["year"] == y].copy()
        m = EMOS().fit(tr_df[["lead_h", "month", "ens_mean", "ens_var", "obs"]])
        emos_last = m
        mu, sig = [], []
        for _, r in te_df.iterrows():
            a, b = m.predict(np.array([r.ens_mean]), np.array([r.ens_var]),
                             r.lead_h, r.month)
            mu.append(float(np.ravel(a)[0])); sig.append(float(np.ravel(b)[0]))
        te_df["mu"], te_df["sigma"] = mu, sig
        rows.append(te_df)
    R = pd.concat(rows, ignore_index=True)
    R["raw_sd"] = np.sqrt(R["ens_var"])
    R["crps_raw"] = gaussian_crps(R["ens_mean"].to_numpy(),
                                  R["raw_sd"].to_numpy(), R["obs"].to_numpy())
    R["crps_emos"] = gaussian_crps(R["mu"].to_numpy(),
                                   R["sigma"].to_numpy(), R["obs"].to_numpy())

    # ---- report ----
    print(f"\nscored years: {scored_years}   (train = strictly-earlier years)\n")
    hdr = (f"  {'grp':<10}{'n':>6}{'RMSEraw':>9}{'RMSEcal':>9}"
           f"{'spr/rmse raw':>13}{'sig/rmse cal':>13}"
           f"{'CRPSraw':>9}{'CRPScal':>9}{'CRPSS[95%CI]':>20}")
    print(hdr + "\n  " + "-" * (len(hdr) - 2))

    def line(tag, sub):
        rr = np.sqrt(np.mean((sub.ens_mean - sub.obs) ** 2))
        rc = np.sqrt(np.mean((sub.mu - sub.obs) ** 2))
        crps_r, crps_c = sub.crps_raw.mean(), sub.crps_emos.mean()
        crpss = 1 - crps_c / crps_r
        d = sub.crps_raw.to_numpy() - sub.crps_emos.to_numpy()
        lo, hi = block_ci(d)
        clo, chi = lo / crps_r, hi / crps_r
        print(f"  {tag:<10}{len(sub):>6}{rr:>9.2f}{rc:>9.2f}"
              f"{sub.raw_sd.mean() / rr:>13.2f}{sub.sigma.mean() / rc:>13.2f}"
              f"{crps_r:>9.2f}{crps_c:>9.2f}"
              f"{f'{crpss:+.2f} [{clo:+.2f},{chi:+.2f}]':>20}")

    for fd in (1, 2, 3):
        sub = R[R["fday"] == fd]
        if len(sub):
            line(f"fday +{fd}", sub)
            om, exp = rank_outer_mass(
                np.column_stack([sub["ens_mean"] - sub["raw_sd"],
                                 sub["ens_mean"], sub["ens_mean"] + sub["raw_sd"]]),
                sub["obs"].to_numpy())
            pom, pexp = pit_outer_mass(sub["mu"].to_numpy(), sub["sigma"].to_numpy(),
                                       sub["obs"].to_numpy())
            print(f"    calibration: raw-ens outer-rank mass ~{om:.2f} "
                  f"(flat {exp:.2f});  EMOS PIT outer-10% mass {pom:.2f} "
                  f"(flat {pexp:.2f})")
            print(f"    Open-Meteo blend MAE reference (non-paired): "
                  f"{BLENDS_REF_MAE[fd]:.2f} C  |  EMOS MAE here "
                  f"{np.mean(np.abs(sub.mu - sub.obs)):.2f} C")
    print()
    for L in sorted(R["lead_h"].unique()):
        line(f"lead {L}h", R[R["lead_h"] == L])

    pooled = sorted(emos_last.pooled)
    print(f"\nEMOS cells pooled for thin data (mostly May): {len(pooled)} "
          f"-> {pooled[:8]}{' ...' if len(pooled) > 8 else ''}")

    # fit on ALL years and persist for downstream
    full = EMOS().fit(g[["lead_h", "month", "ens_mean", "ens_var", "obs"]])
    (REPO / "data" / "gefs_emos.json").write_text(json.dumps(full.to_dict()))
    print(f"wrote data/gefs_emos.json (fit on all {len(years)} overlap years)")

    print("\n=== LIMITATIONS ===")
    for L in [
        f"GEFS x patched-WBGT overlap is only {len(years)} years; "
        f"walk-forward scores {len(scored_years)} of them -> wide CIs.",
        "Target is patched-reanalysis WBGT (its own ~1 C error, worse on "
        "dry-transition days, per report S5) - EMOS calibrates toward that, "
        "not toward station truth.",
        "Ensemble WBGT uses a fixed 1000 hPa and dswrf-derived direct beam "
        "(0.75 x global); the reforecast has no direct component.",
        "May is data-thin and its cells are pooled (flagged above).",
        "Rank histogram uses a 3-point pseudo-ensemble (mean +/- 1 SD) as "
        "a compact proxy; a full 5-member rank histogram needs the member "
        "WBGT columns, added when the backfill completes.",
    ]:
        print(f"  - {L}")


if __name__ == "__main__":
    main()
