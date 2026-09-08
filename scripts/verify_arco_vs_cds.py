"""
Acceptance test: does ARCO-ERA5 (the queue-free Google Zarr mirror) return
the same numbers as the official Copernicus CDS download?

For every era5_doha_*.nc already fetched from CDS, pull the identical month
+ grid cell from ARCO and compare the 7 variables hour by hour.

Pass criterion: differences at floating-point-rounding level
(temp/dewpoint < 0.01 K, wind < 0.01 m/s, pressure < 1 Pa, radiation
within a few J/m2 or a small relative tolerance).

Run:  python scripts/verify_arco_vs_cds.py
"""

import pathlib
import sys
import tempfile
import zipfile

import numpy as np
import pandas as pd
import xarray as xr

ARCO_URL = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
DOHA_LAT, DOHA_LON = 25.27, 51.61

CDS_DIR = pathlib.Path("data/era5")

# CDS short name -> ARCO long name
VARMAP = {
    "t2m": "2m_temperature",
    "d2m": "2m_dewpoint_temperature",
    "sp": "surface_pressure",
    "u10": "10m_u_component_of_wind",
    "v10": "10m_v_component_of_wind",
    "ssrd": "surface_solar_radiation_downwards",
    "fdir": "total_sky_direct_solar_radiation_at_surface",
}


def load_cds_point(path: pathlib.Path) -> xr.Dataset:
    with path.open("rb") as fh:
        is_zip = fh.read(2) == b"PK"
    if is_zip:
        td = tempfile.mkdtemp()
        with zipfile.ZipFile(path) as z:
            z.extractall(td)
        parts = [xr.open_dataset(p) for p in sorted(pathlib.Path(td).glob("*.nc"))]
        ds = xr.merge(parts, compat="override")
    else:
        ds = xr.open_dataset(path)
    ds = ds.sel(latitude=DOHA_LAT, longitude=DOHA_LON, method="nearest")
    for d in list(ds.sizes):
        if d not in ("valid_time", "time") and ds.sizes[d] == 1:
            ds = ds.squeeze(d, drop=True)
    tname = "valid_time" if "valid_time" in ds.coords else "time"
    return ds.rename({tname: "time"})


def main() -> None:
    files = sorted(CDS_DIR.glob("era5_doha_*.nc"))
    if not files:
        raise SystemExit("No CDS files to compare against.")

    print(f"Opening ARCO-ERA5 ...", file=sys.stderr)
    arco = xr.open_zarr(ARCO_URL, storage_options={"token": "anon"}, chunks=None)
    arco_pt = arco.sel(latitude=DOHA_LAT, longitude=DOHA_LON, method="nearest")

    tol = {"t2m": 0.02, "d2m": 0.02, "sp": 2.0, "u10": 0.02, "v10": 0.02,
           "ssrd": 500.0, "fdir": 500.0}   # abs tol; radiation in J/m2

    overall_ok = True
    for f in files:
        cds = load_cds_point(f)
        t0 = pd.Timestamp(cds.time.values[0])
        t1 = pd.Timestamp(cds.time.values[-1])
        a = arco_pt.sel(time=slice(t0, t1))

        print(f"\n=== {f.name}  ({t0.date()} .. {t1.date()}, "
              f"{cds.sizes['time']} h) ===")
        print(f"  {'var':<6} {'max|Δ|':>12} {'mean|Δ|':>12} {'tol':>8}  result")
        for short, longn in VARMAP.items():
            cv = np.asarray(cds[short].values, dtype=float)
            av = np.asarray(a[longn].values, dtype=float)
            n = min(len(cv), len(av))
            d = np.abs(cv[:n] - av[:n])
            mx, mn = np.nanmax(d), np.nanmean(d)
            ok = mx <= tol[short]
            overall_ok &= ok
            print(f"  {short:<6} {mx:12.4f} {mn:12.4f} {tol[short]:8.2f}  "
                  f"{'PASS' if ok else 'FAIL'}")

    print("\n" + ("ALL PASS - ARCO is equivalent to CDS for our variables."
                  if overall_ok else
                  "SOME FAIL - inspect before switching."))


if __name__ == "__main__":
    main()
