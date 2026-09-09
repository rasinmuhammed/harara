"""
Unit tests for the pure helpers in scripts/twin_external_validation.py.

The full validation needs the PROSPIE workbook (gitignored, fetched on
demand), so it is not exercised here; these cover the metabolic-rate
conversion, the leave-one-subject-out ECTemp curve, and the
repeated-measures aggregation.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts.twin_external_validation import (
    aggregate, fit_ectemp_curve, run_ectemp, _met_wm2,
)


def test_met_wm2_rest_and_walk():
    speed = np.array([0.0, 5.0])          # km/h
    grade = np.array([0.0, 0.0])
    workrest = np.array([0.0, 1.0])
    vo2 = np.array([np.nan, np.nan])
    met = _met_wm2(speed, grade, workrest, vo2)
    assert 55.0 <= met[0] <= 90.0                       # ~1.2 MET rest
    assert met[1] > met[0] + 40.0                       # brisk walk is higher
    assert np.all(met <= 550.0)                         # clipped


def test_met_wm2_uses_measured_vo2_when_present():
    met = _met_wm2(np.array([4.0]), np.array([0.0]),
                   np.array([1.0]), np.array([25.0]))   # ~7 MET, below the clip
    assert abs(met[0] - 25.0 / 3.5 * 58.15) < 1e-6


def test_ectemp_curve_recovers_a_monotone_relationship():
    rng = np.random.default_rng(0)
    # a realistic core-temperature trajectory (slow rise then plateau), which
    # is what the random-walk EKF assumes
    t = np.arange(1200)
    core = 37.0 + 1.8 * (1 - np.exp(-t / 300.0)) + rng.normal(0, 0.03, t.size)
    hr = 60 + 25 * (core - 37.0) + rng.normal(0, 4, core.size)
    (b0, b1, b2), s2 = fit_ectemp_curve(hr, core)
    grid = np.linspace(36.5, 39.5, 20)
    assert np.all(b1 + 2 * b2 * grid > 0)                # dHR/dCT > 0
    assert 0 < s2 < 400
    est = run_ectemp(hr, ((b0, b1, b2), s2))
    assert np.corrcoef(est, core)[0, 1] > 0.9
    assert abs(np.mean(est - core)) < 0.15              # roughly unbiased


def test_aggregate_bland_altman_on_two_subjects():
    # subject A: unbiased; subject B: +0.4 C offset. Two trials each.
    rows = [
        {"pid": 1, "condition": 1, "bias": 0.05, "rmse": 0.2, "mae": 0.15},
        {"pid": 1, "condition": 2, "bias": -0.05, "rmse": 0.2, "mae": 0.15},
        {"pid": 2, "condition": 1, "bias": 0.40, "rmse": 0.5, "mae": 0.42},
        {"pid": 2, "condition": 2, "bias": 0.40, "rmse": 0.5, "mae": 0.42},
    ]
    out = aggregate(rows)
    p = out["point"]
    assert out["n_subjects"] == 2 and out["n_trials"] == 4
    assert abs(p["bias"] - 0.20) < 1e-6                 # mean of subject means
    assert p["loa_lo"] < p["bias"] < p["loa_hi"]
    assert out["ci95"]["bias"][0] <= p["bias"] <= out["ci95"]["bias"][1]
