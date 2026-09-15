"""
src.twl against physical sanity checks and against the thesis's own
published comparison chart (Brake 2002, Figure 18, p.114: "Hot, Dry
conditions, DB=MRT=WB+10, 0.5 m/s"), not just internal self-consistency.
"""

import numpy as np
import pytest

from src.psychro import saturation_vapor_pressure_hpa
from src.twl import (
    DEFAULT_CORE_TEMP_LIMIT_C,
    DRY_BULB_WITHDRAWAL_C,
    TWL_ACCLIMATISATION_WM2,
    TWL_BUFFER_WM2,
    TWL_WITHDRAWAL_WM2,
    WET_BULB_WITHDRAWAL_C,
    classify,
    twl_wm2,
)


def _rh_for_wet_bulb_approx(dry_bulb_c: float, wet_bulb_c: float) -> float:
    """RH such that saturation vapour pressure at wet_bulb_c approximates
    the actual vapour pressure at dry_bulb_c -- a crude but adequate
    stand-in for a psychrometric wet-bulb depression in these tests,
    since we only need a representative humid point, not exact PROSPIE-
    grade accuracy."""
    e = saturation_vapor_pressure_hpa(np.array([wet_bulb_c]))[0]
    es = saturation_vapor_pressure_hpa(np.array([dry_bulb_c]))[0]
    return float(np.clip(100.0 * e / es, 1.0, 100.0))


def test_valid_range_on_typical_gulf_conditions():
    # a real Doha summer afternoon and a mild evening, both physically
    # valid (60-380 W/m2 is the thesis's own stated valid range, p.101)
    hot = twl_wm2(np.array([40.0]), np.array([55.0]), np.array([1000.0]),
                  np.array([2.0]), np.array([48.0]))[0]
    mild = twl_wm2(np.array([26.0]), np.array([40.0]), np.array([1013.0]),
                   np.array([1.5]), np.array([26.0]))[0]
    assert 60.0 <= hot <= 380.0
    assert 60.0 <= mild <= 380.0
    assert mild > hot   # milder conditions sustain a higher metabolic rate


def test_monotonic_decrease_with_temperature():
    temps = np.array([25.0, 30.0, 35.0, 40.0, 45.0])
    twl = twl_wm2(temps, np.full(5, 40.0), np.full(5, 1013.0),
                  np.full(5, 1.0), temps)
    assert np.all(np.diff(twl) < 0)


def test_monotonic_decrease_with_humidity():
    rh = np.array([20.0, 40.0, 60.0, 80.0])
    twl = twl_wm2(np.full(4, 35.0), rh, np.full(4, 1013.0),
                  np.full(4, 1.0), np.full(4, 35.0))
    assert np.all(np.diff(twl) < 0)


def test_more_wind_increases_sustainable_rate():
    wind = np.array([0.2, 1.0, 3.0, 6.0])
    twl = twl_wm2(np.full(4, 36.0), np.full(4, 50.0), np.full(4, 1013.0),
                  wind, np.full(4, 36.0))
    assert np.all(np.diff(twl) > 0)


def test_wind_below_minimum_is_clamped():
    a = twl_wm2(np.array([35.0]), np.array([40.0]), np.array([1013.0]),
               np.array([0.0]), np.array([35.0]))
    b = twl_wm2(np.array([35.0]), np.array([40.0]), np.array([1013.0]),
               np.array([0.2]), np.array([35.0]))
    np.testing.assert_allclose(a, b)


