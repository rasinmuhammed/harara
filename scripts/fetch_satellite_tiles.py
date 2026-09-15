"""
Fetch and composite free satellite imagery for the site surface-heat layer.

Sources: Microsoft Planetary Computer's public STAC API
(https://planetarycomputer.microsoft.com/api/stac/v1), no account or key
needed for search and read, asset URLs are signed on the fly with the
`planetary_computer` package.

  - landsat-c2-l2 (Landsat 8/9 Collection 2 Level 2): the `lwir11` asset is
    calibrated surface temperature in Kelvin (USGS product), not top-of-
    atmosphere brightness. Scale and offset are read from the asset's own
    `raster:bands` metadata, not hardcoded, so a product revision cannot
    silently corrupt the conversion. Public domain (USGS).
  - sentinel-2-l2a (Sentinel-2 Level 2A): 10 m visible/NIR bands (B04, B08)
    and the 20 m SWIR band (B11) used for a built-up index, reprojected onto
    the Landsat-aligned 10 m grid. Free under the Copernicus licence,
    attribution required.

This produces a CLIMATOLOGICAL composite (the median of several cloud-free
summer scenes over 2 to 3 years), not a live snapshot. A single satellite
pass is one moment in time; averaging several removes residual cloud noise
and any one day's anomaly. That framing must survive into every doc and UI
surface this touches: this is a typical surface-heat pattern, not today's
forecast, and it never feeds src/wbgt.py or the scheduler.

Per-pixel cloud masking (not just the scene-level cloud-cover percentage) is
applied before compositing: Landsat's QA_PIXEL "Clear" bit, and Sentinel-2's
Scene Classification Layer (SCL), because a low scene-average cloud cover
does not guarantee the specific site pixel was clear on that date.

Usage:
    python scripts/fetch_satellite_tiles.py --lat 25.2854 --lon 51.5310 \
        --radius-m 2000 --out-dir data/satellite
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import warnings

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.satellite_grid import Grid30, bbox_from_site, site_key  # noqa: E402

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
MAX_SCENE_CLOUD = 20.0  # percent, scene-level pre-filter
MIN_CLEAR_SCENES = 2
LANDSAT_CLEAR_BIT = 1 << 6  # QA_PIXEL bit 6 = "Clear" (USGS Collection 2)
LANDSAT_FILL_BIT = 1 << 0
S2_GOOD_SCL = {2, 4, 5, 6, 7}  # dark area, vegetation, bare soil, water, unclassified
# excluded: 0/1 nodata-saturated, 3 cloud shadow, 8/9 cloud, 10 cirrus, 11 snow


def _catalog():
    import planetary_computer as pc
    import pystac_client

    return pystac_client.Client.open(STAC_URL, modifier=pc.sign_inplace)


def _search(catalog, collection: str, bbox, date_ranges: list[str], max_cloud: float):
    items = []
    for dr in date_ranges:
        found = catalog.search(
            collections=[collection], bbox=bbox, datetime=dr,
            query={"eo:cloud_cover": {"lt": max_cloud}},
            limit=50,
        ).items()
        items.extend(found)
    return items


def _reproject_to_shape(href: str, crs, transform, shape: tuple[int, int],
                        band_index: int = 1, resampling=Resampling.bilinear,
                        nodata=None) -> np.ndarray:
    with rasterio.open(href) as src:
        dst = np.full(shape, np.nan, dtype="float32")
        reproject(
            source=rasterio.band(src, band_index),
            destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=transform, dst_crs=crs,
            resampling=resampling, src_nodata=nodata, dst_nodata=np.nan,
        )
        return dst


def _reproject_to_grid(href: str, grid: Grid30, band_index: int = 1,
                       resampling=Resampling.bilinear, nodata=None) -> np.ndarray:
    """Onto the 10 m grid, for Sentinel-2's native-fine bands."""
    return _reproject_to_shape(href, grid.crs, grid.transform10,
                               (grid.height10, grid.width10),
                               band_index, resampling, nodata)


