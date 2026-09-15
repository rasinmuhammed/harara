import numpy as np
import pytest

from src.conformal import ConformalCorrection, coverage, fit_conformal


def _miscalibrated(rng, n, true_sd=1.0, stated_sd=0.3, bias=0.0):
    """A point estimator whose stated interval is too narrow: truth has
    std true_sd, but the estimator reports an interval built from a smaller
    stated_sd, so raw coverage is well under 95%."""
    y = rng.normal(0.0, true_sd, n)
    est = bias + rng.normal(0.0, 0.05, n)   # a near-unbiased point estimate
    lo = est - 1.96 * stated_sd
    hi = est + 1.96 * stated_sd
    return lo, hi, y


def test_raw_interval_is_undercovered():
    rng = np.random.default_rng(0)
    lo, hi, y = _miscalibrated(rng, 2000)
    assert coverage(lo, hi, y) < 0.6


def test_conformal_correction_restores_nominal_coverage():
    rng = np.random.default_rng(1)
    # split into calibration and test, as a held-out design would
    lo_c, hi_c, y_c = _miscalibrated(rng, 4000)
    lo_t, hi_t, y_t = _miscalibrated(rng, 4000)

    corr = fit_conformal(lo_c, hi_c, y_c, alpha=0.05)
    lo_adj, hi_adj = corr.apply(lo_t, hi_t)
    cov = coverage(lo_adj, hi_adj, y_t)

    # split-conformal has finite-sample variance; on 4000 held-out points
    # coverage should land close to the 95% target
    assert 0.93 <= cov <= 0.99


def test_well_calibrated_interval_gets_small_correction():
    rng = np.random.default_rng(2)
    n = 5000
    y = rng.normal(0.0, 1.0, n)
    # a genuinely well-calibrated 95% interval around a near-unbiased estimate
    est = rng.normal(0.0, 0.02, n)
    lo, hi = est - 1.96, est + 1.96
    corr = fit_conformal(lo, hi, y, alpha=0.05)
    assert corr.delta < 0.15


def test_asymmetric_bias_is_corrected_by_widening_both_sides():
    """A systematically biased estimator (interval shifted, not just narrow)
    still reaches nominal coverage after symmetric widening -- the guarantee
    is coverage, not that the correction is the 'smallest possible'."""
    rng = np.random.default_rng(3)
    lo_c, hi_c, y_c = _miscalibrated(rng, 4000, bias=0.4)
    lo_t, hi_t, y_t = _miscalibrated(rng, 4000, bias=0.4)
    corr = fit_conformal(lo_c, hi_c, y_c, alpha=0.05)
    lo_adj, hi_adj = corr.apply(lo_t, hi_t)
    assert coverage(lo_adj, hi_adj, y_t) >= 0.90


def test_fit_conformal_rejects_too_few_points():
    rng = np.random.default_rng(4)
    lo, hi, y = _miscalibrated(rng, 5)
    with pytest.raises(ValueError):
        fit_conformal(lo, hi, y)


def test_fit_conformal_drops_non_finite_points():
    rng = np.random.default_rng(5)
    lo, hi, y = _miscalibrated(rng, 200)
    lo[3], hi[7], y[11] = np.nan, np.nan, np.nan
    corr = fit_conformal(lo, hi, y)
    assert corr.n_calibration == 197


def test_apply_widens_symmetrically():
    corr = ConformalCorrection(delta=0.5, alpha=0.05, n_calibration=100)
    lo, hi = corr.apply(np.array([1.0, 2.0]), np.array([3.0, 4.0]))
    np.testing.assert_allclose(lo, [0.5, 1.5])
    np.testing.assert_allclose(hi, [3.5, 4.5])


def test_round_trip_dict():
    corr = ConformalCorrection(delta=0.42, alpha=0.05, n_calibration=137)
    back = ConformalCorrection.from_dict(corr.to_dict())
    assert back == corr


def test_shape_mismatch_raises():
    with pytest.raises(ValueError):
        fit_conformal(np.zeros(10), np.zeros(10), np.zeros(11))
