"""
NWS Heat Index (Rothfusz 1990 regression of Steadman 1979's Apparent
Temperature model), the "feels like" temperature-plus-humidity index used
operationally by Dubai Municipality alongside the GCC-wide midday ban -- a
different physical quantity from Qatar's WBGT (Liljegren, src.wbgt) and from
Abu Dhabi's Thermal Work Limit: heat index has no wind or radiation term, so
it is not interchangeable with either. It is implemented here to let Harara
compare what a Doha day would read as under Dubai's own index, not because
heat index is a better metric than WBGT for outdoor workers -- the opposite
is generally true, since it omits solar load and wind, both of which matter
outdoors. See docs/technical_report.md for the multi-jurisdiction rationale.

Reference:
- Rothfusz, L.P. (1990), "The Heat Index Equation", NWS Southern Region
  Technical Attachment SR 90-23.
  https://www.wpc.ncep.noaa.gov/html/heatindex_equationbody.html
- Steadman, R.G. (1979), "The Assessment of Sultriness", J. Appl. Meteorol.
"""

from __future__ import annotations

import numpy as np

# Dubai Municipality's own heat-index thresholds are not published as a
# single public numeric standard the way Qatar's WBGT one is; Dubai's
# enforced rule is the GCC-wide calendar midday ban (15 Jun - 15 Sep,
# hours vary by emirate). This module computes the index only -- it does
# not assert a stop-work threshold, unlike src.wbgt's QATAR_..._THRESHOLD_C.


def _c_to_f(temp_c: np.ndarray) -> np.ndarray:
    return temp_c * 9.0 / 5.0 + 32.0


def _f_to_c(temp_f: np.ndarray) -> np.ndarray:
    return (temp_f - 32.0) * 5.0 / 9.0


def heat_index_c(temp_c: np.ndarray, rh_pct: np.ndarray) -> np.ndarray:
    """
    NWS heat index in degrees Celsius.

    Parameters
    ----------
    temp_c : 2 m air temperature [C]
    rh_pct : relative humidity [%]

    Below about 27 C (80 F), the NWS's own simple formula is used instead
    of the regression, which is not valid there. Two small correction
    terms are applied on top of the Rothfusz regression, exactly as NOAA
    specifies: a downward adjustment for low humidity in hot, dry
    conditions, and an upward adjustment for high humidity in the 80-87 F
    band. All arrays broadcast together.
    """
    t = _c_to_f(np.asarray(temp_c, dtype=float))
    rh = np.asarray(rh_pct, dtype=float)

    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    avg = 0.5 * (simple + t)

    hi_full = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * rh
        - 0.22475541 * t * rh
        - 0.00683783 * t * t
        - 0.05481717 * rh * rh
        + 0.00122874 * t * t * rh
        + 0.00085282 * t * rh * rh
        - 0.00000199 * t * t * rh * rh
    )

    low_adj = np.where(
        (rh < 13.0) & (t >= 80.0) & (t <= 112.0),
        ((13.0 - rh) / 4.0) * np.sqrt(np.clip((17.0 - np.abs(t - 95.0)), 0.0, None) / 17.0),
        0.0,
    )
    high_adj = np.where(
        (rh > 85.0) & (t >= 80.0) & (t <= 87.0),
        ((rh - 85.0) / 10.0) * ((87.0 - t) / 5.0),
        0.0,
    )
    hi_full = hi_full - low_adj + high_adj

    # the simple formula's own average with T decides whether we are in
    # the "below 80 F" regime NOAA specifies, matching the reference
    # implementation exactly (not just thresholding T itself)
    hi_f = np.where(avg < 80.0, simple, hi_full)
    return _f_to_c(hi_f)
