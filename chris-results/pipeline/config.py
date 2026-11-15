"""AquaGuard configuration: study area, paths, analysis grid.

Default: Elin Pelin, Bulgaria (the NASA Space Apps demo).

Case mode: set AQUAGUARD_CASE=/path/to/case.json to run the same pipeline on
another AOI.  The JSON overrides the AOI, grid, date range, sensor orbit,
pipeline network, labels, dry-season months and train/test split.  Case data
lives under the case root's data/ and outputs/ directories, so cases never
touch the Bulgaria products.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from pyproj import Transformer
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------- #
# Default (Bulgaria) values
# --------------------------------------------------------------------------- #
CASE = None
CASE_ROOT = ROOT
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
STATIC = DATA / "static"
MET = DATA / "met"
VECTORS = DATA / "vectors"
OUTPUTS = ROOT / "outputs"

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
S1_ORBIT_STATE = "descending"
S1_RELATIVE_ORBIT = 7
PIPELINE_GEOJSON = VECTORS / "water_main.geojson"
GAS_GEOJSON = VECTORS / "pipelines_aoi.geojson"
LABELS_CSV = None
DRY_MONTHS = (6, 7, 8, 9)
DRY_YEARS = None
TRAIN_END = "2025-07-01"
VAL_END = "2026-01-01"
CASE_NAME = "Elin Pelin water main"

# --------------------------------------------------------------------------- #
# Case override
# --------------------------------------------------------------------------- #
_case_env = os.environ.get("AQUAGUARD_CASE")
if _case_env:
    case_path = Path(_case_env)
    if not case_path.is_absolute():
        case_path = ROOT / case_path
    CASE = json.loads(case_path.read_text())
    CASE_ROOT = Path(CASE["root"])
    if not CASE_ROOT.is_absolute():
        CASE_ROOT = ROOT / CASE_ROOT

    DATA = CASE_ROOT / "data"
    RAW = DATA / "raw"
    INTERIM = DATA / "interim"
    STATIC = DATA / "static"
    MET = DATA / "met"
    VECTORS = DATA / "vectors"
    OUTPUTS = CASE_ROOT / "outputs"

    AOI = CASE["aoi"]
    GRID_EPSG = int(CASE.get("grid_epsg", 32634))
    RES = float(CASE.get("res", 20.0))
    START = CASE.get("start", START)
    END = CASE.get("end", END)
    S1_ORBIT_STATE = CASE.get("s1_orbit_state", "descending")
    S1_RELATIVE_ORBIT = int(CASE.get("s1_relative_orbit", 7))

    def _case_path(value: str | None) -> Path | None:
        return (CASE_ROOT / value) if value else None

    PIPELINE_GEOJSON = _case_path(CASE.get("pipeline_geojson", "data/vectors/water_main.geojson"))
    GAS_GEOJSON = _case_path(CASE.get("gas_geojson"))
    LABELS_CSV = _case_path(CASE.get("labels_csv"))
    DRY_MONTHS = tuple(CASE.get("dry_months", [6, 7, 8, 9]))
    DRY_YEARS = tuple(CASE["dry_years"]) if CASE.get("dry_years") else None
    TRAIN_END = CASE.get("train_end", "2025-07-01")
    VAL_END = CASE.get("val_end", "2026-01-01")
    CASE_NAME = CASE.get("name", "AquaGuard case")

for _p in (DATA, RAW, INTERIM, STATIC, MET, VECTORS, OUTPUTS):
    _p.mkdir(parents=True, exist_ok=True)

# STAC endpoints shared by all cases
PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
S1_COLLECTION = "sentinel-1-rtc"
ES_STAC = "https://earth-search.aws.element84.com/v1"
S2_COLLECTION = "sentinel-2-l2a"
LANDSAT_COLLECTION = "landsat-c2-l2"
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
