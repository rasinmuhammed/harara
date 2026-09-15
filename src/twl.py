"""
Thermal Work Limit (TWL), Brake & Bates (2002) -- the heat-stress index
industry practice in Abu Dhabi and the wider Gulf mining/oil-and-gas
sector references alongside WBGT (src.wbgt) and Dubai's heat index
(src.heat_index). Unlike WBGT and heat index, which are single-number
environmental readings, TWL is the maximum metabolic rate (W/m^2) an
acclimatised, well-hydrated worker can sustain in a given environment
without exceeding a deep-body core temperature of 38.2 C or a sweat rate
of 1.2 kg/hr -- the higher the number, the safer the environment. It
folds wind speed and clothing vapour permeability into the balance,
neither of which WBGT or heat index carry.

This module was deliberately NOT written from a partial description.
It is a direct, function-for-function port of the actual reference
implementation: Brake, D.J. (2002), PhD thesis, Curtin University of
Technology, Appendix C, "TWL formulation (Visual Basic code)",
`Function fHstTWLnew` (TWL Formulation I: Standard Formulation), pp.
178-183 -- not the simplified narrative walkthrough in section 3.1
("Derivation of TWL", pp. 95-107), which describes a piecewise
evaporation model (three "zones" of skin wettedness) that turns out NOT
to be what the shipped, validated code actually computes. The real
`fQbalError` function (p.182) solves the skin heat balance assuming
fully wet skin throughout (skin wettedness = 1); the zone-based curve
in the narrative section is explanatory background on the physiology,
not the production formula. Trusting the narrative over the code would
have shipped a formula the primary source itself does not use -- this
port follows the code.

Also published as: Brake, D.J. & Bates, G.P. (2002), "Limiting
Metabolic Rate (Thermal Work Limit) as an Index of Thermal Stress",
Applied Occupational and Environmental Hygiene, 17(3):176-186.

Method
------
`fHstTWLnew` does two nested solves:

1. Inner: for a given trial core temperature, find the mean skin
   temperature at which heat arriving from the core (a tanh curve fit
   to Wyndham's conductance data, `_conductance_curve`) equals heat
   leaving the skin to the environment (sensible + fully-wet
   evaporative loss). This module's `_solve_skin_temp` root-finds it
   with a vectorised bisection -- the reference code uses a Newton
   iteration, a different path to the same root of the same equation.

2. Outer: the reference code steps trial core temperature up from
   37.6 C in 0.1 C increments until either it exceeds the user's core
   -temperature limit (default 38.2 C) or the sweat rate implied by
   that core/skin combination (a separate tanh curve fit,
   `_sweat_rate_curve`, NOT the evaporation term used in step 1)
   exceeds the user's sweat-rate limit (default 1.2 kg/hr), then backs
   off one step. Both curves are monotonic in the thermoregulatory
   signal, so this module replaces the discrete 0.1 C scan with an
   exact outer root-find for the sweat-rate crossing when it binds
   before the core-temperature limit does -- the same converged answer
   the reference code's scan approximates, at machine precision instead
   of 0.1 C resolution. In hot, humid conditions (Harara's primary use
   case) the sweat-rate limit binds before the core-temperature limit
   materially more often than in hot, dry conditions, so this
   distinction is not a corner case here.

What this module does NOT do
-----------------------------
It takes mean radiant temperature as a required input, the same way
`src.wbgt.wbgt_liljegren_c` takes shortwave/direct radiation and lets
`thermofeel` solve the globe-temperature energy balance internally --
but `thermofeel` has no public function that derives mean radiant
temperature from only the fields Harara's Doha archive carries
(shortwave + direct beam; the reference code's own MRT-from-globe path
needs a measured globe temperature, and ECMWF-style full-sky MRT needs
a fuller radiation field set: net shortwave, downward and net thermal
longwave). Wiring TWL to run end-to-end on Harara's existing weather
record is therefore a real, separate follow-up, not done here.

Reference:
- Brake, D.J. (2002), PhD thesis, Curtin University of Technology.
  https://curate.curtin.edu.au/articles/thesis/The_Deep_Body_Core_Temperatures_Physical_Fatigue_and_Fluid_Status_of_Thermally_Stressed_Workers_and_the_Development_of_Thermal_Work_Limit_as_an_Index_of_Heat_Stress/31454590
- Brake, D.J. & Bates, G.P. (2002), Applied Occupational and
  Environmental Hygiene, 17(3):176-186.
  https://doi.org/10.1080/104732202753438261
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.psychro import saturation_vapor_pressure_hpa

# Standard TWL formulation defaults (thesis Appendix C, fHstTWLnew's own
# optional-argument defaults): clothing typical of an acclimatised
# industrial worker in a summer cotton shirt and trousers.
DEFAULT_CLO = 0.35                        # Iclo: intrinsic clothing insulation [clo]
DEFAULT_VAPOR_PERMEATION_EFFICIENCY = 0.45  # VapPerm (i_cl)
DEFAULT_POSTURE_FACTOR = 0.73             # Posture, standing person
DEFAULT_CORE_TEMP_LIMIT_C = 38.2          # TcTarget
DEFAULT_SWEAT_RATE_MAX_KG_HR = 1.2        # SrMaxkgperhr, per standard 1.8 m^2 person
STANDARD_BODY_SURFACE_AREA_M2 = 1.8       # cStdSurfArea
MIN_WIND_MS = 0.2                         # RelWind floor ("natural convection")
LATENT_HEAT_WM2_PER_KG_M2_HR = 675.0      # 2430 kJ/kg @ 30 C, kJ/(m^2.hr) -> W/m^2
CORE_TEMP_SCAN_FLOOR_C = 36.0             # a physiologically resting-range floor
                                           # for the outer root-find's lower bound

# Table 8 (thesis p.108): action levels for self-paced work.
TWL_WITHDRAWAL_WM2 = 115.0
TWL_BUFFER_WM2 = 140.0
TWL_ACCLIMATISATION_WM2 = 220.0
# Backstops applied irrespective of the computed TWL (thesis p.109-110):
DRY_BULB_WITHDRAWAL_C = 44.0
WET_BULB_WITHDRAWAL_C = 32.0


def _p_sat_kpa(t_c: np.ndarray) -> np.ndarray:
    return saturation_vapor_pressure_hpa(t_c) / 10.0


def _conductance_curve(tsigma: np.ndarray) -> np.ndarray:
    """fPhyConductanceCurve: core-to-skin heat conductance, W/(m^2.C)."""
    return 84.0 + 72.0 * np.tanh(1.3 * (tsigma - 37.9))


def _sweat_rate_curve(tsigma: np.ndarray) -> np.ndarray:
    """fPhySweatRateCurve: sweat rate, kg/(m^2.hr) -- used only to check
    the user's sweat-rate limit, NOT in the skin heat balance itself
    (see module docstring)."""
    return 0.42 + 0.44 * np.tanh(1.16 * (tsigma - 37.4))


@dataclass
class _Constants:
    """Per-point quantities that do not depend on the unknown skin
    temperature, computed once rather than inside the root-find loops."""
    pa: np.ndarray
    hc: np.ndarray
    fcl: np.ndarray
    rcl: np.ndarray
    he: np.ndarray
    fpcl: np.ndarray


def _constants(t_air_c, rh_pct, pressure_hpa, wind_ms, clo, icl) -> _Constants:
    p_kpa = np.asarray(pressure_hpa, dtype=float) / 10.0
    pa = _p_sat_kpa(t_air_c) * np.asarray(rh_pct, dtype=float) / 100.0
    v = np.maximum(np.asarray(wind_ms, dtype=float), MIN_WIND_MS)

    hc = 0.608 * p_kpa ** 0.6 * v ** 0.6                       # EESAM p500 eqn 13
    fcl = 1.0 + 0.3 * clo                                      # ASHRAE eqn 47
    rcl = 0.155 * clo                                          # ASHRAE eqn 41
    he = 1587.0 * hc * p_kpa / (p_kpa - pa) ** 2                # EESAM p501 eqn 17
    lr = 16.5                                                   # Lewis Ratio
    recl = rcl / (lr * icl)                                     # ASHRAE Table 2
    fpcl = 1.0 / (1.0 + fcl * he * recl)                        # ASHRAE Table 2
    return _Constants(pa=pa, hc=hc, fcl=fcl, rcl=rcl, he=he, fpcl=fpcl)


def _qbal_error(tskin, t_air_c, t_rad_c, t_core_c, c: _Constants, posture_factor):
    """fQbalError, ported directly: Qskintoenv - Qcoretoskin, assuming
    fully wet skin (w=1) -- zero at the true skin temperature for this
    trial core temperature."""
    hr = posture_factor * 4.61 * (1.0 + ((t_rad_c + tskin) / 546.0) ** 3)  # EESAM p500 eqn 9
    h = hr + c.hc                                                # ASHRAE eqn 9
    toper = (hr * t_rad_c + c.hc * t_air_c) / h                  # ASHRAE eqn 8
    fcle = c.fcl / (1.0 + c.fcl * h * c.rcl)                     # ASHRAE Table 2
    cr = fcle * h * (tskin - toper)                              # C + R

    psat_skin = _p_sat_kpa(tskin)
    eskin = c.fpcl * c.fcl * c.he * (psat_skin - c.pa)           # w = 1, fully wet skin

    tsigma = 0.1 * tskin + 0.9 * t_core_c
    qcoretoskin = _conductance_curve(tsigma) * (t_core_c - tskin)
    return (cr + eskin) - qcoretoskin


def _solve_skin_temp(t_air_c, t_rad_c, t_core_c, c: _Constants, posture_factor,
                      n_bisections: int) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised bisection for fFindTsforQbal's root, at a given trial
    core temperature. Returns (tskin, valid) -- valid is False where no
    sign change exists in [10 C, t_core_c) (no physically valid steady
    state at that core temperature, e.g. dew point too high)."""
    shape = np.broadcast(t_air_c, t_rad_c, t_core_c).shape
    lo = np.broadcast_to(np.float64(10.0), shape).copy()
    hi = np.broadcast_to(t_core_c, shape).astype(float) - 1e-3

    def f(tskin):
        return _qbal_error(tskin, t_air_c, t_rad_c, t_core_c, c, posture_factor)

    f_lo, f_hi = f(lo), f(hi)
    valid = np.sign(f_lo) != np.sign(f_hi)
    for _ in range(n_bisections):
        mid = 0.5 * (lo + hi)
        same_side_as_lo = np.sign(f(mid)) == np.sign(f_lo)
        lo = np.where(same_side_as_lo, mid, lo)
        hi = np.where(same_side_as_lo, hi, mid)
    return 0.5 * (lo + hi), valid


