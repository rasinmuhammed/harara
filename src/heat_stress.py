"""
Physiological heat-stress layer: WBGT -> allowable work/rest allocation.

Implements the ACGIH TLV / Action Limit screening criteria for heat stress
(ACGIH 2017, "Heat Stress and Strain"), which are also the basis of
ISO 7243. Given the WBGT, the metabolic workload, and whether the worker
is heat-acclimatized, it returns the maximum fraction of each hour that
can be worked (the rest of the hour is rest in shade).

This is a SCREENING model on public standards - not medical advice and
not a substitute for physiological monitoring. It exists to convert a
forecast WBGT into an operational decision that is role- and
state-specific, rather than a single calendar rule in Qatar's
Decision 17/2021.

Workload categories (approx. metabolic rate, W):
    rest        ~115    sitting
    light       ~180    sitting/standing light hand + arm work
    moderate    ~300    sustained hand/arm + leg work, walking
    heavy       ~415    pick/shovel work, carrying loads
    very_heavy  ~520    intense digging, climbing stairs with load

Work/rest cycles (fraction of the hour worked):
    1.00  continuous
    0.75  45 min work / 15 min rest
    0.50  30 / 30
    0.25  15 / 45
    0.00  no safe work - stop

WBGT screening limits (deg C). Rows = work fraction, cols = workload.
"None" = that workload is not tabulated at that cycle (treat as unsafe).
"""

from __future__ import annotations

import numpy as np

WORK_FRACTIONS = (1.00, 0.75, 0.50, 0.25)
WORKLOADS = ("light", "moderate", "heavy", "very_heavy")

# ACGIH 2017 TLV (acclimatized worker).
_TLV_ACCLIM = {
    1.00: {"light": 29.5, "moderate": 27.5, "heavy": 26.0, "very_heavy": None},
    0.75: {"light": 30.5, "moderate": 28.5, "heavy": 27.5, "very_heavy": None},
    0.50: {"light": 31.5, "moderate": 29.5, "heavy": 28.5, "very_heavy": 27.5},
    0.25: {"light": 32.5, "moderate": 31.0, "heavy": 30.0, "very_heavy": 29.5},
}

# ACGIH 2017 Action Limit (unacclimatized worker) - e.g. a migrant worker
# in the first ~1-2 weeks, or after >1 week away from the heat.
_TLV_UNACCLIM = {
    1.00: {"light": 27.5, "moderate": 25.0, "heavy": 22.5, "very_heavy": None},
    0.75: {"light": 29.0, "moderate": 26.5, "heavy": 24.5, "very_heavy": None},
    0.50: {"light": 30.0, "moderate": 28.0, "heavy": 26.5, "very_heavy": 25.0},
    0.25: {"light": 31.0, "moderate": 29.0, "heavy": 28.0, "very_heavy": 26.5},
}


def _limits(acclimatized: bool):
    return _TLV_ACCLIM if acclimatized else _TLV_UNACCLIM


def allowable_work_fraction(
    wbgt_c: np.ndarray,
    workload: str = "moderate",
    acclimatized: bool = True,
) -> np.ndarray:
    """
    Max fraction of the hour that can be worked at this WBGT.

    Returns an array with values in {1.00, 0.75, 0.50, 0.25, 0.00}. 0.00
    means even a 15-min-work / 45-min-rest cycle exceeds the screening
    limit -> stop work.
    """
    if workload not in WORKLOADS:
        raise ValueError(f"workload must be one of {WORKLOADS}")
    w = np.asarray(wbgt_c, dtype=float)
    table = _limits(acclimatized)
    out = np.zeros_like(w)                       # default: stop
    # from most permissive cycle to least: first limit that is >= WBGT wins
    for frac in WORK_FRACTIONS:
        lim = table[frac][workload]
        if lim is None:
            continue
        out = np.where((out == 0.0) & (w <= lim), frac, out)
    # NaN WBGT -> NaN decision
    return np.where(np.isnan(w), np.nan, out)


def stop_work(
    wbgt_c: np.ndarray,
    workload: str = "moderate",
    acclimatized: bool = True,
) -> np.ndarray:
    """True where no safe work cycle exists for this workload/state."""
    return allowable_work_fraction(wbgt_c, workload, acclimatized) == 0.0


# Qatar Ministerial Decision 17/2021: blanket outdoor-work ban 10:00-15:30
# local time, 1 June - 15 September, plus a WBGT>32.1 stop anytime.
QATAR_BAN_MONTHS = (6, 7, 8, 9)
QATAR_BAN_START_HOUR = 10.0
QATAR_BAN_END_HOUR = 15.5
QATAR_BAN_SEPT_LAST_DAY = 15


def in_qatar_calendar_ban(local_times) -> np.ndarray:
    """Boolean mask: is this local timestamp inside the calendar ban window?"""
    import pandas as pd

    lt = pd.DatetimeIndex(local_times)
    hod = lt.hour + lt.minute / 60.0
    in_months = np.isin(lt.month, QATAR_BAN_MONTHS)
    not_late_sept = ~((lt.month == 9) & (lt.day > QATAR_BAN_SEPT_LAST_DAY))
    in_hours = (hod >= QATAR_BAN_START_HOUR) & (hod < QATAR_BAN_END_HOUR)
    return np.asarray(in_months & not_late_sept & in_hours)
