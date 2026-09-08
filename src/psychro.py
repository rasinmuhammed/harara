"""
Psychrometrics: wet-bulb temperature and related conversions.

The wet-bulb temperature is the humidity-carrying term of WBGT
(WBGT_outdoor = 0.7*Tnwb + 0.2*Tg + 0.1*Ta), so forecast error in
wet-bulb is the right quantity for studying humid-heat forecast failures
without needing solar radiation (which METAR does not report).

`wet_bulb_stull` is the Stull (2011) empirical fit, valid roughly
-20..50 C and 5..99 % RH at sea level, with a stated RMS error of
~0.3 C and a worst-case bias of ~+/-1 C at the extremes. Adequate here:
we compare two wet-bulb estimates computed the *same* way, so the fit
error largely cancels in the difference.

Reference: Stull, R. (2011), "Wet-Bulb Temperature from Relative Humidity
and Air Temperature", J. Appl. Meteor. Climatol., 50, 2267-2269.
"""

from __future__ import annotations

import numpy as np


def saturation_vapor_pressure_hpa(temp_c: np.ndarray) -> np.ndarray:
    """Tetens formula over water, hPa."""
    t = np.asarray(temp_c, dtype=float)
    return 6.1078 * 10.0 ** ((7.5 * t) / (237.3 + t))


def rh_from_dewpoint(temp_c: np.ndarray, dewpoint_c: np.ndarray) -> np.ndarray:
    """Relative humidity [%] from temperature and dewpoint."""
    e = saturation_vapor_pressure_hpa(dewpoint_c)
    es = saturation_vapor_pressure_hpa(temp_c)
    return np.clip(100.0 * e / es, 0.0, 100.0)


def wet_bulb_stull(temp_c: np.ndarray, rh_pct: np.ndarray) -> np.ndarray:
    """
    Psychrometric wet-bulb temperature [C] from dry-bulb temperature and
    relative humidity, Stull (2011).
    """
    t = np.asarray(temp_c, dtype=float)
    rh = np.asarray(rh_pct, dtype=float)
    return (
        t * np.arctan(0.151977 * np.sqrt(rh + 8.313659))
        + np.arctan(t + rh)
        - np.arctan(rh - 1.676331)
        + 0.00391838 * rh ** 1.5 * np.arctan(0.023101 * rh)
        - 4.686035
    )


def wet_bulb_from_dewpoint(temp_c: np.ndarray, dewpoint_c: np.ndarray) -> np.ndarray:
    """Convenience: wet-bulb from temperature + dewpoint (via RH)."""
    return wet_bulb_stull(temp_c, rh_from_dewpoint(temp_c, dewpoint_c))
