"""
Unit tests for the satellite surface-heat pipeline. No network: masking logic
and the downscaling model are tested on synthetic arrays with a known
structure, so we can check the model recovers the right DIRECTION of effect
(vegetated patches read cooler than bare patches) without needing live data
in CI.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.lst_downscale import (
    aggregate_3x3, compute_covariates, downscale, spatial_blocks,
    upsample_bilinear,
)
from src.satellite_grid import Grid30, bbox_from_site, site_key
from scripts.fetch_satellite_tiles import (
    LANDSAT_CLEAR_BIT, LANDSAT_FILL_BIT, S2_GOOD_SCL, _median_composite,
)


def test_bbox_from_site_reasonable_size():
    lat, lon = 25.2854, 51.5310
    minlon, minlat, maxlon, maxlat = bbox_from_site(lat, lon, 2000)
    assert minlon < lon < maxlon
    assert minlat < lat < maxlat
    # roughly a 4 km box (2 km radius) -> about 0.036 deg at this latitude
    assert 0.02 < (maxlon - minlon) < 0.06
    assert 0.02 < (maxlat - minlat) < 0.06


def test_site_key_stable_and_snaps_nearby_sites_together():
    k1 = site_key(25.2854, 51.5310, 2000)
    k2 = site_key(25.2861, 51.5308, 2000)  # a few hundred metres away
    assert k1 == k2
    k3 = site_key(25.40, 51.60, 2000)  # a different part of the city
    assert k1 != k3


def test_grid30_synthetic_10m_is_exact_3x_subdivision():
    g = Grid30.synthetic(width30=8, height30=6, pixel=30.0)
    assert g.width10 == 24 and g.height10 == 18
    assert g.transform10[0] == pytest.approx(10.0)


def test_landsat_qa_bits():
    # Clear (bit 6) and not fill (bit 0)
    clear_pixel = 1 << 6
    assert (clear_pixel & LANDSAT_CLEAR_BIT) != 0
    assert (clear_pixel & LANDSAT_FILL_BIT) == 0
    cloudy_pixel = (1 << 3)  # cloud bit, not clear
    assert (cloudy_pixel & LANDSAT_CLEAR_BIT) == 0


def test_s2_good_scl_excludes_cloud_and_shadow():
    assert 4 in S2_GOOD_SCL and 5 in S2_GOOD_SCL  # vegetation, bare soil
    for bad in (3, 8, 9, 10, 11, 0, 1):  # shadow, cloud x2, cirrus, snow, nodata, saturated
        assert bad not in S2_GOOD_SCL


def test_median_composite_ignores_masked_pixels():
    a = np.array([[10.0, 20.0], [30.0, 40.0]])
    b = np.array([[100.0, 20.0], [30.0, 40.0]])  # pixel (0,0) is an outlier/cloud here
    mask_a = np.array([[True, True], [True, True]])
    mask_b = np.array([[False, True], [True, True]])  # mask out the outlier
    comp, n = _median_composite([a, b], [mask_a, mask_b])
    assert comp[0, 0] == pytest.approx(10.0)  # only scene a counted
    assert n[0, 0] == 1
    assert n[1, 1] == 2


def test_compute_covariates_ndvi_range():
    red = np.array([0.1, 0.3])
    nir = np.array([0.5, 0.32])
    swir = np.array([0.2, 0.35])
    cov = compute_covariates(red, nir, swir)
    assert -1.0 <= cov["ndvi"][0] <= 1.0
    assert cov["ndvi"][0] > cov["ndvi"][1]  # first pixel is more vegetated


def test_aggregate_3x3_is_exact_mean():
    fine = np.arange(36, dtype="float32").reshape(6, 6)
    coarse = aggregate_3x3(fine)
    assert coarse.shape == (2, 2)
    assert coarse[0, 0] == pytest.approx(fine[:3, :3].mean())


def test_upsample_bilinear_preserves_coarse_mean_roughly():
    coarse = np.array([[10.0, 20.0], [30.0, 40.0]])
    fine = upsample_bilinear(coarse, (30, 30))
    assert fine.mean() == pytest.approx(coarse.mean(), abs=1.5)


def test_spatial_blocks_produces_requested_fold_count_and_spatial_coherence():
    grid = spatial_blocks((24, 24), n_blocks=4)
    assert set(np.unique(grid)) <= {0, 1, 2, 3}
    # a fold should occupy contiguous tiles, not be scattered pixel-by-pixel
    assert (grid[0, 0] == grid[1, 1]) or (grid == grid[0, 0]).sum() > 4


def _synthetic_site(h30=12, w30=12, seed=0):
    """Checkerboard land cover: alternating 30 m blocks are mostly vegetated
    or mostly bare, with the block's LST a linear function of its mean NDVI
    plus noise, exactly the structure the downscaler should recover."""
    rng = np.random.default_rng(seed)
    h10, w10 = h30 * 3, w30 * 3

    block_is_green = (np.add.outer(np.arange(h30), np.arange(w30)) % 2 == 0)
    ndvi10 = np.zeros((h10, w10))
    for i in range(h30):
        for j in range(w30):
            base = 0.6 if block_is_green[i, j] else 0.05
            ndvi10[i*3:i*3+3, j*3:j*3+3] = base + rng.normal(0, 0.03, (3, 3))
    ndvi10 = np.clip(ndvi10, -0.2, 0.9)

    # derive red/nir/swir consistent with that NDVI (not physically exact,
    # just enough to drive compute_covariates -> a coherent ndvi/ndbi signal)
    nir = 0.3 + 0.2 * ndvi10
    red = nir * (1 - ndvi10) / (1 + ndvi10 + 1e-6)
    swir = red * (1.2 - 0.3 * ndvi10)

    ndvi30 = aggregate_3x3(ndvi10)
    lst30 = 45.0 - 15.0 * ndvi30 + rng.normal(0, 0.5, (h30, w30))

    cov10 = compute_covariates(red, nir, swir)
    return lst30, cov10, block_is_green


def test_downscale_recovers_cooler_pattern_over_vegetated_subpixels():
    lst30, cov10, block_is_green = _synthetic_site()
    result = downscale(lst30, cov10, n_folds=4, seed=0)

    assert np.isfinite(result.lst_fine_c).all()
    assert result.cv_n_folds >= 2
    # the model should be predictive: CV RMSE well below the raw scene spread
    assert result.cv_rmse_c < result.coarse_std_c

    # within blocks, the fine prediction should be cooler where the local
    # 10 m NDVI is higher (vegetated) than where it is lower (bare), even
    # though training only ever saw 30 m block averages
    ndvi10 = cov10["ndvi"]
    veg_mask = ndvi10 > 0.4
    bare_mask = ndvi10 < 0.2
    assert result.lst_fine_c[veg_mask].mean() < result.lst_fine_c[bare_mask].mean()

    assert "ndvi" in result.feature_importance
    assert abs(sum(result.feature_importance.values()) - 1.0) < 1e-6


def test_downscale_raises_on_too_few_valid_pixels():
    lst30 = np.full((4, 4), np.nan)
    lst30[0, 0] = 40.0
    cov10 = {
        "ndvi": np.zeros((12, 12)), "ndbi": np.zeros((12, 12)), "brightness": np.zeros((12, 12)),
    }
    with pytest.raises(RuntimeError):
        downscale(lst30, cov10)
