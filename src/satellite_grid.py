"""
Grid utilities for the satellite surface-heat pipeline.

Everything downstream (fetch, masking, downscaling) works in one canonical
grid per site: Landsat's native 30 m grid and an exact 10 m subdivision of it
(each 30 m cell is exactly nine 10 m cells), both in Landsat's own UTM CRS.
Sentinel-2 bands are reprojected onto that 10 m grid rather than the other
way around, so "aggregate 10 m to 30 m" is an exact 3x3 block mean with no
resampling error, and "predict at 10 m" and "add the coarse residual back"
line up pixel-for-pixel.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine, from_bounds
from rasterio.warp import calculate_default_transform


def bbox_from_site(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """(minlon, minlat, maxlon, maxlat) for a square of the given radius
    around (lat, lon), in degrees. Good enough at this scale (a few km); we
    do not need geodesic precision, only a query window."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.1, np.cos(np.radians(lat))))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def site_key(lat: float, lon: float, radius_m: float) -> str:
    """Cache key: snap to ~1 km / 250 m so nearby sites share a fetch,
    matching the project's existing grid-snap convention elsewhere."""
    glat = round(lat, 2)
    glon = round(lon, 2)
    gr = round(radius_m / 250.0) * 250
    raw = f"{glat:.2f},{glon:.2f},{gr}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


@dataclass
class Grid30:
    """A Landsat-aligned 30 m grid over the site bbox, and its exact 10 m
    subdivision (each 30 m cell = one 3x3 block of 10 m cells)."""

    crs: CRS
    transform30: Affine
    width30: int
    height30: int

    @property
    def transform10(self) -> Affine:
        return self.transform30 @ Affine.scale(1 / 3, 1 / 3)

    @property
    def width10(self) -> int:
        return self.width30 * 3

    @property
    def height10(self) -> int:
        return self.height30 * 3

    @classmethod
    def from_landsat_item(cls, item, bbox_wgs84) -> "Grid30":
        """Build the 30 m grid from a Landsat item's own CRS, aligned to that
        item's pixel grid so no resampling is needed for the Landsat read
        itself, clipped to the query bbox."""
        asset = item.assets.get("lwir11") or item.assets["red"]
        with rasterio.open(asset.href) as src:
            crs = src.crs
            # bbox -> this CRS
            from rasterio.warp import transform_bounds
            left, bottom, right, top = transform_bounds("EPSG:4326", crs, *bbox_wgs84)
            # snap to the source's own pixel grid so pixels line up exactly
            inv = ~src.transform
            c0, r0 = inv * (left, top)
            c1, r1 = inv * (right, bottom)
            col0, row0 = int(np.floor(min(c0, c1))), int(np.floor(min(r0, r1)))
            col1, row1 = int(np.ceil(max(c0, c1))), int(np.ceil(max(r0, r1)))
            width = max(4, col1 - col0)
            height = max(4, row1 - row0)
            transform = src.transform * Affine.translation(col0, row0)
        return cls(crs=crs, transform30=transform, width30=width, height30=height)

    @classmethod
    def synthetic(cls, width30: int = 12, height30: int = 12, pixel: float = 30.0) -> "Grid30":
        """A local, no-network grid for unit tests: arbitrary UTM-like CRS,
        origin at (0, height*pixel), north-up."""
        transform = from_bounds(0, 0, width30 * pixel, height30 * pixel, width30, height30)
        return cls(crs=CRS.from_epsg(32639), transform30=transform, width30=width30, height30=height30)
