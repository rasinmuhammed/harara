"""
EMOS / NGR: the CRPS closed form, and that fitting recovers a known
bias + spread relationship and beats the raw ensemble on CRPS.
"""

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.emos import EMOS, gaussian_crps


def test_crps_matches_montecarlo():
    rng = np.random.default_rng(0)
    mu, sigma, y = 2.0, 1.3, 3.1
    draws = rng.normal(mu, sigma, 400_000)
    mc = np.mean(np.abs(draws - y)) - 0.5 * np.mean(
        np.abs(draws[:200_000] - draws[200_000:]))
    assert abs(float(gaussian_crps(mu, sigma, y)) - mc) < 0.01


def test_crps_zero_for_perfect_sharp_forecast():
    assert float(gaussian_crps(5.0, 1e-6, 5.0)) < 1e-3


def test_ngr_recovers_bias_and_calibrates_spread():
    rng = np.random.default_rng(1)
    n = 8000
    truth = rng.normal(30, 4, n)
    # raw ensemble: biased +1.5, and UNDER-dispersed (reports var 0.5 but
    # real error var is ~2.0)
    ens_mean = truth + 1.5 + rng.normal(0, np.sqrt(2.0 - 0.5), n)
    ens_var = np.full(n, 0.5)
    df = pd.DataFrame(dict(lead_h=36, month=7, ens_mean=ens_mean,
                           ens_var=ens_var, obs=truth))
    m = EMOS(min_cell=100).fit(df)
    mu, sigma = m.predict(ens_mean, ens_var, 36, 7)

    # bias removed
    assert abs(np.mean(mu - truth)) < 0.2
    # spread inflated toward the real error spread (~sqrt(2)=1.41)
    assert 1.0 < np.mean(sigma) < 2.2
    # calibrated CRPS beats raw-ensemble CRPS
    crps_cal = np.mean(gaussian_crps(mu, sigma, truth))
    crps_raw = np.mean(gaussian_crps(ens_mean, np.sqrt(ens_var), truth))
    assert crps_cal < crps_raw * 0.9


def test_thin_cell_pools_and_flags():
    rng = np.random.default_rng(2)
    rows = []
    for month, k in [(6, 2000), (7, 2000), (5, 20)]:      # May is thin
        t = rng.normal(29, 3, k)
        rows.append(pd.DataFrame(dict(
            lead_h=36, month=month, ens_mean=t + 1 + rng.normal(0, 1, k),
            ens_var=np.full(k, 1.0), obs=t)))
    m = EMOS(min_cell=150).fit(pd.concat(rows, ignore_index=True))
    assert m.is_pooled(36, 5)
    assert not m.is_pooled(36, 7)
    mu, sigma = m.predict(np.array([30.0]), np.array([1.0]), 36, 5)
    assert np.isfinite(mu).all() and np.isfinite(sigma).all()


def test_roundtrip_serialisation():
    rng = np.random.default_rng(3)
    t = rng.normal(30, 4, 3000)
    df = pd.DataFrame(dict(lead_h=36, month=7, ens_mean=t + 1,
                           ens_var=np.full(3000, 1.0), obs=t))
    m = EMOS(min_cell=100).fit(df)
    m2 = EMOS.from_dict(m.to_dict())
    a = m.predict(t + 1, np.ones_like(t), 36, 7)
    b = m2.predict(t + 1, np.ones_like(t), 36, 7)
    assert np.allclose(a[0], b[0]) and np.allclose(a[1], b[1])
