"""Extract the OSM pipeline network around the AOI.

Uses a cached Overpass dump in data/vectors/overpass_pipelines_raw.json; if it
is missing, the query is fetched from the public Overpass API.  The cache is
small and can be committed, so the rest of the pipeline is reproducible without
depending on /tmp files.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import LineString, box

from pipeline.config import AOI, VECTORS

CACHE = VECTORS / "overpass_pipelines_raw.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "TerraGuard/1.0 (NASA Space Apps hackathon)"


def fetch_overpass() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    pad = 0.02
    s = AOI["south"] - pad
    w = AOI["west"] - pad
    n = AOI["north"] + pad
    e = AOI["east"] + pad
    query = (
        f'[out:json][timeout:90];'
        f'way["man_made"="pipeline"]({s},{w},{n},{e});'
        f'out tags geom;'
    )
    last = None
    for attempt in range(3):
        try:
            r = requests.post(OVERPASS, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=120)
            r.raise_for_status()
            d = r.json()
            CACHE.write_text(json.dumps(d))
            return d
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Overpass failed after 3 attempts: {last}")


def main() -> None:
    d = fetch_overpass()
    bbox = box(AOI["west"], AOI["south"], AOI["east"], AOI["north"])
    rows = []
    for e in d["elements"]:
        g = e.get("geometry") or []
        if len(g) < 2:
            continue
        t = e.get("tags", {}) or {}
        line = LineString([(c["lon"], c["lat"]) for c in g])
        if line.distance(bbox) > 0.02:  # keep 2 km of context
            continue
        rows.append(
            {
                "osm_id": e["id"],
                "substance": t.get("substance") or t.get("type") or "unknown",
                "location": t.get("location"),
                "name": t.get("name"),
                "operator": t.get("operator"),
                "geometry": line,
            }
        )
    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326").sort_values(["substance", "osm_id"]).reset_index(drop=True)

    water = gdf[gdf["substance"].isin(["water", "sewage"])].copy()
    water.to_file(VECTORS / "water_pipelines.geojson", driver="GeoJSON")
    gdf.to_file(VECTORS / "pipelines_aoi.geojson", driver="GeoJSON")

    main = water[water["osm_id"] == 1106343159]
    if len(main):
        main.to_file(VECTORS / "water_main.geojson", driver="GeoJSON")
        print("water main length km:", round(main.to_crs(32634).length.sum() / 1000, 2))
    print(gdf.groupby("substance").size().to_dict())
    print("wrote", VECTORS / "pipelines_aoi.geojson")


if __name__ == "__main__":
    main()
