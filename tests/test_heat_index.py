"""
src.heat_index against an independently-written reimplementation of the
same NOAA/Rothfusz reference (https://www.wpc.ncep.noaa.gov/html/
heatindex_equationbody.html), not against the module's own arithmetic --
so a copy-paste bug in either the regression or an adjustment term would
be caught, not just re-confirmed.
"""

import numpy as np
import pytest

from src.heat_index import heat_index_c


def _reference_hi_f(t_f: float, rh: float) -> float:
    """Independent hand-transcription of the NOAA Rothfusz procedure."""
    simple = 0.5 * (t_f + 61.0 + (t_f - 68.0) * 1.2 + rh * 0.094)
    avg = 0.5 * (simple + t_f)
    if avg < 80.0:
        return simple

    hi = (-42.379 + 2.04901523 * t_f + 10.14333127 * rh
          - 0.22475541 * t_f * rh - 0.00683783 * t_f ** 2
          - 0.05481717 * rh ** 2 + 0.00122874 * t_f ** 2 * rh
          + 0.00085282 * t_f * rh ** 2 - 0.00000199 * t_f ** 2 * rh ** 2)

    if rh < 13.0 and 80.0 <= t_f <= 112.0:
        hi -= ((13.0 - rh) / 4.0) * np.sqrt(max(0.0, 17.0 - abs(t_f - 95.0)) / 17.0)
    if rh > 85.0 and 80.0 <= t_f <= 87.0:
        hi += ((rh - 85.0) / 10.0) * ((87.0 - t_f) / 5.0)
    return hi


CASES_F = [
    (100.0, 55.0), (95.0, 70.0), (90.0, 40.0), (105.0, 30.0),
    (85.0, 90.0), (82.0, 88.0), (88.0, 5.0), (100.0, 8.0),
    (70.0, 50.0), (60.0, 80.0),
]


@pytest.mark.parametrize("t_f,rh", CASES_F)
def test_matches_independent_reference(t_f, rh):
    t_c = (t_f - 32.0) * 5.0 / 9.0
    expect_f = _reference_hi_f(t_f, rh)
    expect_c = (expect_f - 32.0) * 5.0 / 9.0
    got = heat_index_c(np.array([t_c]), np.array([rh]))[0]
    assert got == pytest.approx(expect_c, abs=1e-6)


def test_low_rh_high_t_adjustment_lowers_index():
    """A hot, very dry desert case should trigger the NOAA low-RH
    correction, which subtracts from the raw regression."""
    t_c = np.array([38.0])   # 100.4 F
    hi_dry = heat_index_c(t_c, np.array([5.0]))
    hi_no_adj = _reference_hi_f(100.4, 5.0)
    # confirm the adjustment branch actually fires for this point (rh<13,
    # 80<=t<=112) and that the module applies it, not just the raw regression
    raw = (-42.379 + 2.04901523 * 100.4 + 10.14333127 * 5.0
           - 0.22475541 * 100.4 * 5.0 - 0.00683783 * 100.4 ** 2
           - 0.05481717 * 5.0 ** 2 + 0.00122874 * 100.4 ** 2 * 5.0
           + 0.00085282 * 100.4 * 5.0 ** 2 - 0.00000199 * 100.4 ** 2 * 5.0 ** 2)
    assert hi_no_adj < raw
    assert hi_dry[0] == pytest.approx((hi_no_adj - 32.0) * 5.0 / 9.0, abs=1e-6)


def test_high_rh_moderate_t_adjustment_raises_index():
    t_c = (82.0 - 32.0) * 5.0 / 9.0
    hi = heat_index_c(np.array([t_c]), np.array([90.0]))[0]
    raw = (-42.379 + 2.04901523 * 82.0 + 10.14333127 * 90.0
           - 0.22475541 * 82.0 * 90.0 - 0.00683783 * 82.0 ** 2
           - 0.05481717 * 90.0 ** 2 + 0.00122874 * 82.0 ** 2 * 90.0
           + 0.00085282 * 82.0 * 90.0 ** 2 - 0.00000199 * 82.0 ** 2 * 90.0 ** 2)
    raw_c = (raw - 32.0) * 5.0 / 9.0
    assert hi > raw_c


def test_below_80f_uses_simple_formula_not_regression():
    # a mild day: T=25C (77F), RH=50% -- well under the regime switch
    t_c, rh = np.array([25.0]), np.array([50.0])
    got = heat_index_c(t_c, rh)[0]
    expect_f = _reference_hi_f(77.0, 50.0)
    assert got == pytest.approx((expect_f - 32.0) * 5.0 / 9.0, abs=1e-6)
    # sanity: mild-day heat index should be close to actual temperature,
    # not wildly different (the regression, wrongly applied here, would
    # diverge badly at low T)
    assert abs(got - 25.0) < 5.0


def test_increases_with_humidity_at_fixed_hot_temperature():
    t_c = np.full(5, 38.0)
    rh = np.array([20.0, 40.0, 60.0, 80.0, 95.0])
    hi = heat_index_c(t_c, rh)
    assert np.all(np.diff(hi) > 0)


def test_plausible_doha_summer_extreme():
    # a real, severe Doha August afternoon: ~42 C, ~55% RH -- heat index
    # should read well above air temperature and in a physically
    # plausible extreme-heat range
    hi = heat_index_c(np.array([42.0]), np.array([55.0]))[0]
    assert 55.0 < hi < 90.0


def test_broadcasts_arrays():
    t_c = np.array([20.0, 30.0, 40.0])
    rh = np.array([30.0, 60.0, 70.0])
    out = heat_index_c(t_c, rh)
    assert out.shape == (3,)
    assert np.isfinite(out).all()
