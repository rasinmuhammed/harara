"""
Cosine of the solar zenith angle from timestamp + location.

thermofeel's Liljegren WBGT needs this. A low sun and an overhead sun of
the same intensity load a black globe (and a standing worker) very
differently, so the solver has to know where the sun is. ERA5 ships the
cosine of the solar zenith angle as a variable; the Open-Meteo archive
does not, so we compute it here.

Algorithm: NOAA solar-position equations - a short Fourier series in the
"fractional year" for the equation of time and the solar declination, then
the standard spherical-astronomy expression for the zenith angle. Accurate
to well under a degree, which is far more than WBGT needs.

Reference: NOAA Global Monitoring Laboratory solar calculator,
https://gml.noaa.gov/grad/solcalc/solareqns.PDF
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def cos_solar_zenith_angle(
    times_utc: pd.DatetimeIndex, lat_deg: float, lon_deg: float
) -> np.ndarray:
    """
    Parameters
    ----------
    times_utc : timestamps; tz-aware are converted to UTC, naive are
                assumed to already be UTC
    lat_deg   : latitude  [degrees, north positive]
    lon_deg   : longitude [degrees, east positive]

    Returns
    -------
    np.ndarray of cos(zenith), clipped to [0, 1]. 0 means the sun is at or
    below the horizon (night / twilight).
    """
    t = pd.DatetimeIndex(times_utc)
    if t.tz is not None:
        t = t.tz_convert("UTC").tz_localize(None)

    doy = t.dayofyear.to_numpy().astype(float)
    hour = (t.hour + t.minute / 60.0 + t.second / 3600.0).to_numpy()

    # Fractional year, radians.
    gamma = 2.0 * np.pi / 365.0 * (doy - 1.0 + (hour - 12.0) / 24.0)

    # Equation of time [minutes]: the difference between clock time and true
    # solar time caused by Earth's elliptical orbit and axial tilt.
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * np.cos(gamma)
        - 0.032077 * np.sin(gamma)
        - 0.014615 * np.cos(2.0 * gamma)
        - 0.040849 * np.sin(2.0 * gamma)
    )

    # Solar declination [radians]: latitude at which the sun is overhead.
    decl = (
        0.006918
        - 0.399912 * np.cos(gamma)
        + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2.0 * gamma)
        + 0.000907 * np.sin(2.0 * gamma)
        - 0.002697 * np.cos(3.0 * gamma)
        + 0.001480 * np.sin(3.0 * gamma)
    )

    # True solar time [minutes] -> hour angle [radians]. Data is UTC, so the
    # timezone term is zero; only longitude shifts local solar noon.
    time_offset = eqtime + 4.0 * lon_deg
    tst = hour * 60.0 + time_offset
    hour_angle = np.deg2rad(tst / 4.0 - 180.0)

    lat = np.deg2rad(lat_deg)
    cza = (
        np.sin(lat) * np.sin(decl)
        + np.cos(lat) * np.cos(decl) * np.cos(hour_angle)
    )
    return np.clip(cza, 0.0, 1.0)
