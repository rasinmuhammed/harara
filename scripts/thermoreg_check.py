"""
Behaviour checks for the two-node thermoregulation model. Prints core and
skin temperature, heart rate and sweat rate for a set of standard
scenarios. The expected ranges are also asserted in
tests/test_thermoreg.py.

Run:  python scripts/thermoreg_check.py
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.thermoreg import Subject, ThermoState, simulate

SUB = Subject()


def run(label, t_air, rh, wind, met, minutes, st0=None):
    t = np.arange(0, minutes + 1, 2.0)
    a = lambda x: np.full_like(t, float(x))
    o = simulate(SUB, t, a(t_air), a(rh), a(wind),
                 met if np.ndim(met) else a(met), st0=st0)
    print(f"  {label:<28} Tcr {o['t_cr'][0]:.2f}->{o['t_cr'][-1]:.2f}  "
          f"Tsk {o['t_sk'][-1]:.1f}  HR {o['hr'][-1]:.0f}  "
          f"sweat {o['m_sweat_wm2'][-1]:.0f} W/m2")
    return o


if __name__ == "__main__":
    print("two-node thermoregulation model, steady-state behaviour:")
    run("rest 25C/50%", 25, 50, 0.1, 58, 180, ThermoState(36.9, 34.0))
    run("light 28C/45%", 28, 45, 0.5, 120, 120, ThermoState(36.9, 34.0))
    run("walk 30C/40%", 30, 40, 1.0, 165, 90, ThermoState(36.9, 34.0))
    run("moderate 33C/45%", 33, 45, 1.0, 250, 120, ThermoState(36.9, 34.2))
    run("heavy 38C/40%", 38, 40, 1.0, 380, 60, ThermoState(36.9, 34.5))
    run("very heavy 42C/30%", 42, 30, 0.7, 420, 60, ThermoState(36.9, 34.5))
    run("cold 5C", 5, 50, 2.0, 80, 60, ThermoState(36.9, 32.0))

    t = np.arange(0, 151, 2.0)
    met = np.where((t % 40) < 25, 300.0, 70.0)     # 25 min work / 15 min rest
    a = lambda x: np.full_like(t, float(x))
    o = simulate(SUB, t, a(35), a(45), a(1.0), met, st0=ThermoState(36.9, 34.5))
    print(f"\n  work/rest cycling at WBGT ~29: Tcr peak {o['t_cr'].max():.2f}, "
          f"end {o['t_cr'][-1]:.2f}")
