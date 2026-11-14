"""Kitchener water-main network (ArcGIS Feature Service) -> kitchener_water_mains.parquet.

Used to place control sites on the same kind of infrastructure as the break sites (Stage 6).
"""
from __future__ import annotations

import json
import time
from datetime import date

import geopandas as gpd
import pandas as pd
import requests

from .config import UTM_CRS, WGS84, Config, report_file

SERVICE = "https://services1.arcgis.com/qAo1OsXi67t7XgmS/ArcGIS/rest/services/Water_Mains/FeatureServer/0"
# CONDITION_SCORE / CRITICALITY / LINED* describe the asset's *current* state (possibly assessed after
# breaks) and must not be used as predictive features; kept for analysis only.
KEEP = {"WATMAINID": "main_id", "STATUS": "status", "CATEGORY": "category", "PRESSURE_ZONE": "pressure_zone",
        "ROADSEGMENTID": "road_segment_id", "PIPE_SIZE": "pipe_size_mm", "MATERIAL": "material",
        "INSTALLATION_DATE": "installation_date", "LINED": "lined", "LINED_DATE": "lined_date",
        "CONDITION_SCORE": "condition_score_current", "CRITICALITY": "criticality_current",
        "SHALLOW_MAIN": "shallow_main", "BRIDGE_MAIN": "bridge_main"}


def fetch(page: int = 2000) -> dict:
    url = SERVICE + "/query"
    n = requests.get(url, params={"where": "1=1", "returnCountOnly": "true", "f": "json"}, timeout=60).json()["count"]
    feats, off = [], 0
    while off < n:
        params = {"where": "1=1", "outFields": ",".join(KEEP), "outSR": 4326, "f": "geojson",
                  "orderByFields": "OBJECTID", "resultOffset": off, "resultRecordCount": page}
        for attempt in range(4):
            try:
                r = requests.get(url, params=params, timeout=120)
                r.raise_for_status()
                batch = r.json()["features"]
                break
            except (requests.RequestException, KeyError, ValueError):
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        feats += batch
        off += page
        print(f"  fetched {len(feats)}/{n} main segments")
    if len(feats) != n:
        raise RuntimeError(f"pagination mismatch: {len(feats)} != {n}")
    return {"type": "FeatureCollection", "features": feats}


def run(cfg: Config) -> gpd.GeoDataFrame:
    print("Water-main network")
    fc = fetch()
    raw = cfg.path("raw_dir") / f"kitchener_water_mains_raw_{date.today():%Y%m%d}.geojson"
    raw.write_text(json.dumps(fc))
    print(f"  raw snapshot -> {report_file(raw)}")
    g = gpd.GeoDataFrame.from_features(fc["features"], crs=WGS84).rename(columns=KEEP)
    for c in ("installation_date", "lined_date"):
        g[c] = pd.to_datetime(pd.to_numeric(g[c], errors="coerce"), unit="ms", utc=True)
    g["install_year"] = g["installation_date"].dt.year.astype("Int64")
    g["material"] = g["material"].replace({"XXX": None, "": None})
    g["pipe_size_mm"] = pd.to_numeric(g["pipe_size_mm"], errors="coerce").where(lambda s: s > 0)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    g["length_m"] = g.geometry.to_crs(UTM_CRS).length
    out = cfg.path("processed_dir") / "kitchener_water_mains.parquet"
    g.to_parquet(out)
    act = g[g["status"].eq("ACTIVE")]
    print(f"  {len(g)} segments, {g['length_m'].sum() / 1000:.0f} km total; active: {len(act)} ({act['length_m'].sum() / 1000:.0f} km)")
    print(f"  mains -> {report_file(out)}")
    return g
