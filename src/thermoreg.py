"""
Two-node human thermoregulation model (Gagge, Stolwijk & Nishi 1971),
compact SI implementation.

Used here as a FORWARD SIMULATOR: given a time series of environment
(air temperature, humidity, wind, mean radiant temperature) and metabolic
rate, it integrates core and skin temperature and the controller outputs
(skin blood flow, sweat rate). In the digital-twin study it plays two
roles: (1) generate synthetic "ground-truth" core temperature and heart
rate to develop and stress-test the estimator before any pilot data
exists; (2) serve as the process model inside the particle filter.

Behaviour checks (see scripts/thermoreg_check.py):
  - rest, 25 C / 50 % / 0.1 m/s        -> Tcr ~36.8, Tsk ~32-33, HR ~70
  - moderate work ~250 W/m2, 30-38 C   -> Tcr plateaus 37.3-38.0 (compensable)
  - heavy work >=350 W/m2, >=36 C       -> Tcr climbs steadily (uncompensable)
  - 25/15 min work/rest cycling at WBGT ~29 -> Tcr plateaus ~37.5 (safe)
  - HR spans ~70..~185 rest->very-heavy and stays monotone in core temp

Known biases: the 2-node rational form runs core temperature UP somewhat
fast in strongly uncompensable heat (no volitional-exhaustion cap), and
has not been calibrated to Gulf-worker field data - that calibration is
a pilot deliverable. For a safety tool the fast-rise bias is the
conservative direction.

References:
  Gagge A.P., Stolwijk J.A.J., Nishi Y. (1971) An effective temperature
  scale based on a simple model of human physiological regulatory
  response. ASHRAE Trans 77(1):247-262.
  ISO 7933:2004 (analytical heat-balance terms and limits).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# ---- body / physical constants -------------------------------------------------
C_BODY = 3490.0        # J/(kg K), mean specific heat of body tissue
LR = 16.5              # K/kPa, Lewis ratio for air
SBC = 5.67e-8          # Stefan-Boltzmann
EMISS = 0.95           # skin emissivity
A_RAD_FRAC = 0.72      # effective radiating area fraction (standing)
CP_AIR = 1005.0        # J/(kg K)

# set points and control gains (Gagge 1971 / ASHRAE Fundamentals)
TCR_SET = 36.8
TSK_SET = 33.7
CSW = 200.0           # sweat gain, W/m2 per K of body warm signal
CDIL = 120.0          # vasodilation gain, (L/h/m2) per K core warm signal
CSTR = 0.5            # vasoconstriction gain, per K skin cold signal
SKBF_NEUTRAL = 6.3    # L/(h m2)
SKBF_MAX = 90.0
SKBF_MIN = 0.5
MSW_MAX = 650.0       # W/m2, ceiling on evaporative heat from sweating (~1.6 L/h)
I_CL = 0.45           # clothing moisture permeability index (light, permeable)
ALPHA_MIN, ALPHA_MAX = 0.04, 0.35   # skin mass fraction bounds


@dataclass
class Subject:
    mass_kg: float = 74.0
    height_m: float = 1.75
    work_eff: float = 0.0          # mechanical efficiency of the task
    clo: float = 0.35            # light summer work clothing
    hr_rest: float = 70.0
    hr_max: float = 190.0

    @property
    def a_dubois(self) -> float:
        return 0.202 * self.mass_kg ** 0.425 * self.height_m ** 0.725


@dataclass
class ThermoState:
    t_cr: float = 36.9
    t_sk: float = 34.0
    # diagnostics filled by step()
    skbf: float = SKBF_NEUTRAL
    m_sweat_wm2: float = 0.0
    skin_wettedness: float = 0.06
    hr: float = 70.0


def _p_sat_kpa(t_c: np.ndarray) -> np.ndarray:
    """Saturation vapour pressure over water, kPa (Antoine-ish, ASHRAE)."""
    return 0.61078 * np.exp(17.27 * t_c / (t_c + 237.3))


def step(
    st: ThermoState,
    sub: Subject,
    dt_s: float,
    t_air_c: float,
    rh_pct: float,
    wind_ms: float,
    t_radiant_c: float | None,
    met_wm2: float,
) -> ThermoState:
    """Advance the two-node model by dt_s seconds. met_wm2 is metabolic
    rate per unit body surface area (rest ~58, walking ~150-200, hard
    manual labour ~350-450)."""
    a_d = sub.a_dubois
    t_r = t_air_c if t_radiant_c is None else t_radiant_c
    p_a = float(_p_sat_kpa(np.array(t_air_c)) * (rh_pct / 100.0))

    # --- heat transfer coefficients (W/m2K) ---
    v = max(wind_ms, 0.05)
    h_c = float(np.clip(8.7 * v ** 0.6, 3.5, 70.0))               # convection
    h_r = 4.0 * EMISS * SBC * A_RAD_FRAC * (273.15 + (st.t_sk + t_r) / 2.0) ** 3
    h = h_c + h_r
    f_cl = 1.0 + 0.31 * sub.clo                                   # clothing area factor
    r_cl = 0.155 * sub.clo                                        # m2K/W
    r_e_cl = r_cl / (LR * I_CL)                                   # evap clo resistance

    # operative temperature and series sensible/evaporative resistances
    t_op = (h_r * t_r + h_c * t_air_c) / h
    r_t = r_cl + 1.0 / (f_cl * h)                                 # sensible
    h_e = LR * h_c
    r_e_t = r_e_cl + 1.0 / (f_cl * h_e)                           # evaporative

    # --- respiratory losses (W/m2) ---
    c_res = 0.0014 * met_wm2 * (34.0 - t_air_c)
    e_res = 0.0173 * met_wm2 * max(0.0, 5.87 - p_a)

    # --- sensible skin loss ---
    dry = (st.t_sk - t_op) / r_t

    # --- controller signals ---
    warm_cr = max(0.0, st.t_cr - TCR_SET)
    cold_sk = max(0.0, TSK_SET - st.t_sk)
    warm_sk = max(0.0, st.t_sk - TSK_SET)
    # skin blood flow (L/h/m2)
    skbf = (SKBF_NEUTRAL + CDIL * warm_cr) / (1.0 + CSTR * cold_sk)
    skbf = float(np.clip(skbf, SKBF_MIN, SKBF_MAX))
    # sweat: driven by mean body warm signal, local skin multiplier
    warm_b = max(0.0, 0.1 * st.t_cr + 0.9 * st.t_sk - (0.1 * TCR_SET + 0.9 * TSK_SET))
    m_rsw = CSW * warm_b * float(np.exp(warm_sk / 10.7))
    m_rsw = float(np.clip(m_rsw, 0.0, MSW_MAX))
    # evaporation actually achievable given humidity and clothing
    p_sk_s = float(_p_sat_kpa(np.array(st.t_sk)))
    e_max = max(1e-6, (p_sk_s - p_a) / r_e_t)
    w = float(np.clip(0.06 + 0.94 * (m_rsw / e_max), 0.06, 1.0))   # skin wettedness
    e_sk = w * e_max

    # --- core<->skin conduction (tissue + convective via blood) ---
    k_cond = 5.28 + 1.163 * skbf                       # W/m2K
    q_cr_sk = k_cond * (st.t_cr - st.t_sk)

    # --- node energy balances (W/m2) ---
    s_cr = met_wm2 - sub.work_eff * met_wm2 - c_res - e_res - q_cr_sk
    s_sk = q_cr_sk - dry - e_sk

    # --- variable mass split by skin blood flow ---
    alpha = float(np.clip(0.0418 + 0.745 / (skbf + 0.585), ALPHA_MIN, ALPHA_MAX))
    c_cr = (1 - alpha) * sub.mass_kg * C_BODY / a_d    # J/(m2 K)
    c_sk = alpha * sub.mass_kg * C_BODY / a_d

    t_cr = st.t_cr + dt_s * s_cr / c_cr
    t_sk = st.t_sk + dt_s * s_sk / c_sk

    # --- heart rate (activity + thermal cardiovascular drift) ---
    # gains chosen so HR spans ~rest..~185 over rest->very-heavy work and
    # does not saturate for moderate work (keeps HR informative about core
    # temperature, which is the point for the estimator).
    hr = (sub.hr_rest
          + 0.28 * (met_wm2 - 58.0)                    # activity component
          + 16.0 * max(0.0, t_cr - 37.0)               # core thermal drift
          + 12.0 * (skbf / SKBF_MAX))                  # cutaneous circulatory load
    hr = float(np.clip(hr, sub.hr_rest, sub.hr_max))

    return ThermoState(t_cr=t_cr, t_sk=t_sk, skbf=skbf, m_sweat_wm2=m_rsw,
                       skin_wettedness=w, hr=hr)


def simulate(
    sub: Subject,
    minutes: np.ndarray,          # time stamps (minutes), strictly increasing
    t_air_c: np.ndarray,
    rh_pct: np.ndarray,
    wind_ms: np.ndarray,
    met_wm2: np.ndarray,
    t_radiant_c: np.ndarray | None = None,
    st0: ThermoState | None = None,
    substep_s: float = 30.0,
) -> dict:
    """Integrate over a schedule. Inputs are sampled per `minutes`; the
    model sub-steps at `substep_s`. Returns arrays aligned to `minutes`."""
    st = st0 or ThermoState()
    n = len(minutes)
    out = {k: np.empty(n) for k in ("t_cr", "t_sk", "hr", "skbf",
                                    "m_sweat_wm2", "skin_wettedness")}
    for i in range(n):
        if i > 0:
            span = (minutes[i] - minutes[i - 1]) * 60.0
            nsub = max(1, int(round(span / substep_s)))
            for _ in range(nsub):
                st = step(st, sub, span / nsub,
                          float(t_air_c[i]), float(rh_pct[i]), float(wind_ms[i]),
                          None if t_radiant_c is None else float(t_radiant_c[i]),
                          float(met_wm2[i]))
        for k in out:
            out[k][i] = getattr(st, k)
    out["state"] = st
    return out
