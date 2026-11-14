#!/usr/bin/env python
"""Acquire hourly meteorology for the Elin Pelin AOI from the Open-Meteo ERA5 archive.

Source : https://archive-api.open-meteo.com/v1/archive (ERA5 / ERA5T, no auth)
Period : 2022-01-01 .. 2026-11-14 (UTC)
Point  : 42.6375 N, 23.6075 E (API snaps to nearest ERA5 grid cell)

Outputs (data/met/):
  weather_hourly.csv  - one row per hour, native API variable names
  weather_daily.csv   - daily aggregates, one row per date
  metadata.json       - request URL, returned coordinates/elevation, units

Run:
  ~/.pixi/bin/pixi run python data/static/scripts/fetch_met.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "met"
OUT.mkdir(parents=True, exist_ok=True)

LAT, LON = 42.6375, 23.6075
START, END = "2022-01-01", "2026-11-14"
HOURLY_VARS = [
    "temperature_2m",
    "precipitation",
    "relative_humidity_2m",
    "shortwave_radiation",
    "et0_fao_evapotranspiration",
    "soil_moisture_0_to_7cm",
    "soil_moisture_7_to_28cm",
    "soil_moisture_28_to_100cm",
    "vapor_pressure_deficit",
    "wind_speed_10m",
]
BASE_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch(variables: list[str]) -> dict:
    params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": START,
        "end_date": END,
        "hourly": ",".join(variables),
        "timezone": "UTC",
    }
    r = requests.get(BASE_URL, params=params, timeout=300)
    r.raise_for_status()
    payload = r.json()
    if payload.get("error"):
        raise RuntimeError(f"Open-Meteo error: {payload.get('reason')}")
    return payload


def main() -> None:
    payload = fetch(HOURLY_VARS)
    units = payload["hourly_units"]
    hourly = payload["hourly"]

    # Drop any variable the API did not return (defensive; all 10 are available).
    missing = [v for v in HOURLY_VARS if v not in hourly]
    if missing:
        print(f"WARNING: variables missing from response, dropped: {missing}")
        HOURLY_VARS[:] = [v for v in HOURLY_VARS if v in hourly]

    df = pd.DataFrame({"time_utc": pd.to_datetime(hourly["time"], utc=True)})
    for v in HOURLY_VARS:
        df[v] = pd.to_numeric(pd.Series(hourly[v]), errors="coerce")

    # Local naive UTC timestamp is easier for downstream joins; keep ISO string too.
    df["time_utc"] = df["time_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    df.to_csv(OUT / "weather_hourly.csv", index=False)

    d = df.copy()
    d["date"] = pd.to_datetime(d.pop("time_utc"), utc=True).dt.date
    g = d.groupby("date", sort=True)

    daily = pd.DataFrame(
        {
            "precip_sum": g["precipitation"].sum(min_count=1),
            "temp_mean": g["temperature_2m"].mean(),
            "temp_min": g["temperature_2m"].min(),
            "temp_max": g["temperature_2m"].max(),
            "rh_mean": g["relative_humidity_2m"].mean(),
            "radiation_sum": g["shortwave_radiation"].sum(min_count=1),
            "et0_sum": g["et0_fao_evapotranspiration"].sum(min_count=1),
            "sm0_7": g["soil_moisture_0_to_7cm"].mean(),
            "sm7_28": g["soil_moisture_7_to_28cm"].mean(),
            "sm28_100": g["soil_moisture_28_to_100cm"].mean(),
            "vpd_mean": g["vapor_pressure_deficit"].mean(),
            "wind_mean": g["wind_speed_10m"].mean(),
            "n_hours": g["temperature_2m"].count(),
        }
    ).reset_index()
    daily["radiation_mj_m2"] = daily["radiation_sum"] * 0.0036  # W h/m2 -> MJ/m2
    daily.to_csv(OUT / "weather_daily.csv", index=False)

    meta = {
        "source": "Open-Meteo ERA5 archive API (ERA5 + ERA5T)",
        "request_url": f"{BASE_URL}?latitude={LAT}&longitude={LON}&start_date={START}"
        f"&end_date={END}&hourly={','.join(HOURLY_VARS)}&timezone=UTC",
        "requested_lat": LAT,
        "requested_lon": LON,
        "returned_lat": payload.get("latitude"),
        "returned_lon": payload.get("longitude"),
        "grid_elevation_m": payload.get("elevation"),
        "timezone": "UTC",
        "start": START,
        "end": END,
        "hourly_units": units,
        "daily_units": {
            "precip_sum": "mm/day",
            "temp_mean/min/max": "degC",
            "rh_mean": "%",
            "radiation_sum": "W h/m2/day",
            "radiation_mj_m2": "MJ/m2/day",
            "et0_sum": "mm/day",
            "sm0_7/sm7_28/sm28_100": "m3/m3 (daily mean)",
            "vpd_mean": "kPa",
            "wind_mean": "km/h",
            "n_hours": "count of valid hourly values",
        },
        "n_hours": len(df),
        "first_hour": str(df["time_utc"].iloc[0]),
        "last_hour": str(df["time_utc"].iloc[-1]),
    }
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")

    print(f"wrote {len(df)} hourly rows, {len(daily)} daily rows")
    print(daily.describe().round(3).to_string())
    print("daily date range:", daily["date"].iloc[0], "->", daily["date"].iloc[-1])
    print("days with n_hours != 24:", int((daily["n_hours"] != 24).sum()))


if __name__ == "__main__":
    main()
