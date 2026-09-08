"""
Outdoor (sun-exposed) WBGT, computed with the physically-based Liljegren
et al. (2008) method via ECMWF's `thermofeel`.

No empirical single-location regressions. The globe temperature and the
natural wet-bulb temperature are each solved from a steady-state energy
balance (short- and long-wave radiation in/out, convection, evaporation)
and combined as

    WBGT = 0.7 * Tnwb + 0.2 * Tg + 0.1 * Ta

This is the method used operationally by KNMI and ECMWF, and validated
against station observations worldwide by Kong & Huber (2022).

References:
- Liljegren, J.C. et al. (2008), "Modeling the Wet Bulb Globe Temperature
  Using Standard Meteorological Measurements", J. Occup. Environ. Hyg.,
  https://doi.org/10.1080/15459620802310770
- Kong, Q. & Huber, M. (2022), Earth's Future,
  https://doi.org/10.1029/2021EF002334
"""

from __future__ import annotations

import numpy as np
import thermofeel as tf

# Qatar Ministerial Decision 17/2021: outdoor work must stop when WBGT
# reaches 32.1 C (mandatory midday stoppage ~10:00-15:30, 1 Jun - 15 Sep).
QATAR_WBGT_STOP_WORK_THRESHOLD_C = 32.1


def wbgt_liljegren_c(
    temp_c: np.ndarray,
    rh_pct: np.ndarray,
    pressure_hpa: np.ndarray,
    wind_speed_10m_ms: np.ndarray,
    shortwave_wm2: np.ndarray,
    direct_wm2: np.ndarray,
    cos_zenith: np.ndarray,
) -> np.ndarray:
    """
    Outdoor WBGT in degrees Celsius.

    Parameters
    ----------
    temp_c            : 2 m air temperature [C]
    rh_pct            : relative humidity [%]
    pressure_hpa      : surface air pressure [hPa]
    wind_speed_10m_ms : wind speed at 10 m [m/s]
    shortwave_wm2     : downward shortwave irradiance at the surface,
                        global horizontal [W/m2]
    direct_wm2        : the direct-beam part of `shortwave_wm2`, on the
                        horizontal plane [W/m2]
    cos_zenith        : cosine of the solar zenith angle in [0, 1], 0 at
                        night (see src.solar.cos_solar_zenith_angle)

    All arrays broadcast together. Returns NaN where the energy-balance
    iteration fails to converge (rare, usually near-calm wind).
    """
    temp_c = np.asarray(temp_c, dtype=float)
    sw = np.clip(np.asarray(shortwave_wm2, dtype=float), 0.0, None)
    direct = np.clip(np.asarray(direct_wm2, dtype=float), 0.0, None)

    # Direct-beam fraction of the shortwave flux. Undefined when the sun is
    # down / there is no radiation -> 0. thermofeel additionally clamps this
    # to [0, 0.9] and zeroes it below the horizon.
    with np.errstate(divide="ignore", invalid="ignore"):
        fdir = np.where(sw > 0.0, direct / sw, 0.0)
    fdir = np.clip(np.nan_to_num(fdir, nan=0.0), 0.0, 1.0)

    cza = np.clip(np.asarray(cos_zenith, dtype=float), 0.0, 1.0)

    wbgt_k = tf.calculate_wbgt_liljegren(
        t2_k=temp_c + 273.15,
        rh=np.asarray(rh_pct, dtype=float),
        pressure=np.asarray(pressure_hpa, dtype=float),
        va=np.asarray(wind_speed_10m_ms, dtype=float),
        ssrd=sw,
        fdir=fdir,
        cossza=cza,
    )
    return np.asarray(wbgt_k, dtype=float) - 273.15


def exceeds_threshold(
    wbgt_c: np.ndarray,
    threshold_c: float = QATAR_WBGT_STOP_WORK_THRESHOLD_C,
) -> np.ndarray:
    return np.asarray(wbgt_c, dtype=float) > threshold_c
