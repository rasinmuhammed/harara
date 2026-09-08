"""
Risk-optimal work/rest scheduling for outdoor labour under an uncertain
WBGT forecast.

The decision each hour is a work fraction w_h in [0,1] (0 = full rest in
shade, 1 = continuous work). A crew must deliver `w_req` effective
work-hours over the day's allowed window.

Accumulated thermal load (a deliberately simple, transparent 1-state
integrator; upgrade path is a multi-node model such as Fiala/JOS-3):

    load_h        = max(0, WBGT_h - WBGT_ref) ** p          # per worked hour
    H_h           = sum_{k<=h} phi**(h-k) * w_k * load_k     # retained load
    day_strain    = max_h H_h                                # peak retained load

`phi` is passive hourly retention (rest cools only by not adding load, a
conservative simplification). The objective is the CONDITIONAL VALUE AT
RISK of `day_strain` across forecast scenarios (Rockafellar-Uryasev),
i.e. the mean of the worst (1-beta) fraction of scenarios - so the plan
is robust to the bad forecast draws, not just good on average.

Everything below is a linear program; solved with SciPy/HiGHS.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

WBGT_REF_DEFAULT = 28.0     # ~ ACGIH continuous-work limit, moderate workload
PHI_DEFAULT = 0.80          # hourly retained fraction (~3 h half-life)
P_DEFAULT = 1.0             # load exponent (1 -> LP; >1 still LP, precomputed)


def hourly_load(wbgt: np.ndarray, wbgt_ref=WBGT_REF_DEFAULT, p=P_DEFAULT) -> np.ndarray:
    return np.maximum(0.0, np.asarray(wbgt, dtype=float) - wbgt_ref) ** p


def _retention_matrix(H: int, phi: float) -> np.ndarray:
    """Lower-triangular A with A[h,k] = phi**(h-k) for k<=h."""
    idx = np.arange(H)
    d = idx[:, None] - idx[None, :]
    A = np.where(d >= 0, phi ** np.clip(d, 0, None), 0.0)
    return A


def retained_load_path(w: np.ndarray, wbgt_true: np.ndarray,
                       phi=PHI_DEFAULT, wbgt_ref=WBGT_REF_DEFAULT,
                       p=P_DEFAULT) -> np.ndarray:
    """Hour-by-hour retained thermal load for a schedule against one WBGT path."""
    load = hourly_load(wbgt_true, wbgt_ref, p)
    A = _retention_matrix(len(w), phi)
    return A @ (np.asarray(w, dtype=float) * load)


def realized_strain(w: np.ndarray, wbgt_true: np.ndarray,
                    phi=PHI_DEFAULT, wbgt_ref=WBGT_REF_DEFAULT, p=P_DEFAULT) -> float:
    """Peak retained thermal load for a schedule against one WBGT path."""
    return float(retained_load_path(w, wbgt_true, phi, wbgt_ref, p).max())


@dataclass
class ScheduleResult:
    w: np.ndarray
    status: str
    obj: float


def schedule_cvar(
    wbgt_scenarios: np.ndarray,     # (S, H) forecast scenarios of hourly WBGT
    allowed: np.ndarray,            # (H,) bool: hour may be worked
    w_req: float,                   # required effective work-hours
    beta: float = 0.90,             # CVaR tail level
    phi: float = PHI_DEFAULT,
    wbgt_ref: float = WBGT_REF_DEFAULT,
    p: float = P_DEFAULT,
) -> ScheduleResult:
    """
    min_w  CVaR_beta[ max_h H_h(w; scenario) ]
    s.t.   sum_h w_h >= w_req,   0 <= w_h <= allowed_h

    LP variables: w (H), per-scenario peak m (S), VaR level t (1),
    tail excess z (S).
    """
    S, H = wbgt_scenarios.shape
    A = _retention_matrix(H, phi)
    loads = hourly_load(wbgt_scenarios, wbgt_ref, p)          # (S, H)
    # C[s] : (H, H) mapping w -> H_path for scenario s  = A * diag(loads[s])
    # constraint  m_s >= (A @ (w*loads[s]))_h   for all h
    nx = H + S + 1 + S
    iw = slice(0, H)
    im = slice(H, H + S)
    it = H + S
    iz = slice(H + S + 1, H + S + 1 + S)

    c = np.zeros(nx)
    c[it] = 1.0
    c[iz] = 1.0 / ((1.0 - beta) * S)

    rows_A, rows_b = [], []

    # m_s - sum_k A[h,k]*loads[s,k]*w_k >= 0   ->   (<=) form: sum(...) - m_s <= 0
    for s in range(S):
        Wmap = A * loads[s][None, :]          # (H, H); row h, col k
        for h in range(H):
            row = np.zeros(nx)
            row[iw] = Wmap[h]
            row[im.start + s] = -1.0
            rows_A.append(row)
            rows_b.append(0.0)

    # z_s >= m_s - t   ->   m_s - t - z_s <= 0
    for s in range(S):
        row = np.zeros(nx)
        row[im.start + s] = 1.0
        row[it] = -1.0
        row[iz.start + s] = -1.0
        rows_A.append(row)
        rows_b.append(0.0)

    # sum_h w_h >= w_req   ->   -sum w <= -w_req
    row = np.zeros(nx)
    row[iw] = -1.0
    rows_A.append(row)
    rows_b.append(-float(w_req))

    A_ub = np.array(rows_A)
    b_ub = np.array(rows_b)

    bounds = (
        [(0.0, 1.0 if allowed[h] else 0.0) for h in range(H)]
        + [(0.0, None)] * S
        + [(None, None)]
        + [(0.0, None)] * S
    )

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if not res.success:
        # fall back: work the coolest allowed hours first
        return _greedy_fallback(wbgt_scenarios.mean(0), allowed, w_req)
    w = np.clip(res.x[iw], 0.0, 1.0)
    return ScheduleResult(w=w, status="optimal", obj=float(res.fun))


def _greedy_fallback(wbgt_point, allowed, w_req) -> ScheduleResult:
    w = np.zeros(len(wbgt_point))
    order = np.argsort(np.where(allowed, wbgt_point, np.inf))
    need = w_req
    for h in order:
        if not allowed[h] or need <= 0:
            break
        take = min(1.0, need)
        w[h] = take
        need -= take
    return ScheduleResult(w=w, status="greedy_fallback", obj=float("nan"))


# ----------------------------------------------------------------- policies
def policy_cvar(scenarios, allowed, w_req, **kw) -> np.ndarray:
    return schedule_cvar(scenarios, allowed, w_req, **kw).w


def policy_deterministic(point_forecast, allowed, w_req, **kw) -> np.ndarray:
    return schedule_cvar(point_forecast[None, :], allowed, w_req, **kw).w


def policy_clairvoyant(wbgt_true, allowed, w_req, **kw) -> np.ndarray:
    return schedule_cvar(wbgt_true[None, :], allowed, w_req, **kw).w


def policy_calendar(local_hour, allowed, ban_lo=10.0, ban_hi=15.5) -> np.ndarray:
    """Qatar Decision 17/2021 style: work all allowed daylight hours except
    the fixed midday ban window."""
    lh = np.asarray(local_hour, dtype=float)
    w = allowed.astype(float).copy()
    w[(lh >= ban_lo) & (lh < ban_hi)] = 0.0
    return w


def policy_reactive(signal_wbgt, allowed, w_req, hard_stop=32.1) -> np.ndarray:
    """Smart-reactive: fill the coolest allowed hours first up to w_req,
    never working an hour whose signal exceeds hard_stop unless there is no
    other way to meet the requirement."""
    sig = np.asarray(signal_wbgt, dtype=float)
    H = len(sig)
    w = np.zeros(H)
    safe = allowed & (sig <= hard_stop)
    for pool in (safe, allowed & ~safe):          # safe hours first, then forced
        for h in np.argsort(np.where(pool, sig, np.inf)):
            if not pool[h] or w.sum() >= w_req:
                break
            w[h] = min(1.0, w_req - w.sum())
    return w
