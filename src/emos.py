"""
EMOS / Nonhomogeneous Gaussian Regression for the GEFS reforecast.

For a target (here WBGT derived from the ensemble members) we model

    y | ensemble  ~  Normal(mu, sigma^2)
    mu     = a + b * ens_mean
    sigma^2 = c + d * ens_var

(Gneiting, Raftery, Westveld and Goldman, 2005). Parameters are fit by
minimising the mean continuous ranked probability score, which for a
Gaussian has a closed form. A separate (a, b, c, d) is fit per
(lead, calendar month) cell; cells with too few training instances pool
to month +/- 1, then to a lead-only fit, and are flagged.

The caller is responsible for passing only data that precedes the scored
period. The walk-forward loop is in scripts/gefs_calibration.py; this
module fits what it is given.

Interface used by src.forecast_uncertainty.GEFSEnsembleModel:
    m = EMOS().fit(train_df)                      # cols: lead_h, month, ens_mean, ens_var, obs
    mu, sigma = m.predict(ens_mean, ens_var, lead_h, month)
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.special import erf

MIN_CELL = 150          # training instances below which a cell is pooled
_SQRT_PI = np.sqrt(np.pi)


def _phi(z):
    return np.exp(-0.5 * z * z) / np.sqrt(2 * np.pi)


def _Phi(z):
    return 0.5 * (1.0 + erf(z / np.sqrt(2)))


def gaussian_crps(mu, sigma, y):
    """Closed-form CRPS of N(mu, sigma) at observation y (elementwise)."""
    sigma = np.maximum(sigma, 1e-6)
    z = (np.asarray(y, float) - mu) / sigma
    return sigma * (z * (2 * _Phi(z) - 1) + 2 * _phi(z) - 1.0 / _SQRT_PI)


def _unpack(theta):
    # a free; b,c,d kept positive via softplus so the optimiser is unconstrained
    a = theta[0]
    b = np.log1p(np.exp(theta[1]))
    c = np.log1p(np.exp(theta[2]))
    d = np.log1p(np.exp(theta[3]))
    return a, b, c, d


def _fit_cell(ens_mean, ens_var, obs):
    m = np.asarray(ens_mean, float)
    v = np.maximum(np.asarray(ens_var, float), 0.0)
    y = np.asarray(obs, float)
    ok = np.isfinite(m) & np.isfinite(v) & np.isfinite(y)
    m, v, y = m[ok], v[ok], y[ok]
    if len(y) < 20:
        return None

    def nll(theta):
        a, b, c, d = _unpack(theta)
        mu = a + b * m
        sig = np.sqrt(c + d * v)
        return float(np.mean(gaussian_crps(mu, sig, y)))

    # start from OLS bias + residual-variance-based spread
    b0 = np.cov(m, y)[0, 1] / max(np.var(m), 1e-6)
    a0 = float(np.mean(y) - b0 * np.mean(m))
    resid_var = float(np.var(y - (a0 + b0 * m)))
    theta0 = np.array([a0, np.log(np.expm1(max(b0, 0.1))),
                       np.log(np.expm1(max(resid_var, 0.1))), 0.0])
    res = minimize(nll, theta0, method="Nelder-Mead",
                   options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 4000})
    a, b, c, d = _unpack(res.x)
    return dict(a=float(a), b=float(b), c=float(c), d=float(d),
                n=int(len(y)), crps=float(res.fun))


class EMOS:
    def __init__(self, min_cell: int = MIN_CELL):
        self.min_cell = min_cell
        self.cells: dict[tuple[int, int], dict] = {}     # (lead, month) -> params
        self.lead_only: dict[int, dict] = {}
        self.pooled: set[tuple[int, int]] = set()

    # - fit -----------------------------------------------------------------
    def fit(self, df):
        """df columns: lead_h, month, ens_mean, ens_var, obs."""
        leads = sorted(df["lead_h"].unique())
        months = sorted(df["month"].unique())
        for L in leads:
            dl = df[df["lead_h"] == L]
            fit_l = _fit_cell(dl["ens_mean"], dl["ens_var"], dl["obs"])
            if fit_l:
                self.lead_only[L] = fit_l
            for M in months:
                cell = df[(df["lead_h"] == L) & (df["month"] == M)]
                if len(cell) >= self.min_cell:
                    f = _fit_cell(cell["ens_mean"], cell["ens_var"], cell["obs"])
                    if f:
                        self.cells[(L, M)] = f
                        continue
                # pool to month +/- 1
                near = df[(df["lead_h"] == L) & (df["month"].between(M - 1, M + 1))]
                self.pooled.add((L, M))
                if len(near) >= self.min_cell:
                    f = _fit_cell(near["ens_mean"], near["ens_var"], near["obs"])
                    if f:
                        self.cells[(L, M)] = f
                        continue
                if L in self.lead_only:                 # last resort: lead only
                    self.cells[(L, M)] = self.lead_only[L]
        return self

    # - predict -----------------------------------------------------------
    def predict(self, ens_mean, ens_var, lead_h, month):
        p = self.cells.get((int(lead_h), int(month))) or self.lead_only.get(int(lead_h))
        if p is None:                                    # untrained: identity + raw spread
            mu = np.asarray(ens_mean, float)
            sigma = np.sqrt(np.maximum(np.asarray(ens_var, float), 1e-4))
            return mu, sigma
        m = np.asarray(ens_mean, float)
        v = np.maximum(np.asarray(ens_var, float), 0.0)
        return p["a"] + p["b"] * m, np.sqrt(p["c"] + p["d"] * v)

    def is_pooled(self, lead_h, month) -> bool:
        return (int(lead_h), int(month)) in self.pooled

    # - serialise -------------------------------------------------------
    def to_dict(self):
        return {"min_cell": int(self.min_cell),
                "cells": {f"{int(k[0])}_{int(k[1])}": v for k, v in self.cells.items()},
                "lead_only": {str(int(k)): v for k, v in self.lead_only.items()},
                "pooled": [[int(a), int(b)] for a, b in self.pooled]}

    @classmethod
    def from_dict(cls, d):
        o = cls(d["min_cell"])
        o.cells = {tuple(int(x) for x in k.split("_")): v
                   for k, v in d["cells"].items()}
        o.lead_only = {int(k): v for k, v in d["lead_only"].items()}
        o.pooled = {tuple(x) for x in d["pooled"]}
        return o
