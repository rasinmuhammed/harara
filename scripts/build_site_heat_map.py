"""
Build the downscaled surface-heat map for one site: fetch (or reuse cached)
satellite composites, run the downscaling model, write a 10 m GeoTIFF, a PNG
render for the web overlay, and a plain-language summary.

This is a climatological, advisory layer. It never touches src/wbgt.py or
the scheduler; see the module docstrings in fetch_satellite_tiles.py and
lst_downscale.py for why, and keep any new caller honest about that.

Usage:
    python scripts/build_site_heat_map.py --lat 25.2854 --lon 51.5310 \
        --radius-m 2000 --out-dir data/satellite
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
import rasterio

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.lst_downscale import compute_covariates, downscale  # noqa: E402
from scripts.fetch_satellite_tiles import MIN_CLEAR_SCENES, fetch_site  # noqa: E402

MIN_PER_PIXEL_SCENES = 1  # a 30 m pixel needs at least this many clear looks


def _read(path: str) -> np.ndarray:
    with rasterio.open(path) as src:
        return src.read(1).astype("float32")


def _zone_stats(lst_fine: np.ndarray, ndvi10: np.ndarray, ndbi10: np.ndarray) -> dict:
    veg = ndvi10 > 0.3
    bare = (ndvi10 < 0.1) & (ndbi10 > -0.1)
    out = {}
    if veg.sum() > 20:
        out["vegetated_mean_c"] = round(float(np.nanmean(lst_fine[veg])), 1)
        out["vegetated_fraction"] = round(float(veg.mean()), 3)
    if bare.sum() > 20:
        out["bare_or_built_mean_c"] = round(float(np.nanmean(lst_fine[bare])), 1)
        out["bare_or_built_fraction"] = round(float(bare.mean()), 3)
    if "vegetated_mean_c" in out and "bare_or_built_mean_c" in out:
        out["typical_difference_c"] = round(out["bare_or_built_mean_c"] - out["vegetated_mean_c"], 1)
    return out


def build(lat: float, lon: float, radius_m: float,
         out_dir: pathlib.Path = pathlib.Path("data/satellite"),
         max_scenes: int | None = None) -> dict:
    meta = fetch_site(lat, lon, radius_m, out_dir=out_dir, max_scenes=max_scenes)
    files = meta["files"]

    lst_30 = _read(files["lst_celsius_30m"])
    n_30 = _read(files["lst_n_scenes_30m"])
    red = _read(files["red"])
    nir = _read(files["nir"])
    swir = _read(files["swir"])

    cov10 = compute_covariates(red, nir, swir)
    valid_30 = n_30 >= MIN_PER_PIXEL_SCENES

    result = downscale(lst_30, cov10, valid_30=valid_30)

    site_dir = pathlib.Path(files["lst_celsius_30m"]).parent
    tif_path = site_dir / "lst_downscaled_10m.tif"
    with rasterio.open(files["red"]) as ref:
        profile = ref.profile.copy()
    profile.update(dtype="float32", nodata=np.nan, count=1)
    with rasterio.open(tif_path, "w", **profile) as dst:
        dst.write(result.lst_fine_c.astype("float32"), 1)

    png_path = site_dir / "lst_downscaled_10m.png"
    _render_png(result.lst_fine_c, png_path)

    summary = {
        **{k: v for k, v in meta.items() if k != "files"},
        "cv_rmse_c": round(result.cv_rmse_c, 2),
        "cv_n_folds": result.cv_n_folds,
        "coarse_mean_c": round(result.coarse_mean_c, 1),
        "coarse_std_c": round(result.coarse_std_c, 1),
        "fine_min_c": round(float(np.nanmin(result.lst_fine_c)), 1),
        "fine_max_c": round(float(np.nanmax(result.lst_fine_c)), 1),
        "feature_importance": {k: round(v, 3) for k, v in result.feature_importance.items()},
        "zones": _zone_stats(result.lst_fine_c, cov10["ndvi"], cov10["ndbi"]),
        "geotiff": str(tif_path),
        "png": str(png_path),
        "caveats": [
            "Climatological composite over recent summers, not a live reading.",
            "Spatial cross-validation RMSE is an internal consistency check, "
            "not a comparison against any ground sensor; no ground truth "
            "exists at this resolution for this site.",
            "This is a relative surface-heat pattern for siting and "
            "awareness. It does not feed WBGT, the forecast, or the "
            "scheduler, and it is not a substitute for the forecast plan.",
        ],
    }
    (site_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def _render_png(field: np.ndarray, path: pathlib.Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    vmin, vmax = np.nanpercentile(field, [2, 98])
    fig, ax = plt.subplots(figsize=(field.shape[1] / 100, field.shape[0] / 100), dpi=100)
    ax.imshow(field, cmap="inferno", vmin=vmin, vmax=vmax)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(path, transparent=True)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--radius-m", type=float, default=2000)
    ap.add_argument("--out-dir", type=pathlib.Path, default=pathlib.Path("data/satellite"))
    ap.add_argument("--max-scenes", type=int, default=None)
    args = ap.parse_args()
    summary = build(args.lat, args.lon, args.radius_m, out_dir=args.out_dir,
                    max_scenes=args.max_scenes)
    print(json.dumps(summary, indent=2))
