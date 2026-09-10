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

# ---- worker-time constraints (see docs/scheduler_worker_time_plan.md) --------
REST_ALLOWANCE_H = 2.0      # on-site hours allowed over the work owed
MAX_WORK_BLOCKS = 2         # at most a morning and an afternoon block
MIN_BLOCK_HOURS = 1.5       # a shorter block is not worth mobilising the crew
LAMBDA_TV = 0.15            # anti-fragmentation weight on sum |w_h - w_{h-1}|
LAMBDA_DEV = 0.05           # stability weight on sum |w_h - w_ref_h|
LAMBDA_REST = 0.25          # residual exposure of resting in the heat on site
BLOCK_EPS = 0.05            # work fraction at or below this counts as rest


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
    *,
    window: tuple[int, int] | None = None,   # (t_in, t_out) inclusive on-site window
    lambda_tv: float = 0.0,                   # weight on sum_h |w_h - w_{h-1}|
    lambda_dev: float = 0.0,                  # weight on sum_h |w_h - w_ref_h|
    w_ref: np.ndarray | None = None,          # reference schedule for lambda_dev
) -> ScheduleResult:
    """
    min_w  CVaR_beta[ max_h H_h(w; scenario) ]
             + lambda_tv * sum_h |w_h - w_{h-1}|
             + lambda_dev * sum_h |w_h - w_ref_h|
    s.t.   sum_h w_h >= w_req,   0 <= w_h <= allowed_h
           w_h = 0 outside `window` if given

    LP variables: w (H), per-scenario peak m (S), VaR level t (1),
    tail excess z (S), and - only when their weight is active - total-variation
    aux u (H-1) and deviation aux d (H). With the keyword args at their
    defaults this is the original CVaR LP unchanged.
    """
    S, H = wbgt_scenarios.shape
    A = _retention_matrix(H, phi)
    loads = hourly_load(wbgt_scenarios, wbgt_ref, p)          # (S, H)

    use_tv = lambda_tv > 0.0 and H >= 2
    use_dev = lambda_dev > 0.0 and w_ref is not None
    n_u = (H - 1) if use_tv else 0
    n_d = H if use_dev else 0

    # C[s] : (H, H) mapping w -> H_path for scenario s  = A * diag(loads[s])
    # constraint  m_s >= (A @ (w*loads[s]))_h   for all h
    nx = H + S + 1 + S + n_u + n_d
    iw = slice(0, H)
    im = slice(H, H + S)
    it = H + S
    iz = slice(H + S + 1, H + S + 1 + S)
    iu = H + S + 1 + S
    idv = H + S + 1 + S + n_u

    c = np.zeros(nx)
    c[it] = 1.0
    c[iz] = 1.0 / ((1.0 - beta) * S)
    if use_tv:
        c[iu:iu + n_u] = lambda_tv
    if use_dev:
        c[idv:idv + n_d] = lambda_dev

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

    # u_h >= |w_h - w_{h-1}|
    if use_tv:
        for h in range(1, H):
            for sgn in (1.0, -1.0):
                row = np.zeros(nx)
                row[h] = sgn
                row[h - 1] = -sgn
                row[iu + (h - 1)] = -1.0
                rows_A.append(row)
                rows_b.append(0.0)

    # d_h >= |w_h - w_ref_h|   (w_ref_h constant -> moves to b)
    if use_dev:
        wr = np.asarray(w_ref, dtype=float)
        for h in range(H):
            row = np.zeros(nx)
            row[h] = 1.0
            row[idv + h] = -1.0
            rows_A.append(row)
            rows_b.append(float(wr[h]))
            row = np.zeros(nx)
            row[h] = -1.0
            row[idv + h] = -1.0
            rows_A.append(row)
            rows_b.append(-float(wr[h]))

    A_ub = np.array(rows_A)
    b_ub = np.array(rows_b)

    hi = np.where(np.asarray(allowed, dtype=bool), 1.0, 0.0)
    if window is not None:
        t_in, t_out = window
        keep = np.zeros(H, dtype=bool)
        keep[t_in:t_out + 1] = True
        hi = np.where(keep, hi, 0.0)

    bounds = (
        [(0.0, float(hi[h])) for h in range(H)]
        + [(0.0, None)] * S
        + [(None, None)]
        + [(0.0, None)] * S
        + [(0.0, None)] * n_u
        + [(0.0, None)] * n_d
    )

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if not res.success:
        # fall back: work the coolest allowed hours first
        return _greedy_fallback(wbgt_scenarios.mean(0), hi > 0.0, w_req)
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


# ----------------------------------------------- worker-time / windowed search
@dataclass
class WindowedScheduleResult:
    w: np.ndarray
    status: str
    obj: float
    t_in: int
    t_out: int
    span_hours: int
    onsite_rest_hours: float
    n_blocks: int
    w_ref: np.ndarray


def _work_blocks(w: np.ndarray, eps: float = BLOCK_EPS) -> list[tuple[int, int]]:
    """Maximal runs of consecutive hours with w_h > eps, as (start, end) pairs
    with end inclusive."""
    runs: list[tuple[int, int]] = []
    start = None
    for h, v in enumerate(np.asarray(w, dtype=float)):
        if v > eps and start is None:
            start = h
        elif v <= eps and start is not None:
            runs.append((start, h - 1))
            start = None
    if start is not None:
        runs.append((start, len(w) - 1))
    return runs


def _worked_span(w: np.ndarray, eps: float = BLOCK_EPS) -> int:
    runs = _work_blocks(w, eps)
    if not runs:
        return 0
    return runs[-1][1] - runs[0][0] + 1