def twl_wm2(
    t_air_c: np.ndarray,
    rh_pct: np.ndarray,
    pressure_hpa: np.ndarray,
    wind_speed_ms: np.ndarray,
    mean_radiant_temp_c: np.ndarray,
    *,
    core_temp_limit_c: float = DEFAULT_CORE_TEMP_LIMIT_C,
    sweat_rate_max_kg_hr: float = DEFAULT_SWEAT_RATE_MAX_KG_HR,
    clo: float = DEFAULT_CLO,
    vapor_permeation_efficiency: float = DEFAULT_VAPOR_PERMEATION_EFFICIENCY,
    posture_factor: float = DEFAULT_POSTURE_FACTOR,
    n_bisections: int = 60,
) -> np.ndarray:
    """
    Thermal Work Limit in W/m^2: the maximum sustainable metabolic rate
    at which deep-body core temperature and sweat rate both stay within
    their limits. Higher is safer (more work capacity); see
    TWL_WITHDRAWAL_WM2 etc. for the published self-paced-work action
    levels.

    Parameters
    ----------
    t_air_c              : dry-bulb air temperature [C]
    rh_pct                : relative humidity [%]
    pressure_hpa           : barometric pressure [hPa]
    wind_speed_ms          : wind speed over the skin [m/s] (clamped to
                             the reference implementation's 0.2 m/s floor)
    mean_radiant_temp_c    : mean radiant temperature [C] -- NOT derived
                             here; see the module docstring for why.

    Returns NaN where the skin-temperature root-find has no sign change
    within [10 C, core_temp_limit_c) at the core-temperature limit --
    the same "no solution" case the reference implementation reports as
    an error (dew point too high, or conditions too cold with too much
    wind, for any steady state to exist within the model's assumptions).
    """
    t_air_c, rh_pct, pressure_hpa, wind_speed_ms, mean_radiant_temp_c = (
        np.broadcast_arrays(
            np.asarray(t_air_c, dtype=float), np.asarray(rh_pct, dtype=float),
            np.asarray(pressure_hpa, dtype=float), np.asarray(wind_speed_ms, dtype=float),
            np.asarray(mean_radiant_temp_c, dtype=float),
        )
    )
    c = _constants(t_air_c, rh_pct, pressure_hpa, wind_speed_ms, clo,
                   vapor_permeation_efficiency)
    sweat_rate_max_kg_m2_hr = sweat_rate_max_kg_hr / STANDARD_BODY_SURFACE_AREA_M2

    # Try the core-temperature limit first (the common case: sweat rate
    # has not yet saturated when core temperature reaches its cap).
    tc_cap = np.full(t_air_c.shape, core_temp_limit_c)
    ts_at_cap, valid_at_cap = _solve_skin_temp(
        t_air_c, mean_radiant_temp_c, tc_cap, c, posture_factor, n_bisections)
    tsigma_at_cap = 0.1 * ts_at_cap + 0.9 * tc_cap
    sr_at_cap = _sweat_rate_curve(tsigma_at_cap)
    sweat_binds = sr_at_cap > sweat_rate_max_kg_m2_hr

    # Where sweat rate would already exceed its cap at the core-
    # temperature limit, root-find the lower core temperature at which
    # the sweat-rate cap is exactly met (sweat rate is monotonic in
    # core temperature, so this has a unique solution) -- the exact
    # limit the reference implementation's 0.1 C outer scan approximates.
    lo_tc = np.full(t_air_c.shape, CORE_TEMP_SCAN_FLOOR_C)
    hi_tc = tc_cap.copy()

    def sr_minus_max(tc_trial):
        ts_trial, _ = _solve_skin_temp(
            t_air_c, mean_radiant_temp_c, tc_trial, c, posture_factor, n_bisections)
        tsig = 0.1 * ts_trial + 0.9 * tc_trial
        return _sweat_rate_curve(tsig) - sweat_rate_max_kg_m2_hr

    for _ in range(n_bisections):
        mid_tc = 0.5 * (lo_tc + hi_tc)
        # sr_minus_max < 0 below the crossing, > 0 above it (monotonic increasing)
        below = sr_minus_max(mid_tc) < 0.0
        lo_tc = np.where(below, mid_tc, lo_tc)
        hi_tc = np.where(below, hi_tc, mid_tc)
    tc_sweat_limited = 0.5 * (lo_tc + hi_tc)

    tc_final = np.where(sweat_binds, tc_sweat_limited, tc_cap)
    ts_final, valid_final = _solve_skin_temp(
        t_air_c, mean_radiant_temp_c, tc_final, c, posture_factor, n_bisections)
    valid = np.where(sweat_binds, valid_final, valid_at_cap)

    tsigma = 0.1 * ts_final + 0.9 * tc_final
    h_core_to_skin = _conductance_curve(tsigma) * (tc_final - ts_final)

    k = (0.0014 * (34.0 - t_air_c) + 0.0173 * (5.87 - c.pa))     # ASHRAE eqn 26,
    m = h_core_to_skin * (1.0 + k)                               # as in fHstTWLnew directly

    return np.where(valid, m, np.nan)


def classify(twl_wm2_value: np.ndarray, dry_bulb_c: np.ndarray,
             wet_bulb_c: np.ndarray) -> np.ndarray:
    """
    Table 8 (thesis p.108) self-paced-work action level, as a string
    array: "withdrawal", "buffer", "acclimatisation_only", "unrestricted".
    The dry-bulb (44 C) and wet-bulb (32 C) backstops apply irrespective
    of the computed TWL value (thesis p.109-110).
    """
    twl = np.asarray(twl_wm2_value, dtype=float)
    db = np.asarray(dry_bulb_c, dtype=float)
    wb = np.asarray(wet_bulb_c, dtype=float)

    out = np.where(twl >= TWL_ACCLIMATISATION_WM2, "unrestricted",
           np.where(twl >= TWL_BUFFER_WM2, "acclimatisation_only",
           np.where(twl >= TWL_WITHDRAWAL_WM2, "buffer", "withdrawal")))
    backstop = (db > DRY_BULB_WITHDRAWAL_C) | (wb > WET_BULB_WITHDRAWAL_C)
    return np.where(backstop, "withdrawal", out)