def _landsat_lst_and_mask(item, grid: Grid30) -> tuple[np.ndarray, np.ndarray]:
    """Returns (surface_temp_celsius, clear_mask), both at Landsat's OWN
    native 30 m grid. This must stay at native resolution: it is the ground
    truth the downscaling model trains against, and resampling it to 10 m
    here would blur away the very signal the model is supposed to recover,
    leaving nothing genuine to train on."""
    lwir = item.assets["lwir11"]
    bands_meta = lwir.extra_fields.get("raster:bands", [{}])[0]
    scale = bands_meta.get("scale", 0.00341802)
    offset = bands_meta.get("offset", 149.0)

    shape30 = (grid.height30, grid.width30)
    dn = _reproject_to_shape(lwir.href, grid.crs, grid.transform30, shape30,
                             resampling=Resampling.bilinear)
    celsius = dn * scale + offset - 273.15

    qa = _reproject_to_shape(item.assets["qa"].href, grid.crs, grid.transform30, shape30,
                             resampling=Resampling.nearest)
    qa_int = np.nan_to_num(qa, nan=0).astype("uint16")
    clear = ((qa_int & LANDSAT_CLEAR_BIT) != 0) & ((qa_int & LANDSAT_FILL_BIT) == 0)
    clear &= np.isfinite(celsius) & (celsius > -30) & (celsius < 90)
    return celsius, clear


def _s2_bands_and_mask(item, grid: Grid30) -> tuple[dict[str, np.ndarray], np.ndarray]:
    red = _reproject_to_grid(item.assets["B04"].href, grid, resampling=Resampling.bilinear) / 10000.0
    nir = _reproject_to_grid(item.assets["B08"].href, grid, resampling=Resampling.bilinear) / 10000.0
    swir = _reproject_to_grid(item.assets["B11"].href, grid, resampling=Resampling.bilinear) / 10000.0
    scl = _reproject_to_grid(item.assets["SCL"].href, grid, resampling=Resampling.nearest)
    scl_int = np.nan_to_num(scl, nan=0).astype("uint8")
    clear = np.isin(scl_int, list(S2_GOOD_SCL))
    clear &= np.isfinite(red) & np.isfinite(nir) & np.isfinite(swir)
    return {"red": red, "nir": nir, "swir": swir}, clear


