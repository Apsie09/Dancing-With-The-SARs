"""AquaGuard configuration: study area, paths, analysis grid."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from pyproj import Transformer
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
STATIC = DATA / "static"
MET = DATA / "met"
VECTORS = DATA / "vectors"
OUTPUTS = ROOT / "outputs"

for _p in (RAW, INTERIM, STATIC, MET, VECTORS, OUTPUTS):
    _p.mkdir(parents=True, exist_ok=True)

# Small farmland AOI crossed by an underground water transmission main
# (OSM way 1106343159), near Elin Pelin, Sofia Province, Bulgaria.
AOI = {
    "name": "Elin Pelin water main",
    "west": 23.575,
    "south": 42.610,
    "east": 23.640,
    "north": 42.665,
    "center_lon": 23.6075,
    "center_lat": 42.6375,
}

GRID_EPSG = 32634  # UTM zone 34N
RES = 20.0  # metres, analysis grid
START = "2018-01-01"
END = "2026-11-15"

# Sentinel-1 RTC on Planetary Computer
PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
S1_COLLECTION = "sentinel-1-rtc"
# Sentinel-2 / Landsat on AWS Earth Search (public COGs)
ES_STAC = "https://earth-search.aws.element84.com/v1"
S2_COLLECTION = "sentinel-2-l2a"
LANDSAT_COLLECTION = "landsat-c2-l2"

# ASF NISAR GCOV search (public browse + public downloads)
ASF_SEARCH = "https://api.daac.asf.alaska.edu/services/search/param"


def aoi_bbox() -> list[float]:
    return [AOI["west"], AOI["south"], AOI["east"], AOI["north"]]


def aoi_wkt() -> str:
    w, s, e, n = aoi_bbox()
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


def analysis_grid(res: float = RES) -> dict:
    """Return a north-up UTM grid snapped to `res` metres covering the AOI."""
    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{GRID_EPSG}", always_xy=True)
    xs, ys = [], []
    for lon in (AOI["west"], AOI["east"]):
        for lat in (AOI["south"], AOI["north"]):
            x, y = tr.transform(lon, lat)
            xs.append(x)
            ys.append(y)
    west = np.floor(min(xs) / res) * res
    east = np.ceil(max(xs) / res) * res
    south = np.floor(min(ys) / res) * res
    north = np.ceil(max(ys) / res) * res
    width = int(round((east - west) / res))
    height = int(round((north - south) / res))
    return {
        "crs": f"EPSG:{GRID_EPSG}",
        "res": res,
        "west": float(west),
        "south": float(south),
        "east": float(east),
        "north": float(north),
        "width": width,
        "height": height,
        "transform": from_origin(west, north, res, res),
    }


def grid_dict(g: dict) -> dict:
    d = {k: v for k, v in g.items() if k != "transform"}
    t = g["transform"]
    d["transform"] = [t.a, t.b, t.c, t.d, t.e, t.f]
    return d


def save_grid(g: dict | None = None) -> dict:
    g = g or analysis_grid()
    (INTERIM / "grid.json").write_text(json.dumps(grid_dict(g), indent=2))
    return g


if __name__ == "__main__":
    g = save_grid()
    print(json.dumps(grid_dict(g), indent=2))