def test_matches_thesis_figure_18_hot_dry_curve_shape_and_order_of_magnitude():
    """Figure 18 (p.114), "Hot, Dry conditions, DB=MRT=WB+10, 0.5 m/s":
    the published TWL curve runs from roughly 190-210 W/m2 at WB=24 C
    down to roughly 55-90 W/m2 at WB=33 C. This is read off a chart, not
    a table, so the tolerance is generous -- the point is confirming the
    right curve shape and order of magnitude against the primary
    source's own figure, not exact digit matching."""
    wet_bulbs = [24.0, 27.0, 30.0, 33.0]
    expected_ranges = [(160.0, 230.0), (120.0, 190.0), (80.0, 150.0), (40.0, 110.0)]
    got = []
    for wb in wet_bulbs:
        db = wb + 10.0
        rh = _rh_for_wet_bulb_approx(db, wb)
        v = twl_wm2(np.array([db]), np.array([rh]), np.array([1013.0]),
                   np.array([0.5]), np.array([db]))[0]
        got.append(v)
    for v, (lo, hi) in zip(got, expected_ranges):
        assert lo <= v <= hi, f"got {v}, expected in [{lo}, {hi}]"
    assert np.all(np.diff(got) < 0)   # hotter wet-bulb -> lower TWL, matches the figure


def test_classify_action_levels():
    twl = np.array([90.0, 130.0, 180.0, 260.0])
    db = np.full(4, 35.0)
    wb = np.full(4, 25.0)
    labels = classify(twl, db, wb)
    assert list(labels) == ["withdrawal", "buffer", "acclimatisation_only", "unrestricted"]
    assert TWL_WITHDRAWAL_WM2 == 115.0
    assert TWL_BUFFER_WM2 == 140.0
    assert TWL_ACCLIMATISATION_WM2 == 220.0


def test_classify_dry_bulb_backstop_overrides_high_twl():
    # a computed TWL well into "unrestricted" territory, but dry bulb
    # exceeds the 44 C backstop -> must still read withdrawal
    labels = classify(np.array([300.0]), np.array([DRY_BULB_WITHDRAWAL_C + 0.5]),
                      np.array([20.0]))
    assert labels[0] == "withdrawal"


def test_classify_wet_bulb_backstop_overrides_high_twl():
    labels = classify(np.array([300.0]), np.array([35.0]),
                      np.array([WET_BULB_WITHDRAWAL_C + 0.5]))
    assert labels[0] == "withdrawal"


def test_returns_nan_outside_valid_regime():
    # air already at or above the core-temperature limit with saturated
    # humidity -- no steady state exists within the bisection bracket
    v = twl_wm2(np.array([DEFAULT_CORE_TEMP_LIMIT_C + 5.0]), np.array([100.0]),
               np.array([1013.0]), np.array([0.2]),
               np.array([DEFAULT_CORE_TEMP_LIMIT_C + 5.0]))
    assert np.isnan(v[0])


def test_broadcasts_and_shapes():
    n = 5
    out = twl_wm2(np.full(n, 35.0), np.full(n, 45.0), np.full(n, 1013.0),
                  np.full(n, 1.0), np.full(n, 40.0))
    assert out.shape == (n,)
    assert np.isfinite(out).all()


def test_sweat_rate_cap_can_bind_before_core_temperature_cap():
    """The reference implementation scans core temperature up from a
    resting value and stops at whichever limit -- core temperature or
    sweat rate -- is reached first. In hot, humid conditions (low
    evaporative capacity), sweat rate should be able to bind first,
    giving a lower TWL than a naive model that always assumes core
    temperature is the binding constraint. A very tight sweat-rate
    limit makes this deterministic to test."""
    env = dict(t_air_c=np.array([38.0]), rh_pct=np.array([70.0]),
              pressure_hpa=np.array([1000.0]), wind_speed_ms=np.array([1.0]),
              mean_radiant_temp_c=np.array([45.0]))
    normal = twl_wm2(**env, sweat_rate_max_kg_hr=1.2)[0]
    tight = twl_wm2(**env, sweat_rate_max_kg_hr=0.3)[0]
    assert tight < normal


def test_lower_clothing_insulation_increases_sustainable_rate():
    """Less insulation should ease heat loss (cotton work shirt vs a
    heavier ensemble), raising the sustainable metabolic rate, at fixed
    environment."""
    light = twl_wm2(np.array([35.0]), np.array([45.0]), np.array([1013.0]),
                    np.array([1.0]), np.array([35.0]), clo=0.2)[0]
    heavy = twl_wm2(np.array([35.0]), np.array([45.0]), np.array([1013.0]),
                    np.array([1.0]), np.array([35.0]), clo=0.6)[0]
    assert light > heavy
