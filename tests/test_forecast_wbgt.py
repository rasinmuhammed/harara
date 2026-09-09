"""
WBGT-from-forecast-fields path: it must reproduce a direct wbgt_liljegren_c
call exactly, fail loudly on missing inputs, stay finite at night, and
fall back to an Erbs direct-beam estimate only when the direct column is
absent.
"""

import numpy as np
import pandas as pd
import pytest

from src.forecast_wbgt import wbgt_from_forecast_frame
from src.solar import cos_solar_zenith_angle
from src.wbgt import wbgt_liljegren_c

LAT, LON = 25.27, 51.61


def _frame():
    times = pd.date_range("2025-07-15 00:00", "2025-07-15 23:00",
                          freq="h", tz="UTC")
    n = len(times)
    # crude diurnal shapes, physically plausible for a Doha summer day
    local_h = (np.arange(n) + 3) % 24
    diurnal = np.sin(np.pi * np.clip((local_h - 5) / 14.0, 0, None))
    return pd.DataFrame({
        "time": times,
        "temperature_2m": 34.0 + 9.0 * diurnal,
        "relative_humidity_2m": 55.0 - 20.0 * diurnal,
        "wind_speed_10m": 3.0 + 2.0 * diurnal,
        "shortwave_radiation": np.maximum(0.0, 950.0 * diurnal),
        "direct_radiation": np.maximum(0.0, 680.0 * diurnal),
        "surface_pressure": np.full(n, 1000.0),
    })


def test_matches_direct_liljegren_call():
    df = _frame()
    cz = cos_solar_zenith_angle(pd.DatetimeIndex(df["time"]), LAT, LON)
    ref = wbgt_liljegren_c(
        temp_c=df["temperature_2m"].to_numpy(float),
        rh_pct=df["relative_humidity_2m"].to_numpy(float),
        pressure_hpa=df["surface_pressure"].to_numpy(float),
        wind_speed_10m_ms=df["wind_speed_10m"].to_numpy(float),
        shortwave_wm2=df["shortwave_radiation"].to_numpy(float),
        direct_wm2=df["direct_radiation"].to_numpy(float),
        cos_zenith=cz,
    )
    got = wbgt_from_forecast_frame(df, LAT, LON)
    assert got.used_erbs_direct is False
    np.testing.assert_allclose(np.asarray(got), ref, rtol=0, atol=1e-6,
                               equal_nan=True)


def test_missing_column_raises():
    df = _frame().drop(columns=["relative_humidity_2m"])
    with pytest.raises(KeyError):
        wbgt_from_forecast_frame(df, LAT, LON)


def test_night_hours_finite_and_cooler_than_noon():
    df = _frame()
    w = np.asarray(wbgt_from_forecast_frame(df, LAT, LON))
    assert np.isfinite(w).all()
    local = pd.DatetimeIndex(df["time"]).tz_convert("Asia/Qatar").hour
    assert w[local == 3].mean() < w[local == 13].mean()


def test_erbs_fallback_when_direct_absent():
    df = _frame().drop(columns=["direct_radiation"])
    got = wbgt_from_forecast_frame(df, LAT, LON)
    assert got.used_erbs_direct is True
    w = np.asarray(got)
    assert np.isfinite(w).all()
    # a plausible Doha-summer daily peak
    assert 28.0 < w.max() < 40.0
