"""
Worker-time constraints on the scheduler (docs/scheduler_worker_time_plan.md):
the windowed optimiser is span-capped, block-limited, and never keeps a crew on
site longer, resting in the heat longer, or in more pieces than the calendar
rule. The plain CVaR LP is unchanged when the new keyword args are absent.
"""

import numpy as np

from src.scheduler import (
    _work_blocks, _worked_span, cumulative_exposure, policy_calendar,
    policy_earlier_start, schedule_cvar, schedule_windowed,
)

HOURS = np.arange(5, 20).astype(float)          # local 05:00-19:00, H = 15
H = len(HOURS)


def hot_day(peak: float = 34.0, base: float = 26.0) -> np.ndarray:
    """Smooth WBGT bump peaking at 14:00."""
    return base + (peak - base) * np.exp(-((HOURS - 14.0) ** 2) / (2 * 3.0 ** 2))


def test_schedule_cvar_unchanged_without_new_kwargs():
    rng = np.random.default_rng(0)
    scen = 30.0 + rng.normal(0.0, 1.5, size=(20, 12))
    allowed = np.ones(12, dtype=bool)
    a = schedule_cvar(scen, allowed, 6.0, beta=0.9)
    b = schedule_cvar(scen, allowed, 6.0, beta=0.9,
                      window=None, lambda_tv=0.0, lambda_dev=0.0, w_ref=None)
    assert np.allclose(a.w, b.w)
    assert abs(a.obj - b.obj) < 1e-9


def test_cumulative_exposure_value():
    w = np.array([1.0, 0.5, 0.0])
    wbgt = np.array([30.0, 34.0, 40.0])          # excess over 28: 2, 6, 12
    assert cumulative_exposure(w, wbgt, wbgt_ref=28.0) == 1.0 * 2 + 0.5 * 6


def test_policy_earlier_start_single_block_and_hard_stop():
    allowed = np.ones(H, dtype=bool)

    w = policy_earlier_start(np.full(H, 29.0), allowed, 8.0)
    assert w.sum() == 8.0
    assert w[0] == 1.0
    assert len(_work_blocks(w)) == 1

    hot = hot_day(peak=36.0)
    w2 = policy_earlier_start(hot, allowed, 9.0)
    assert w2.sum() == 9.0
    assert all(w2[i] == 0.0 for i in range(H) if hot[i] > 32.1)


def test_windowed_respects_span_cap_and_blocks():
    wbgt = hot_day()
    res = schedule_windowed(wbgt[None, :], np.ones(H, dtype=bool), 9.0,
                            wbgt_point=wbgt)
    assert res.w.sum() >= 9.0 - 1e-6                    # work delivered
    assert res.span_hours <= 9.0 + 2.0                  # w_req + rest_allowance
    assert res.n_blocks <= 2
    for a, b in _work_blocks(res.w):
        assert res.w[a:b + 1].sum() >= 1.5 - 1e-6       # min_block_hours


def test_windowed_never_worse_for_the_worker_than_calendar():
    wbgt = hot_day()
    allowed = np.ones(H, dtype=bool)
    res = schedule_windowed(wbgt[None, :], allowed, 9.0, wbgt_point=wbgt)

    w_cal = policy_calendar(HOURS, allowed)
    cal_span = _worked_span(w_cal)
    cal_rest = cal_span - float(w_cal.sum())
    cal_blocks = len(_work_blocks(w_cal))

    assert res.span_hours <= cal_span
    assert res.onsite_rest_hours <= cal_rest + 1e-6
    assert res.n_blocks <= cal_blocks


def test_zero_rest_allowance_forces_minimal_span():
    wbgt = hot_day()
    res = schedule_windowed(wbgt[None, :], np.ones(H, dtype=bool), 8.0,
                            wbgt_point=wbgt, rest_allowance_h=0.0)
    assert res.span_hours <= 8


def test_windowed_falls_back_to_earlier_start_when_no_window_clears_filters():
    wbgt = hot_day()
    allowed = np.ones(H, dtype=bool)
    res = schedule_windowed(wbgt[None, :], allowed, 9.0, wbgt_point=wbgt,
                            min_block_hours=99.0)
    assert res.status == "ref_fallback"
    assert np.allclose(res.w, policy_earlier_start(wbgt, allowed, 9.0))
