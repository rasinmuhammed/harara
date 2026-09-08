"""
Behavioural tests for the two-node thermoregulation model. These encode
the physiological sanity checks the model was tuned against.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.thermoreg import Subject, ThermoState, simulate


def _run(ta, rh, wind, met, minutes, st0=None):
    t = np.arange(0, minutes + 1, 2.0)
    a = lambda x: np.full_like(t, float(x))
    return simulate(Subject(), t, a(ta), a(rh), a(wind), a(met), st0=st0)


def test_thermoneutral_rest_is_stable():
    o = _run(25, 50, 0.1, 58, 180, ThermoState(36.9, 34.0))
    assert 36.6 < o["t_cr"][-1] < 37.2
    assert 31.5 < o["t_sk"][-1] < 34.5
    assert 60 < o["hr"][-1] < 85


def test_moderate_work_compensable_plateau():
    o = _run(33, 45, 1.0, 250, 120, ThermoState(36.9, 34.2))
    assert o["t_cr"][-1] < 38.3            # does not run away
    assert o["t_cr"][-1] > o["t_cr"][0]    # but does rise


def test_heavy_uncompensable_climbs():
    o = _run(38, 40, 1.0, 380, 60, ThermoState(36.9, 34.5))
    assert o["t_cr"][-1] - o["t_cr"][0] > 1.0


def test_cycling_keeps_core_safe():
    t = np.arange(0, 151, 2.0)
    met = np.where((t % 40) < 25, 300.0, 70.0)
    a = lambda x: np.full_like(t, float(x))
    o = simulate(Subject(), t, a(35), a(45), a(1.0), met, st0=ThermoState(36.9, 34.5))
    assert o["t_cr"].max() < 38.3


def test_cold_lowers_skin_and_core():
    o = _run(5, 50, 2.0, 80, 60, ThermoState(36.9, 32.0))
    assert o["t_sk"][-1] < 26.0
    assert o["t_cr"][-1] < 36.9


def test_hr_monotone_in_core_at_fixed_work():
    hrs, crs = [], []
    for ta in (30, 34, 38):
        o = _run(ta, 40, 1.0, 250, 90, ThermoState(36.9, 34.0))
        crs.append(o["t_cr"][-1]); hrs.append(o["hr"][-1])
    order = np.argsort(crs)
    assert list(np.argsort(np.array(hrs)[order])) == [0, 1, 2]
