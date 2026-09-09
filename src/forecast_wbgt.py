"""
WBGT from a frame of forecast weather fields, through the same Liljegren
pipeline used everywhere else in the repo (src.wbgt + src.solar).

No new physics. This maps forecast column names onto
wbgt_liljegren_c arguments and supplies cos(zenith) from timestamp and
location, exactly as scripts/run_first_result.py does for the analysis
path. It exists so the AI-weather-model study
(scripts/aiwp_humid_heat_study.py) turns each (model, lead) forecast into
a WBGT forecast scored against the patched observational truth by the
same method as the truth itself.

If a model serves global shortwave but not its direct-beam component,
`direct` is estimated with the Erbs et al. (1982) diffuse-fraction
correlation and `used_erbs_direct` is set on the returned object so the
report can note it. On the Open-Meteo previous-runs feed IFS, AIFS and
GFS all serve `direct_radiation`, so this fallback is not expected to
fire; GraphCast serves neither and is handled on the temperature track,
not here.

Reference: Erbs, D.G., Klein, S.A., Duffie, J.A. (1982), "Estimation of
the diffuse radiation fraction for hourly, daily and monthly-average
global radiation", Solar Energy 28, 293-302.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.solar import cos_solar_zenith_angle
from src.wbgt import wbgt_liljegren_c

SOLAR_CONSTANT_WM2 = 1361.0

# Fields wbgt_liljegren_c needs, other than the direct beam (which has a
# fallback) and cos(zenith) (which is computed here).
REQUIRED_COLUMNS = (
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "shortwave_radiation",
    "surface_pressure",
)


class WbgtFromForecast(np.ndarray):
    """A plain ndarray of WBGT in deg C, plus a flag recording whether the
    Erbs direct-beam fallback was used."""

    used_erbs_direct: bool

    def __new__(cls, values: np.ndarray, used_erbs_direct: bool):
        obj = np.asarray(values, dtype=float).view(cls)
        obj.used_erbs_direct = used_erbs_direct
        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return
        self.used_erbs_direct = getattr(obj, "used_erbs_direct", False)


def erbs_direct_wm2(shortwave_wm2: np.ndarray, cos_zenith: np.ndarray
                    ) -> np.ndarray:
    """Direct-beam irradiance on the horizontal from global shortwave and
    solar geometry, via the Erbs (1982) diffuse-fraction correlation."""
    sw = np.clip(np.asarray(shortwave_wm2, dtype=float), 0.0, None)
    cz = np.clip(np.asarray(cos_zenith, dtype=float), 0.0, 1.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        i0 = SOLAR_CONSTANT_WM2 * cz                    # extraterrestrial, horizontal
        kt = np.where(i0 > 0.0, sw / i0, 0.0)
    kt = np.clip(np.nan_to_num(kt, nan=0.0), 0.0, 1.0)

    diffuse_frac = np.where(
        kt <= 0.22,
        1.0 - 0.09 * kt,
        np.where(
            kt <= 0.80,
            0.9511 - 0.1604 * kt + 4.388 * kt**2
            - 16.638 * kt**3 + 12.336 * kt**4,
            0.165,
        ),
    )
    direct = np.clip(sw * (1.0 - diffuse_frac), 0.0, None)
    return np.where(cz > 0.0, direct, 0.0)


def wbgt_from_forecast_frame(
    df: pd.DataFrame,
    lat: float,
    lon: float,
    *,
    time_col: str = "time",
) -> WbgtFromForecast:
    """Outdoor WBGT [deg C] for every row of a forecast weather frame.

    `df` must carry REQUIRED_COLUMNS plus `time_col` (UTC, tz-aware or
    naive-UTC). `direct_radiation` is used if present, otherwise estimated.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"forecast frame missing columns: {missing}")

    times = pd.DatetimeIndex(pd.to_datetime(df[time_col], utc=True))
    cz = cos_solar_zenith_angle(times, lat, lon)

    sw = np.nan_to_num(df["shortwave_radiation"].to_numpy(dtype=float), nan=0.0)
    if "direct_radiation" in df.columns:
        direct = np.nan_to_num(
            df["direct_radiation"].to_numpy(dtype=float), nan=0.0)
        used_erbs = False
    else:
        direct = erbs_direct_wm2(sw, cz)
        used_erbs = True

    wbgt = wbgt_liljegren_c(
        temp_c=df["temperature_2m"].to_numpy(dtype=float),
        rh_pct=df["relative_humidity_2m"].to_numpy(dtype=float),
        pressure_hpa=df["surface_pressure"].to_numpy(dtype=float),
        wind_speed_10m_ms=df["wind_speed_10m"].to_numpy(dtype=float),
        shortwave_wm2=sw,
        direct_wm2=direct,
        cos_zenith=cz,
    )
    return WbgtFromForecast(wbgt, used_erbs)
