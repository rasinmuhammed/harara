"""
Convert the per-month ERA5 files from fetch_era5.py into one tidy hourly
CSV with the SAME schema as the Open-Meteo file, so the two are drop-in
interchangeable for WBGT and for the wind cross-check.

The new Copernicus CDS returns each request as a ZIP containing two
NetCDFs - instantaneous variables (t2m, d2m, sp, u10, v10) and
accumulated variables (ssrd, fdir) are split by "step type". This script
handles that (and a plain single .nc, for older downloads).

Output columns (match data/doha_openmeteo_16yr.csv):
    time, temperature_2m, relative_humidity_2m, surface_pressure,
    wind_speed_10m, direct_radiation, shortwave_radiation

Run:  python scripts/era5_to_csv.py --indir data/era5 \
          --out data/doha_era5_hourly.csv
"""

import argparse
import pathlib
import sys
import tempfile
import zipfile

import numpy as np
import pandas as pd

try:
    import xarray as xr
except ImportError:
    raise SystemExit("Need xarray + netcdf4:  pip install xarray netcdf4")

# Doha, for nearest-gridpoint selection.
DOHA_LAT, DOHA_LON = 25.27, 51.61


def rh_from_dewpoint(t_k: np.ndarray, td_k: np.ndarray) -> np.ndarray:
    """Relative humidity [%] from temperature and dewpoint (both K),
    Magnus formula over water."""
    t_c, td_c = t_k - 273.15, td_k - 273.15
    a, b = 17.625, 243.04
    e = np.exp(a * td_c / (b + td_c))
    es = np.exp(a * t_c / (b + t_c))
    return np.clip(100.0 * e / es, 0.0, 100.0)


def _open_point(path: pathlib.Path) -> xr.Dataset:
    """Open a NetCDF, select the grid cell nearest Doha, drop stray dims."""
    ds = xr.open_dataset(path)
    latname = "latitude" if "latitude" in ds.coords else "lat"
    lonname = "longitude" if "longitude" in ds.coords else "lon"
    ds = ds.sel({latname: DOHA_LAT, lonname: DOHA_LON}, method="nearest")
    # `number` (ensemble) / `expver` are scalar or stray coords for
    # reanalysis - squeeze anything that isn't the time axis.
    for d in list(ds.sizes):
        if d not in ("valid_time", "time") and ds.sizes[d] == 1:
            ds = ds.squeeze(d, drop=True)
    return ds


def load_month(path: pathlib.Path) -> pd.DataFrame:
    with path.open("rb") as fh:
        is_zip = fh.read(2) == b"PK"

    if is_zip:
        with tempfile.TemporaryDirectory() as td:
            with zipfile.ZipFile(path) as z:
                z.extractall(td)
            parts = [_open_point(p) for p in sorted(pathlib.Path(td).glob("*.nc"))]
            ds = xr.merge(parts, compat="override")
            merged = _finish(ds)
        return merged
    else:
        return _finish(_open_point(path))


def _finish(ds: xr.Dataset) -> pd.DataFrame:
    tname = "valid_time" if "valid_time" in ds.coords else "time"
    df = pd.DataFrame({"time": pd.to_datetime(ds[tname].values, utc=True)})

    df["temperature_2m"] = ds["t2m"].values - 273.15
    df["relative_humidity_2m"] = rh_from_dewpoint(ds["t2m"].values,
                                                  ds["d2m"].values)
    df["surface_pressure"] = ds["sp"].values / 100.0            # Pa -> hPa
    df["wind_speed_10m"] = np.sqrt(ds["u10"].values ** 2
                                   + ds["v10"].values ** 2)

    # ERA5 hourly radiation is J/m2 accumulated over the preceding hour;
    # divide by 3600 s -> W/m2. Clip tiny negatives from packing.
    df["shortwave_radiation"] = np.clip(ds["ssrd"].values / 3600.0, 0, None)
    df["direct_radiation"] = np.clip(ds["fdir"].values / 3600.0, 0, None)

    ds.close()
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", default="data/era5")
    ap.add_argument("--out", default="data/doha_era5_hourly.csv")
    args = ap.parse_args()

    files = sorted(pathlib.Path(args.indir).glob("era5_doha_*.nc"))
    if not files:
        raise SystemExit(f"No era5_doha_*.nc in {args.indir} - run fetch_era5.py first.")

    parts = []
    for f in files:
        print(f"  reading {f.name}", file=sys.stderr)
        try:
            parts.append(load_month(f))
        except Exception as e:                       # noqa: BLE001
            print(f"    SKIPPED ({e})", file=sys.stderr)

    df = (pd.concat(parts, ignore_index=True)
            .drop_duplicates(subset="time")
            .sort_values("time")
            .reset_index(drop=True))
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} rows ({df['time'].min()} .. {df['time'].max()}) "
          f"to {args.out}", file=sys.stderr)
