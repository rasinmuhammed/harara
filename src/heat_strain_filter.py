"""
Sequential estimation of individual heat strain with a physical process
model, and forecast-driven forward prediction of it.

USARIEM's ECTemp (Buller et al., 2013) estimates core temperature from
heart rate alone with a random-walk process model. Here the process model
is the two-node thermoregulation model (src.thermoreg), forced by the
measured (and, for prediction, forecast) environment and an activity
estimate. The filter carries a per-person multiplicative metabolic scale
as a latent state, so it self-calibrates to the individual and absorbs
activity-sensor error. Observations are heart rate and, optionally, a
skin-temperature patch.

Relative to a heart-rate-only filter, this gives lower estimation error
when heart rate is ambiguous (the same heart rate can correspond to
different core temperatures depending on workload), and an anticipatory
forecast: propagating the particle cloud forward under an ensemble of WBGT
forecast scenarios gives the probability of core temperature exceeding a
limit within the next H minutes and the time-to-limit distribution.

A particle filter rather than an extended Kalman filter is used because
the dynamics are stiff and non-Gaussian near the uncompensable transition.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.thermoreg import (
    A_RAD_FRAC, C_BODY, CDIL, CSTR, CSW, EMISS, I_CL, LR, MSW_MAX, SBC,
    SKBF_MAX, SKBF_MIN, SKBF_NEUTRAL, TCR_SET, TSK_SET, Subject,
)

ALPHA_MIN, ALPHA_MAX = 0.04, 0.35


def _p_sat_kpa(t_c):
    return 0.61078 * np.exp(17.27 * t_c / (t_c + 237.3))


def dynamics_vec(t_cr, t_sk, m_scale, sub: Subject, dt_s, t_air, rh, wind,
                 t_rad, met_wm2):
    """Vectorised one-step twin of src.thermoreg.step (particles along axis
    0). Returns (t_cr', t_sk', hr_pred)."""
    a_d = sub.a_dubois
    t_r = t_air if t_rad is None else t_rad
    p_a = float(_p_sat_kpa(t_air) * rh / 100.0)
    met = np.maximum(30.0, met_wm2 * m_scale)

    v = max(wind, 0.05)
    h_c = float(np.clip(8.7 * v ** 0.6, 3.5, 70.0))
    h_r = 4.0 * EMISS * SBC * A_RAD_FRAC * (273.15 + (t_sk + t_r) / 2.0) ** 3
    h = h_c + h_r
    f_cl = 1.0 + 0.31 * sub.clo
    r_cl = 0.155 * sub.clo
    r_e_cl = r_cl / (LR * I_CL)
    t_op = (h_r * t_r + h_c * t_air) / h
    r_t = r_cl + 1.0 / (f_cl * h)
    r_e_t = r_e_cl + 1.0 / (f_cl * LR * h_c)

    c_res = 0.0014 * met * (34.0 - t_air)
    e_res = 0.0173 * met * max(0.0, 5.87 - p_a)
    dry = (t_sk - t_op) / r_t

    warm_cr = np.clip(t_cr - TCR_SET, 0, None)
    cold_sk = np.clip(TSK_SET - t_sk, 0, None)
    warm_sk = np.clip(t_sk - TSK_SET, 0, None)
    skbf = np.clip((SKBF_NEUTRAL + CDIL * warm_cr) / (1.0 + CSTR * cold_sk),
                   SKBF_MIN, SKBF_MAX)
    warm_b = np.clip(0.1 * t_cr + 0.9 * t_sk - (0.1 * TCR_SET + 0.9 * TSK_SET),
                     0, None)
    m_rsw = np.clip(CSW * warm_b * np.exp(warm_sk / 10.7), 0.0, MSW_MAX)
    e_max = np.maximum(1e-6, (_p_sat_kpa(t_sk) - p_a) / r_e_t)
    w = np.clip(0.06 + 0.94 * (m_rsw / e_max), 0.06, 1.0)
    e_sk = w * e_max

    k_cond = 5.28 + 1.163 * skbf
    q = k_cond * (t_cr - t_sk)
    s_cr = met - sub.work_eff * met - c_res - e_res - q
    s_sk = q - dry - e_sk

    alpha = np.clip(0.0418 + 0.745 / (skbf + 0.585), ALPHA_MIN, ALPHA_MAX)
    c_cr = (1 - alpha) * sub.mass_kg * C_BODY / a_d
    c_sk = alpha * sub.mass_kg * C_BODY / a_d

    t_cr2 = t_cr + dt_s * s_cr / c_cr
    t_sk2 = t_sk + dt_s * s_sk / c_sk
    hr = (sub.hr_rest + 0.28 * (met - 58.0)
          + 16.0 * np.clip(t_cr2 - 37.0, 0, None)
          + 12.0 * (skbf / SKBF_MAX))
    hr = np.clip(hr, sub.hr_rest, sub.hr_max)
    return t_cr2, t_sk2, hr


@dataclass
class Prediction:
    horizon_min: float
    p_exceed: float
    ttt_median_min: float          # median time-to-threshold (inf if unlikely)
    ttt_p10_min: float             # earliest plausible (10th pct)
    core_p50: np.ndarray
    core_p95: np.ndarray
    minutes: np.ndarray


class HeatStrainParticleFilter:
    def __init__(self, sub: Subject, n: int = 400, seed: int = 0,
                 q_cr: float = 0.05, q_sk: float = 0.09, q_mscale: float = 0.035,
                 hr_sd: float = 7.5, tsk_sd: float = 0.5, rough: float = 0.8):
        self.sub = sub
        self.n = n
        self.rng = np.random.default_rng(seed)
        self.t_cr = 36.9 + self.rng.normal(0, 0.20, n)
        self.t_sk = 34.0 + self.rng.normal(0, 0.6, n)
        self.m_scale = np.clip(self.rng.normal(1.0, 0.22, n), 0.4, 2.0)
        self.w = np.full(n, 1.0 / n)
        self.q_cr, self.q_sk, self.q_ms = q_cr, q_sk, q_mscale
        self.hr_sd, self.tsk_sd = hr_sd, tsk_sd
        self.rough = rough          # roughening scale (fraction of spread)

    # - weighted summaries -------------------------------------------------
    def _wq(self, x, q):
        i = np.argsort(x)
        c = np.cumsum(self.w[i])
        return float(np.interp(q, c, x[i]))

    @property
    def core_mean(self):
        return float(np.sum(self.w * self.t_cr))

    def core_ci(self, lo=0.025, hi=0.975):
        return self._wq(self.t_cr, lo), self._wq(self.t_cr, hi)

    # - one assimilation step ------------------------------------------------
    def update(self, dt_s, t_air, rh, wind, t_rad, met_est, hr_obs,
               tsk_obs=None):
        # propagate
        tcr, tsk, hr_pred = dynamics_vec(
            self.t_cr, self.t_sk, self.m_scale, self.sub, dt_s,
            t_air, rh, wind, t_rad, met_est)
        tcr += self.rng.normal(0, self.q_cr * np.sqrt(dt_s / 60.0), self.n)
        tsk += self.rng.normal(0, self.q_sk * np.sqrt(dt_s / 60.0), self.n)
        self.m_scale = np.clip(
            self.m_scale + self.rng.normal(0, self.q_ms * np.sqrt(dt_s / 60.0),
                                           self.n), 0.5, 1.8)
        self.t_cr, self.t_sk = tcr, tsk

        # weight by observation likelihood
        ll = -0.5 * ((hr_obs - hr_pred) / self.hr_sd) ** 2
        if tsk_obs is not None:
            ll = ll - 0.5 * ((tsk_obs - self.t_sk) / self.tsk_sd) ** 2
        ll -= ll.max()
        self.w *= np.exp(ll)
        s = self.w.sum()
        if s <= 0 or not np.isfinite(s):
            self.w = np.full(self.n, 1.0 / self.n)
        else:
            self.w /= s

        # resample if degenerate, then ROUGHEN (kernel jitter) so the cloud
        # does not collapse to duplicate points - this is what keeps the
        # credible interval honest.
        ess = 1.0 / np.sum(self.w ** 2)
        if ess < self.n / 2:
            pos = (self.rng.random() + np.arange(self.n)) / self.n
            idx = np.searchsorted(np.cumsum(self.w), pos)
            idx = np.clip(idx, 0, self.n - 1)
            self.t_cr, self.t_sk = self.t_cr[idx].copy(), self.t_sk[idx].copy()
            self.m_scale = self.m_scale[idx].copy()
            self.w = np.full(self.n, 1.0 / self.n)
            k = self.rough * self.n ** (-1.0 / 3.0)          # Silverman-ish
            self.t_cr += self.rng.normal(0, k * (self.t_cr.std() + 1e-3), self.n)
            self.t_sk += self.rng.normal(0, k * (self.t_sk.std() + 1e-3), self.n)
            self.m_scale = np.clip(
                self.m_scale + self.rng.normal(
                    0, k * (self.m_scale.std() + 1e-3), self.n), 0.4, 2.0)

    # - anticipatory forecast --------------------------------------------
    def predict_forward(self, env_scenarios, met_plan, dt_s=300.0,
                        threshold=38.5, n_sub=64) -> Prediction:
        """
        env_scenarios: dict with arrays (S, T) for 't_air','rh','wind' and
                       optionally 't_rad', on a common T-step grid (dt_s).
        met_plan:      (T,) planned metabolic rate per step.
        Propagates a subsample of particles under each scenario.
        """
        S, T = env_scenarios["t_air"].shape
        # subsample particles by weight
        pos = (self.rng.random() + np.arange(n_sub)) / n_sub
        pi = np.clip(np.searchsorted(np.cumsum(self.w), pos), 0, self.n - 1)
        base_cr, base_sk, base_ms = self.t_cr[pi], self.t_sk[pi], self.m_scale[pi]

        M = S * n_sub
        cr = np.repeat(base_cr, S).reshape(n_sub, S).T.reshape(M).copy()
        sk = np.repeat(base_sk, S).reshape(n_sub, S).T.reshape(M).copy()
        ms = np.repeat(base_ms, S).reshape(n_sub, S).T.reshape(M).copy()
        sc = np.tile(np.arange(S), n_sub)

        traj = np.empty((T, M))
        crossed_at = np.full(M, np.inf)
        n_sub_int = max(1, int(round(dt_s / 60.0)))     # <=60 s integration steps
        dt_int = dt_s / n_sub_int
        for k in range(T):
            for s in range(S):
                m = sc == s
                ta = float(env_scenarios["t_air"][s, k])
                rh = float(env_scenarios["rh"][s, k])
                wd = float(env_scenarios["wind"][s, k])
                tr = (float(env_scenarios["t_rad"][s, k])
                      if "t_rad" in env_scenarios else None)
                for _ in range(n_sub_int):
                    cr[m], sk[m], _ = dynamics_vec(
                        cr[m], sk[m], ms[m], self.sub, dt_int,
                        ta, rh, wd, tr, met_plan[k])
                    # forward process noise - without it the predictive
                    # ensemble is falsely sharp and probabilities mis-calibrate
                    cr[m] += self.rng.normal(
                        0, self.q_cr * np.sqrt(dt_int / 60.0), m.sum())
                    sk[m] += self.rng.normal(
                        0, self.q_sk * np.sqrt(dt_int / 60.0), m.sum())
            newly = (cr >= threshold) & ~np.isfinite(crossed_at)
            crossed_at[newly] = (k + 1) * dt_s / 60.0
            traj[k] = cr

        minutes = (np.arange(T) + 1) * dt_s / 60.0
        p_exc = float(np.mean(np.isfinite(crossed_at)))
        finite = crossed_at[np.isfinite(crossed_at)]
        return Prediction(
            horizon_min=float(minutes[-1]),
            p_exceed=p_exc,
            ttt_median_min=float(np.median(finite)) if finite.size else float("inf"),
            ttt_p10_min=float(np.percentile(finite, 10)) if finite.size else float("inf"),
            core_p50=np.percentile(traj, 50, axis=1),
            core_p95=np.percentile(traj, 95, axis=1),
            minutes=minutes,
        )