def cumulative_exposure(w: np.ndarray, wbgt: np.ndarray,
                        wbgt_ref: float = WBGT_REF_DEFAULT) -> float:
    """Time-integrated heat dose over WORKED time:
    sum_h w_h * max(0, wbgt_h - wbgt_ref). A stretched day can lower the peak
    retained load and still raise this."""
    w = np.asarray(w, dtype=float)
    wbgt = np.asarray(wbgt, dtype=float)
    return float(np.sum(w * np.maximum(0.0, wbgt - wbgt_ref)))


def policy_earlier_start(wbgt, allowed, w_req, hard_stop=32.1) -> np.ndarray:
    """The plain fixed baseline: start at the first allowed hour and work
    forward continuously, pausing only for hours over the 32.1 C hard stop,
    until `w_req` effective hours are delivered."""
    wbgt = np.asarray(wbgt, dtype=float)
    allowed = np.asarray(allowed, dtype=bool)
    H = len(wbgt)
    w = np.zeros(H)
    remaining = float(w_req)
    for h in range(H):
        if remaining <= 1e-9:
            break
        if not allowed[h] or wbgt[h] > hard_stop:
            continue
        take = min(1.0, remaining)
        w[h] = take
        remaining -= take
    return w


def schedule_windowed(
    wbgt_scenarios: np.ndarray,     # (S, H) or (H,) forecast scenarios
    allowed: np.ndarray,            # (H,) bool
    w_req: float,
    *,
    wbgt_point: np.ndarray,         # (H,) point forecast, for w_ref and dose
    beta: float = 0.90,
    phi: float = PHI_DEFAULT,
    wbgt_ref: float = WBGT_REF_DEFAULT,
    p: float = P_DEFAULT,
    span_cap_h: float | None = None,
    rest_allowance_h: float = REST_ALLOWANCE_H,
    max_work_blocks: int = MAX_WORK_BLOCKS,
    min_block_hours: float = MIN_BLOCK_HOURS,
    lambda_tv: float = LAMBDA_TV,
    lambda_dev: float = LAMBDA_DEV,
    lambda_rest: float = LAMBDA_REST,
    w_ref: np.ndarray | None = None,
) -> WindowedScheduleResult:
    """Outer search over contiguous on-site windows [t_in, t_out], inner CVaR LP
    per window with the anti-fragmentation and stability penalties. Picks the
    window with the lowest penalised objective plus a residual on-site-rest
    cost; falls back to the earlier-start block if no window clears the
    block-shape filters. No integer variables enter the solver.
    """
    scen = np.asarray(wbgt_scenarios, dtype=float)
    if scen.ndim == 1:
        scen = scen[None, :]
    S, H = scen.shape
    allowed = np.asarray(allowed, dtype=bool)
    wbgt_point = np.asarray(wbgt_point, dtype=float)

    if w_ref is None:
        w_ref = policy_earlier_start(wbgt_point, allowed, w_req)
    w_ref = np.asarray(w_ref, dtype=float)

    if span_cap_h is None:
        span_cap_h = w_req + rest_allowance_h
    span_min = max(1, int(np.ceil(w_req - 1e-9)))
    span_cap = int(min(H, np.floor(span_cap_h + 1e-9)))
    span_cap = max(span_min, span_cap)

    best = None                       # (score, t_in, t_out) sort key -> payload
    for length in range(span_min, span_cap + 1):
        for t_in in range(0, H - length + 1):
            t_out = t_in + length - 1
            if allowed[t_in:t_out + 1].sum() + 1e-9 < w_req:
                continue
            res = schedule_cvar(
                scen, allowed, w_req, beta=beta, phi=phi, wbgt_ref=wbgt_ref,
                p=p, window=(t_in, t_out), lambda_tv=lambda_tv,
                lambda_dev=lambda_dev, w_ref=w_ref)
            if not np.isfinite(res.obj):
                continue
            w = res.w
            runs = _work_blocks(w)
            if len(runs) > max_work_blocks:
                continue
            if any(w[a:b + 1].sum() + 1e-9 < min_block_hours for a, b in runs):
                continue
            span = _worked_span(w)
            onsite_rest = max(0.0, span - float(w.sum()))
            score = float(res.obj) + lambda_rest * onsite_rest
            key = (round(score, 9), runs[0][0], runs[-1][1])
            if best is None or key < best[0]:
                act_in, act_out = runs[0][0], runs[-1][1]
                best = (key, w, res.status, float(res.obj), act_in, act_out,
                        span, onsite_rest, len(runs))

    if best is None:
        runs = _work_blocks(w_ref)
        span = _worked_span(w_ref)
        return WindowedScheduleResult(
            w=w_ref, status="ref_fallback", obj=float("nan"),
            t_in=(runs[0][0] if runs else 0),
            t_out=(runs[-1][1] if runs else 0),
            span_hours=span,
            onsite_rest_hours=max(0.0, span - float(w_ref.sum())),
            n_blocks=len(runs), w_ref=w_ref)

    _, w, status, obj, act_in, act_out, span, onsite_rest, n_blocks = best
    return WindowedScheduleResult(
        w=w, status=status, obj=obj, t_in=act_in, t_out=act_out,
        span_hours=span, onsite_rest_hours=onsite_rest, n_blocks=n_blocks,
        w_ref=w_ref)


# ----------------------------------------------------------------- policies
def policy_windowed(wbgt_scenarios, allowed, w_req, *, wbgt_point,
                    **kw) -> np.ndarray:
    return schedule_windowed(wbgt_scenarios, allowed, w_req,
                             wbgt_point=wbgt_point, **kw).w


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