def _median_composite(stack: list[np.ndarray], masks: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel median over the scenes where that pixel was clear.
    Returns (composite, n_clear_scenes_per_pixel)."""
    arr = np.stack(stack)
    mask = np.stack(masks)
    masked = np.where(mask, arr, np.nan)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        # a pixel with zero clear scenes across the whole stack (e.g. a
        # persistently masked border) is EXPECTED to produce NaN here; the
        # caller filters those out via the n_clear / valid_30 mask, so the
        # "All-NaN slice" warning is noise, not a bug.
        warnings.filterwarnings("ignore", message="All-NaN slice encountered")
        composite = np.nanmedian(masked, axis=0)
    n_clear = mask.sum(axis=0)
    return composite, n_clear


def fetch_site(lat: float, lon: float, radius_m: float, *,
              years_back: int = 3, months=(5, 6, 7, 8, 9),
              out_dir: pathlib.Path = pathlib.Path("data/satellite"),
              max_scenes: int | None = None) -> dict:
    key = site_key(lat, lon, radius_m)
    site_dir = out_dir / key
    meta_path = site_dir / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())

    site_dir.mkdir(parents=True, exist_ok=True)
    bbox = bbox_from_site(lat, lon, radius_m)

    year_now = dt.date.today().year
    date_ranges = [
        f"{year_now - y}-{months[0]:02d}-01/{year_now - y}-{months[-1]:02d}-28"
        for y in range(years_back)
    ]

    catalog = _catalog()
    landsat_items = _search(catalog, "landsat-c2-l2", bbox, date_ranges, MAX_SCENE_CLOUD)
    s2_items = _search(catalog, "sentinel-2-l2a", bbox, date_ranges, MAX_SCENE_CLOUD)
    if max_scenes:
        # sort clearest-first so a capped run (fast iteration / tests) still
        # uses the best available scenes, not an arbitrary prefix
        landsat_items = sorted(landsat_items, key=lambda it: it.properties.get("eo:cloud_cover", 100))[:max_scenes]
        s2_items = sorted(s2_items, key=lambda it: it.properties.get("eo:cloud_cover", 100))[:max_scenes]
    if not landsat_items:
        raise RuntimeError(f"no clear Landsat scenes for site {key} in the last {years_back} summers")
    if not s2_items:
        raise RuntimeError(f"no clear Sentinel-2 scenes for site {key} in the last {years_back} summers")

    grid = Grid30.from_landsat_item(landsat_items[0], bbox)

    lst_stack, lst_masks, lst_dates = [], [], []
    for it in landsat_items:
        try:
            c, m = _landsat_lst_and_mask(it, grid)
        except Exception:
            continue
        if m.mean() < 0.3:  # mostly cloud over this site despite the scene-level filter
            continue
        lst_stack.append(c); lst_masks.append(m); lst_dates.append(str(it.datetime))
    if len(lst_stack) < MIN_CLEAR_SCENES:
        raise RuntimeError(f"only {len(lst_stack)} usable Landsat scenes for site {key}, need {MIN_CLEAR_SCENES}")
    lst_composite, lst_n = _median_composite(lst_stack, lst_masks)

    red_stack, nir_stack, swir_stack, s2_masks, s2_dates = [], [], [], [], []
    for it in s2_items:
        try:
            bands, m = _s2_bands_and_mask(it, grid)
        except Exception:
            continue
        if m.mean() < 0.3:
            continue
        red_stack.append(bands["red"]); nir_stack.append(bands["nir"]); swir_stack.append(bands["swir"])
        s2_masks.append(m); s2_dates.append(str(it.datetime))
    if len(red_stack) < MIN_CLEAR_SCENES:
        raise RuntimeError(f"only {len(red_stack)} usable Sentinel-2 scenes for site {key}, need {MIN_CLEAR_SCENES}")
    red_c, _ = _median_composite(red_stack, s2_masks)
    nir_c, _ = _median_composite(nir_stack, s2_masks)
    swir_c, s2_n = _median_composite(swir_stack, s2_masks)

    profile30 = dict(driver="GTiff", height=grid.height30, width=grid.width30, count=1,
                     dtype="float32", crs=grid.crs, transform=grid.transform30, nodata=np.nan)
    profile30_u8 = {**profile30, "dtype": "uint8", "nodata": 0}
    profile10 = dict(driver="GTiff", height=grid.height10, width=grid.width10, count=1,
                     dtype="float32", crs=grid.crs, transform=grid.transform10, nodata=np.nan)
    profile10_u8 = {**profile10, "dtype": "uint8", "nodata": 0}

    def _write(name, arr, prof):
        path = site_dir / name
        with rasterio.open(path, "w", **prof) as dst:
            dst.write(arr.astype(prof["dtype"]), 1)
        return str(path)

    files = {
        # native 30 m Landsat grid: the actual ground truth to train against
        "lst_celsius_30m": _write("lst_celsius_30m.tif", lst_composite, profile30),
        "lst_n_scenes_30m": _write("lst_n_scenes_30m.tif", lst_n, profile30_u8),
        # native 10 m Sentinel-2 grid: the fine covariates
        "red": _write("s2_red_10m.tif", red_c, profile10),
        "nir": _write("s2_nir_10m.tif", nir_c, profile10),
        "swir": _write("s2_swir_10m.tif", swir_c, profile10),
        "s2_n_scenes": _write("s2_n_scenes_10m.tif", s2_n, profile10_u8),
    }

    meta = {
        "site_key": key, "lat": lat, "lon": lon, "radius_m": radius_m,
        "bbox": bbox, "crs": str(grid.crs),
        "grid30": {"width": grid.width30, "height": grid.height30},
        "landsat_scenes_used": len(lst_stack), "landsat_dates": lst_dates,
        "sentinel2_scenes_used": len(red_stack), "sentinel2_dates": s2_dates,
        "years_back": years_back, "months": list(months),
        "note": "Climatological composite (median of cloud-masked scenes), not a live snapshot.",
        "attribution": "Landsat data courtesy of the U.S. Geological Survey (public domain); "
                       "contains modified Copernicus Sentinel data, processed by ESA/Copernicus.",
        "files": files,
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--radius-m", type=float, default=2000)
    ap.add_argument("--years-back", type=int, default=3)
    ap.add_argument("--max-scenes", type=int, default=None,
                    help="cap scenes per collection, clearest first; for fast "
                         "iteration, not for the shipped precompute")
    ap.add_argument("--out-dir", type=pathlib.Path, default=pathlib.Path("data/satellite"))
    args = ap.parse_args()
    meta = fetch_site(args.lat, args.lon, args.radius_m,
                      years_back=args.years_back, out_dir=args.out_dir,
                      max_scenes=args.max_scenes)
    print(json.dumps(meta, indent=2))
