"""
Unit tests for the physical and mathematical core. These guard the
scientific claims: if a refactor breaks the WBGT physics, the
thermoregulation behaviour, the leakage-safe splits, or the scheduler
feasibility, a test fails.

Run:  pytest -q
"""

import numpy as np
import pytest

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.psychro import wet_bulb_stull, rh_from_dewpoint
from src.solar import cos_solar_zenith_angle
from src.wbgt import wbgt_liljegren_c, QATAR_WBGT_STOP_WORK_THRESHOLD_C
from src.heat_stress import allowable_work_fraction, stop_work
from src.scheduler import schedule_cvar, realized_strain, hourly_load
from eval.harness import walk_forward_splits
import pandas as pd


# --------------------------------------------------------------- WBGT
def test_wbgt_ordering_and_range():
    """Hotter/more humid/sunnier/stiller -> higher WBGT; values plausible."""
    base = dict(rh_pct=40.0, pressure_hpa=1000.0, wind_speed_10m_ms=3.0,
                shortwave_wm2=800.0, direct_wm2=600.0, cos_zenith=0.9)
    w_cool = wbgt_liljegren_c(temp_c=30.0, **base)
    w_hot = wbgt_liljegren_c(temp_c=42.0, **base)
    assert 15.0 < w_cool < w_hot < 45.0
    w_humid = wbgt_liljegren_c(temp_c=38.0, rh_pct=70.0, pressure_hpa=1000.0,
                               wind_speed_10m_ms=3.0, shortwave_wm2=800.0,
                               direct_wm2=600.0, cos_zenith=0.9)
    w_dry = wbgt_liljegren_c(temp_c=38.0, rh_pct=20.0, pressure_hpa=1000.0,
                             wind_speed_10m_ms=3.0, shortwave_wm2=800.0,
                             direct_wm2=600.0, cos_zenith=0.9)
    assert w_humid > w_dry
    w_calm = wbgt_liljegren_c(temp_c=40.0, rh_pct=35.0, pressure_hpa=1000.0,
                              wind_speed_10m_ms=0.7, shortwave_wm2=850.0,
                              direct_wm2=650.0, cos_zenith=0.95)
    w_windy = wbgt_liljegren_c(temp_c=40.0, rh_pct=35.0, pressure_hpa=1000.0,
                               wind_speed_10m_ms=8.0, shortwave_wm2=850.0,
                               direct_wm2=650.0, cos_zenith=0.95)
    assert w_calm > w_windy


def test_wbgt_night_below_air_temp():
    """No sun -> globe ~ air; WBGT well below air temperature."""
    w = wbgt_liljegren_c(temp_c=32.0, rh_pct=55.0, pressure_hpa=1002.0,
                         wind_speed_10m_ms=3.0, shortwave_wm2=0.0,
                         direct_wm2=0.0, cos_zenith=0.0)
    assert 24.0 < w < 30.0


# --------------------------------------------------------------- solar
def test_cos_zenith_bounds_and_noon_peak():
    times = pd.date_range("2024-07-01", "2024-07-02", freq="h", tz="UTC")
    cz = cos_solar_zenith_angle(times, 25.27, 51.61)
    assert cz.min() == 0.0 and cz.max() <= 1.0
    local_noon_utc = 9  # Qatar solar noon ~09:00 UTC
    assert np.argmax(cz[:24]) in (local_noon_utc - 1, local_noon_utc,
                                  local_noon_utc + 1)


# --------------------------------------------------------------- psychro
@pytest.mark.parametrize("t,rh,lo,hi", [
    (40.0, 20.0, 20.0, 26.0),
    (35.0, 60.0, 27.0, 31.0),
    (25.0, 50.0, 16.0, 20.0),
])
def test_wet_bulb_reasonable(t, rh, lo, hi):
    assert lo < float(wet_bulb_stull(np.array(t), np.array(rh))) < hi


def test_wet_bulb_le_dry_bulb():
    t = np.array([20.0, 30.0, 42.0])
    rh = np.array([30.0, 55.0, 15.0])
    assert np.all(wet_bulb_stull(t, rh) <= t + 1e-6)


def test_rh_from_dewpoint_saturation():
    assert float(rh_from_dewpoint(np.array(30.0), np.array(30.0))) == pytest.approx(100.0, abs=0.5)


# --------------------------------------------------------------- heat stress
def test_work_fraction_monotone_in_wbgt():
    w = np.array([24, 27, 29, 31, 33, 35], dtype=float)
    fr = allowable_work_fraction(w, "moderate", acclimatized=True)
    assert np.all(np.diff(fr) <= 0)            # never increases with WBGT
    assert fr[0] == 1.0 and fr[-1] == 0.0


def test_unacclimatized_more_restrictive():
    w = np.full(5, 29.0)
    fa = allowable_work_fraction(w, "heavy", True)
    fu = allowable_work_fraction(w, "heavy", False)
    assert np.all(fu <= fa)


def test_stop_work_consistency():
    w = np.array([26.0, 34.0])
    fr = allowable_work_fraction(w, "moderate", True)
    assert np.array_equal(stop_work(w, "moderate", True), fr == 0.0)


# --------------------------------------------------------------- harness
def test_walk_forward_no_leakage():
    n = 1000
    for tr, te in walk_forward_splits(n, n_folds=5, min_train_frac=0.4):
        assert tr.max() < te.min()            # every test index is future
        assert len(np.intersect1d(tr, te)) == 0


# --------------------------------------------------------------- scheduler
def test_scheduler_meets_requirement_and_is_lp_feasible():
    rng = np.random.default_rng(0)
    H = 15
    scen = 28.0 + 4.0 * np.sin(np.linspace(0, np.pi, H))[None, :] \
        + rng.normal(0, 0.5, (40, H))
    allowed = np.ones(H, dtype=bool)
    res = schedule_cvar(scen, allowed, w_req=9.0, beta=0.9)
    assert res.status == "optimal"
    assert res.w.sum() >= 9.0 - 1e-6
    assert np.all((res.w >= -1e-9) & (res.w <= 1 + 1e-9))


def test_scheduler_prefers_cooler_hours():
    """With a clear cool morning / hot afternoon, work should load early."""
    H = 15
    wbgt = np.concatenate([np.full(7, 27.0), np.full(8, 34.0)])
    res = schedule_cvar(wbgt[None, :], np.ones(H, bool), w_req=6.0, beta=0.9)
    assert res.w[:7].sum() > res.w[7:].sum()


def test_realized_strain_zero_when_below_ref():
    w = np.ones(10)
    assert realized_strain(w, np.full(10, 25.0)) == 0.0
    assert hourly_load(np.array([26.0, 30.0]), wbgt_ref=28.0)[0] == 0.0
