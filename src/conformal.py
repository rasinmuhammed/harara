"""
Split conformal calibration for an interval estimator.

The PROSPIE external validation (scripts/twin_external_validation.py) found
that the heat-strain particle filter's stated 95% credible interval covers
the true rectal temperature only 36-42% of the time. That is not a bug in
the physics: the two-node model's process noise describes how uncertain the
*model* is about its own state, which is a different thing from how often
the model is actually right against a real body. Conformal prediction closes
that gap without touching the physics at all: it measures, on real held-out
data, how far outside its own interval the truth actually falls, and widens
the interval by exactly that empirical amount.

This is split conformal prediction with a CQR-style (Romano, Patterson &
Candes 2019) nonconformity score, using the *symmetric* variant: a single
correction is added to both sides. That gives a marginal coverage guarantee
under exchangeability alone -- no distributional assumption on the residuals,
no refitting of the underlying estimator. The guarantee is marginal (correct
on average over the calibration population), not conditional on covariates.

This module is deliberately generic: it operates on any (lo, hi, y) triples
from an estimator that outputs a point plus an interval. It has no knowledge
of the particle filter, WBGT, or any Harara-specific type.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ConformalCorrection:
    """A symmetric interval-widening correction fit on a calibration set."""

    delta: float          # widen both lo and hi by this many units
    alpha: float           # target miscoverage (0.05 -> 95% interval)
    n_calibration: int

    def apply(self, lo, hi):
        """Return (lo, hi) widened by delta. Works on scalars or arrays."""
        return lo - self.delta, hi + self.delta

    def to_dict(self) -> dict:
        return {"delta": self.delta, "alpha": self.alpha,
                "n_calibration": self.n_calibration}

    @classmethod
    def from_dict(cls, d: dict) -> "ConformalCorrection":
        return cls(delta=float(d["delta"]), alpha=float(d["alpha"]),
                    n_calibration=int(d["n_calibration"]))


def fit_conformal(lo, hi, y, alpha: float = 0.05) -> ConformalCorrection:
    """Fit a symmetric split-conformal correction from held-out (lo, hi, y).

    lo, hi, y must be 1D arrays of equal length from points the estimator's
    interval was not assimilated on -- e.g. a different subject, in a
    leave-one-subject-out design, so the correction is validated on data the
    filter's own priors never saw. Passing points the model already fit
    would understate the true miscoverage and make the correction too small.

    Nonconformity score is the CQR form: how far the truth falls outside its
    own interval, `max(lo - y, y - hi)`. A negative score means the truth was
    inside the interval and contributes no widening. The correction is the
    ceil((n+1)(1-alpha))/n empirical quantile of that score -- the standard
    finite-sample split-conformal quantile, which gives an exact marginal
    coverage guarantee of at least 1-alpha under exchangeability of the
    calibration and test points.
    """
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    y = np.asarray(y, dtype=float)
    if not (lo.shape == hi.shape == y.shape):
        raise ValueError("lo, hi, y must have the same shape")
    ok = np.isfinite(lo) & np.isfinite(hi) & np.isfinite(y)
    lo, hi, y = lo[ok], hi[ok], y[ok]
    n = lo.size
    if n < 10:
        raise ValueError(f"conformal calibration needs >=10 finite points, got {n}")

    score = np.maximum(lo - y, y - hi)
    q_level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    delta = float(max(0.0, np.quantile(score, q_level)))
    return ConformalCorrection(delta=delta, alpha=alpha, n_calibration=n)


def coverage(lo, hi, y) -> float:
    """Empirical fraction of y inside [lo, hi], ignoring non-finite points."""
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(lo) & np.isfinite(hi) & np.isfinite(y)
    if not ok.any():
        return float("nan")
    return float(np.mean((y[ok] >= lo[ok]) & (y[ok] <= hi[ok])))
