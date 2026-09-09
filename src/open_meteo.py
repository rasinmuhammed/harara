"""
Live hourly weather forecast from the Open-Meteo forecast API (no key, up to
16 days), in the variable set and units the WBGT code expects.

This is a runtime dependency of the API (src.agent.tools.get_forecast), so it
lives in src/ rather than scripts/. scripts/fetch_forecast.py re-exports it for
command-line use.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import requests

BASE_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = [
    "temperature_2m", "relative_humidity_2m", "surface_pressure",
    "wind_speed_10m", "direct_radiation", "shortwave_radiation",
]


def fetch_forecast(lat: float, lon: float, start: dt.date, end: dt.date,
                   timeout: int = 60) -> pd.DataFrame:
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC", "wind_speed_unit": "ms",
    }
    r = requests.get(BASE_URL, params=params, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(j.get("reason", "open-meteo forecast error"))
    df = pd.DataFrame(j["hourly"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df
