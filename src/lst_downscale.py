"""
Downscale a Landsat surface-temperature composite (30 m) to Sentinel-2's 10 m
grid, using Sentinel-2-derived land-cover covariates.

Method: regression-kriging-style downscaling, a standard approach in the
land-surface-temperature literature (see e.g. the Landsat/Sentinel-2 fusion
work cited in docs/technical_report.md's satellite-heat section).

  1. Aggregate the 10 m covariates to Landsat's 30 m grid (an exact 3x3 mean,
     since the two grids are built to align, see src/satellite_grid.py).
  2. Fit a gradient-boosted regressor: 30 m covariates -> 30 m LST.
  3. Predict at the native 10 m covariates to get a fine-resolution LST field.
  4. Residual correction: resample the fine prediction back to 30 m, take the
     residual against the real 30 m LST, smoothly upsample that residual to
     10 m, and add it back. This keeps the output honest at the resolution we
     actually have ground data for (30 m), while letting the 10 m covariates
     carry the fine spatial pattern within each 30 m cell.

Validation is by SPATIAL block cross-validation (checkerboard blocks of the
30 m grid), never by holding out random pixels, which would leak neighbouring-
pixel information and overstate accuracy. This estimates how well the model
predicts LST in unseen parts of the same site; it is not validated against any
ground sensor, and the caller must report both facts.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import lightgbm as lgb
    _HAVE_LGB = True
except Exception:  # pragma: no cover
    _HAVE_LGB = False


def compute_covariates(red: np.ndarray, nir: np.ndarray, swir: np.ndarray) -> dict[str, np.ndarray]:
    """NDVI (vegetation), NDBI (built-up), and red reflectance as a brightness
    proxy, at whatever resolution the inputs are given."""
    eps = 1e-6
    ndvi = (nir - red) / (nir + red + eps)
    ndbi = (swir - nir) / (swir + nir + eps)
    return {"ndvi": ndvi, "ndbi": ndbi, "brightness": red}


def aggregate_3x3(fine: np.ndarray) -> np.ndarray:
    """Exact mean-pool of a 10 m array down to the aligned 30 m grid
    (height/3, width/3). Requires height and width divisible by 3."""
    h, w = fine.shape
    assert h % 3 == 0 and w % 3 == 0, "fine grid must be an exact 3x multiple of the coarse grid"
    return fine.reshape(h // 3, 3, w // 3, 3).mean(axis=(1, 3))


def upsample_bilinear(coarse: np.ndarray, fine_shape: tuple[int, int]) -> np.ndarray:
    """Smooth upsample of a coarse (30 m) residual field to the fine (10 m)
    shape, for the residual-correction step. Pure numpy bilinear, no extra
    dependency."""
    h0, w0 = coarse.shape
    h1, w1 = fine_shape
    yi = (np.arange(h1) + 0.5) * h0 / h1 - 0.5
    xi = (np.arange(w1) + 0.5) * w0 / w1 - 0.5
    yi = np.clip(yi, 0, h0 - 1)
    xi = np.clip(xi, 0, w0 - 1)
    y0 = np.floor(yi).astype(int); y1 = np.clip(y0 + 1, 0, h0 - 1)
    x0 = np.floor(xi).astype(int); x1 = np.clip(x0 + 1, 0, w0 - 1)
    wy = (yi - y0)[:, None]
    wx = (xi - x0)[None, :]
    top = coarse[y0][:, x0] * (1 - wx) + coarse[y0][:, x1] * wx
    bot = coarse[y1][:, x0] * (1 - wx) + coarse[y1][:, x1] * wx
    return top * (1 - wy) + bot * wy


def spatial_blocks(shape: tuple[int, int], n_blocks: int = 4) -> np.ndarray:
    """A checkerboard-ish assignment of each 30 m pixel to one of n_blocks
    folds, by coarse spatial tiles rather than individual pixels, so a fold
    boundary is never adjacent to itself on both sides."""
    h, w = shape
    tile = max(2, min(h, w) // 6)
    block_rows = (np.arange(h) // tile)
    block_cols = (np.arange(w) // tile)
    grid = (block_rows[:, None] + block_cols[None, :]) % n_blocks
    return grid


@dataclass
class DownscaleResult:
    lst_fine_c: np.ndarray          # (height10, width10) downscaled LST, celsius
    cv_rmse_c: float                # spatial-CV RMSE at the 30 m grid, celsius
    cv_n_folds: int
    coarse_mean_c: float
    coarse_std_c: float
    feature_importance: dict[str, float]


def downscale(
    lst_30_c: np.ndarray,
    covariates_10: dict[str, np.ndarray],
    valid_30: np.ndarray | None = None,
    n_folds: int = 4,
    seed: int = 0,
) -> DownscaleResult:
    """
    lst_30_c: (h30, w30) Landsat LST composite, celsius, NaN where unknown.
    covariates_10: dict of (h30*3, w30*3) arrays (ndvi, ndbi, brightness),
        aligned so each 3x3 block corresponds to one lst_30_c pixel.
    valid_30: optional bool mask of usable lst_30_c pixels (else NaN-derived).
    """
    if not _HAVE_LGB:
        raise RuntimeError("lightgbm is required for downscale()")

    h30, w30 = lst_30_c.shape
    names = sorted(covariates_10)
    cov_30 = {k: aggregate_3x3(v) for k, v in covariates_10.items()}

    valid = np.isfinite(lst_30_c) if valid_30 is None else (valid_30 & np.isfinite(lst_30_c))
    for v in cov_30.values():
        valid &= np.isfinite(v)
    if valid.sum() < 30:
        raise RuntimeError(f"only {int(valid.sum())} valid 30 m training pixels, need at least 30")

    X30 = np.stack([cov_30[k][valid] for k in names], axis=1)
    y30 = lst_30_c[valid]
    folds = spatial_blocks((h30, w30), n_folds)[valid]

    # spatial block cross-validation, honest out-of-sample RMSE
    residuals = []
    for f in np.unique(folds):
        tr, te = folds != f, folds == f
        if tr.sum() < 10 or te.sum() < 1:
            continue
        model = lgb.LGBMRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            min_child_samples=5, random_state=seed, verbose=-1,
        )
        model.fit(X30[tr], y30[tr])
        pred = model.predict(X30[te])
        residuals.append(pred - y30[te])
    residuals = np.concatenate(residuals) if residuals else np.array([0.0])
    cv_rmse = float(np.sqrt(np.mean(residuals ** 2)))
    cv_n_folds = int(len(np.unique(folds)))

    # final model on all valid data, for the actual prediction
    final = lgb.LGBMRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        min_child_samples=5, random_state=seed, verbose=-1,
    )
    final.fit(X30, y30)
    importance = dict(zip(names, (final.feature_importances_ / max(1, final.feature_importances_.sum())).tolist()))

    # predict at native 10 m covariates
    h10, w10 = next(iter(covariates_10.values())).shape
    X10 = np.stack([covariates_10[k].reshape(-1) for k in names], axis=1)
    pred_10 = final.predict(X10).reshape(h10, w10)

    # residual correction: keep the coarse truth where we have it
    pred_30_from_fine = aggregate_3x3(pred_10)
    resid_30 = np.where(valid, lst_30_c - pred_30_from_fine, 0.0)
    resid_10 = upsample_bilinear(resid_30, (h10, w10))
    lst_fine = pred_10 + resid_10

    return DownscaleResult(
        lst_fine_c=lst_fine,
        cv_rmse_c=cv_rmse,
        cv_n_folds=cv_n_folds,
        coarse_mean_c=float(np.nanmean(lst_30_c[valid])),
        coarse_std_c=float(np.nanstd(lst_30_c[valid])),
        feature_importance=importance,
    )
