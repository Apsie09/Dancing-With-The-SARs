#!/usr/bin/env python
"""Acquire static layers for the Elin Pelin (Bulgaria) farmland AOI.

Layers / sources
  1. SoilGrids 250 m - ISRIC WCS GetCoverage (sand, clay, silt, soc, bdod;
     0-5 cm and 5-15 cm) + 6x8 point-API samples for QC.
     https://maps.isric.org/mapserv?map=/map/<property>.map
     https://rest.isric.org/soilgrids/v2.0/properties/query
  2. ESA WorldCover 2021 v200 10 m - tile N42E021 (3x3 deg tiles).
     https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N42E021_Map.tif
  3. Copernicus DEM GLO-30 - tile N42E023.
     https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N42_00_E023_00_DEM/Copernicus_DSM_COG_10_N42_00_E023_00_DEM.tif
  4. OSM buildings and roads - Overpass API (optional distance-to-built raster).

All GeoTIFFs are written on one common analysis grid:
  EPSG:32634 (UTM 34N), 10 m, origin (711020, 4727000), 553 x 628 px.
WorldCover/DEM native products are EPSG:4326 and 30 m; resampling is documented
in research/static-data.md. Soil layers are bilinearly resampled from 250 m.

Run:
  ~/.pixi/bin/pixi run python data/static/scripts/fetch_static.py

Only writes to data/static/.
"""
from __future__ import annotations

import io
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
import rasterio
from rasterio.features import rasterize
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "static"
OUT.mkdir(parents=True, exist_ok=True)
RAW = Path("/tmp/opencode/soil_wcs")
RAW.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# AOI / common grid
# --------------------------------------------------------------------------- #
W, S, E, N = 23.575, 42.610, 23.640, 42.665  # EPSG:4326
BBOX = (W, S, E, N)
DST_CRS = "EPSG:32634"
RES = 10.0

_b = transform_bounds("EPSG:4326", DST_CRS, *BBOX)
XMIN = math.floor(_b[0] / RES) * RES
XMAX = math.ceil(_b[2] / RES) * RES
YMIN = math.floor(_b[1] / RES) * RES
YMAX = math.ceil(_b[3] / RES) * RES
WIDTH = int(round((XMAX - XMIN) / RES))
HEIGHT = int(round((YMAX - YMIN) / RES))
TRANSFORM = from_origin(XMIN, YMAX, RES, RES)
DST_SHAPE = (HEIGHT, WIDTH)
print(f"analysis grid: {WIDTH} x {HEIGHT} px, {DST_CRS}, {RES} m")
print(f"bounds: {XMIN}, {YMIN}, {XMAX}, {YMAX}")

STATUS: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "analysis_grid": {"crs": DST_CRS, "res_m": RES, "width": WIDTH,
                                  "height": HEIGHT, "transform": list(TRANSFORM)[:6],
                                  "bounds": [XMIN, YMIN, XMAX, YMAX]},
                "layers": {}, "failures": []}
ARRAYS: dict[str, np.ndarray] = {}


def write_tif(name: str, arr: np.ndarray, dtype: str, nodata, description: str,
              tags: dict | None = None) -> None:
    profile = {
        "driver": "GTiff", "height": HEIGHT, "width": WIDTH, "count": 1,
        "dtype": dtype, "crs": DST_CRS, "transform": TRANSFORM, "nodata": nodata,
        "compress": "deflate", "predictor": 2, "tiled": True,
        "blockxsize": 256, "blockysize": 256,
    }
    with rasterio.open(OUT / name, "w", **profile) as dst:
        dst.write(arr.astype(dtype), 1)
        dst.set_band_description(1, description)
        if tags:
            dst.update_tags(**tags)
    print(f"  wrote {name}")


def stats(arr: np.ndarray, nodata=np.nan) -> dict:
    a = arr.astype("float64")
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"valid_px": 0}
    return {"valid_px": int(a.size), "min": float(a.min()), "max": float(a.max()),
            "mean": float(a.mean()), "median": float(np.median(a)),
            "p05": float(np.percentile(a, 5)), "p95": float(np.percentile(a, 95))}


def reproject_to_grid(src_arr, src_transform, src_crs, resampling,
                      src_nodata=None, dst_dtype="float32", dst_nodata=np.nan):
    dst = np.full(DST_SHAPE, dst_nodata, dtype=dst_dtype)
    reproject(source=src_arr.astype("float32"), destination=dst,
              src_transform=src_transform, src_crs=src_crs,
              dst_transform=TRANSFORM, dst_crs=DST_CRS,
              src_nodata=src_nodata, dst_nodata=dst_nodata,
              resampling=resampling)
    return dst


# --------------------------------------------------------------------------- #
# 1. SoilGrids
# --------------------------------------------------------------------------- #
SOIL_PROPS = ["sand", "clay", "silt", "soc", "bdod"]
SOIL_DEPTHS = [("0-5cm", "0_5", (0, 5)), ("5-15cm", "5_15", (5, 15))]
SOIL_UNITS = {"sand": "g/kg", "clay": "g/kg", "silt": "g/kg",
              "soc": "g/kg", "bdod": "g/cm3"}  # output units (normalised)
SOIL_SRC_UNITS = {"sand": "g/kg", "clay": "g/kg", "silt": "g/kg",
                  "soc": "dg/kg", "bdod": "cg/cm3"}  # units returned by WCS/API
SOIL_SCALE = {"sand": 1.0, "clay": 1.0, "silt": 1.0, "soc": 0.1, "bdod": 0.01}
SOIL_LONG = {"sand": "sand content", "clay": "clay content", "silt": "silt content",
             "soc": "soil organic carbon", "bdod": "bulk density (fine earth)"}
WCS_MAP = {"sand": "sand", "clay": "clay", "silt": "silt", "soc": "soc", "bdod": "bdod"}


def fetch_wcs(prop: str, depth_id: str) -> tuple[np.ndarray, object, object, dict]:
    """GetCoverage for one soil property/depth at native ~250 m, expanded AOI."""
    pad = 0.01
    url = f"https://maps.isric.org/mapserv?map=/map/{WCS_MAP[prop]}.map"
    params = [
        ("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"),
        ("COVERAGEID", f"{prop}_{depth_id}_mean"), ("FORMAT", "image/tiff"),
        ("SUBSET", f"long({W - pad},{E + pad})"),
        ("SUBSET", f"lat({S - pad},{N + pad})"),
        ("SUBSETTINGCRS", "http://www.opengis.net/def/crs/EPSG/0/4326"),
        ("OUTPUTCRS", "http://www.opengis.net/def/crs/EPSG/0/4326"),
    ]
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=180)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                with MemoryFile(r.content) as mem:
                    with mem.open() as ds:
                        return ds.read(1), ds.transform, ds.crs, {"url": url,
                                                                  "coverage_id": f"{prop}_{depth_id}_mean",
                                                                  "bytes": len(r.content)}
            last = f"HTTP {r.status_code}: {r.text[:300]}"
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"WCS failed for {prop} {depth_id}: {last}")


def sample_point(lon: float, lat: float, sid: int) -> dict:
    url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    params = {"lon": lon, "lat": lat, "property": SOIL_PROPS,
              "depth": [d[0] for d in SOIL_DEPTHS], "value": "mean"}
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 200:
                js = r.json()
                rows = []
                for layer in js["properties"]["layers"]:
                    unit = layer["unit_measure"]["mapped_units"]
                    for dep in layer["depths"]:
                        rows.append({
                            "sample_id": sid, "lon": round(lon, 6), "lat": round(lat, 6),
                            "property": layer["name"], "depth": dep["label"],
                            "value": dep["values"]["mean"], "unit": unit,
                        })
                return {"ok": True, "rows": rows, "query_time_s": js.get("query_time_s")}
            last = f"HTTP {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
        time.sleep(1.5 * (attempt + 1))
    return {"ok": False, "lon": lon, "lat": lat, "error": last}


def fetch_soil_samples() -> list[dict]:
    lons = np.linspace(W, E, 6)
    lats = np.linspace(S, N, 8)
    pts = [(float(lon), float(lat)) for lat in lats for lon in lons]
    print(f"sampling SoilGrids point API at {len(pts)} points (6 x 8) ...")
    rows, failures = [], []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(sample_point, lon, lat, i) for i, (lon, lat) in enumerate(pts)]
        for i, fut in enumerate(futs):
            res = fut.result()
            if res["ok"]:
                rows.extend(res["rows"])
            else:
                failures.append({"lon": res["lon"], "lat": res["lat"], "error": res["error"]})
            if (i + 1) % 12 == 0:
                print(f"  {i + 1}/{len(pts)} points done ({time.time() - t0:.0f}s)")
    print(f"point sampling done in {time.time() - t0:.0f}s, failures={len(failures)}")
    return rows, failures


SAMPLES_CSV = OUT / "soil_samples_6x8.csv"
if SAMPLES_CSV.exists() and os.environ.get("FORCE_SOIL", "0") != "1":
    import pandas as pd
    sdf = pd.read_csv(SAMPLES_CSV)
    print(f"reusing cached {SAMPLES_CSV.name} ({len(sdf)} rows)")
else:
    soil_rows, soil_fail = fetch_soil_samples()
    if soil_rows:
        import pandas as pd
        sdf = pd.DataFrame(soil_rows)
        sdf.to_csv(SAMPLES_CSV, index=False)
        print(f"  wrote soil_samples_6x8.csv ({len(sdf)} rows, {sdf.sample_id.nunique()} points)")
for prop in SOIL_PROPS:
    for depth_id, fname, (d0, d1) in SOIL_DEPTHS:
        name = f"soil_{prop}_{fname}.tif"
        try:
            arr, tr, crs, info = fetch_wcs(prop, depth_id)
            arr = arr.astype("float32")
            arr[arr <= 0] = np.nan  # 0 = WCS background outside the soil mask
            out = reproject_to_grid(arr, tr, crs, Resampling.bilinear,
                                    src_nodata=np.nan, dst_nodata=np.nan)
            out[(out < 0) | (out > 20000)] = np.nan
            valid = np.isfinite(out)
            gap_frac = float(1.0 - valid.mean())
            # WCS output contains no-data streaks from server-side warping/masking.
            # Fill them from the nearest valid 250 m SoilGrids cell; keep the mask.
            if valid.any():
                idx = distance_transform_edt(~valid, return_distances=False, return_indices=True)
                filled = out[tuple(idx)]
            else:
                filled = out
            filled = filled.astype("float32") * SOIL_SCALE[prop]  # to output units
            if name == "soil_sand_0_5.tif":
                write_tif("soil_nodata_mask.tif", (~valid).astype("uint8"), "uint8", 255,
                          "1 = SoilGrids WCS no-data pixel (gap-filled in soil_*.tif)",
                          {"source": "ISRIC SoilGrids v2.0 WCS", "classes": "0=valid, 1=nodata"})
                STATUS["layers"]["soil_nodata_mask.tif"] = {
                    "source": "Derived from SoilGrids WCS output",
                    "crs": DST_CRS, "res_m": RES, "units": "0/1",
                    "nodata_px": int((~valid).sum()), "nodata_fraction": round(gap_frac, 5),
                }
            write_tif(name, filled, "float32", np.nan,
                      f"SoilGrids 250m {SOIL_LONG[prop]} {d0}-{d1} cm ({SOIL_UNITS[prop]})",
                      {"source": "ISRIC SoilGrids v2.0 WCS", "coverage_id": info["coverage_id"],
                       "unit": SOIL_UNITS[prop], "source_unit": SOIL_SRC_UNITS[prop],
                       "depth_cm": f"{d0}-{d1}",
                       "native_res_m": "250", "resampling": "bilinear 250m -> 10m",
                       "gap_fill": "nearest valid SoilGrids cell"})
            ARRAYS[name] = filled
            STATUS["layers"][name] = {
                "source": "ISRIC SoilGrids v2.0 WCS GetCoverage",
                "url": info["url"], "coverage_id": info["coverage_id"],
                "units": SOIL_UNITS[prop], "source_units": SOIL_SRC_UNITS[prop],
                "unit_scale_applied": SOIL_SCALE[prop],
                "depth_cm": f"{d0}-{d1}",
                "crs": DST_CRS, "res_m": RES, "native_res_m": 250,
                "background_masked": 0, "gap_filled_fraction": round(gap_frac, 5),
                "stats": stats(filled),
            }
        except Exception as exc:  # noqa: BLE001
            print(f"  WCS FAILED {name}: {exc}")
            STATUS["failures"].append({"layer": name, "error": str(exc)})

# --------------------------------------------------------------------------- #
# 2. ESA WorldCover 2021 v200, 10 m, tile N42E021
# --------------------------------------------------------------------------- #
WC_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
          "ESA_WorldCover_10m_2021_v200_N42E021_Map.tif")
print("reading ESA WorldCover N42E021 window ...")
wc_pad = 0.02  # padded window so the reprojected UTM grid is fully covered
with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
    with rasterio.open(WC_URL) as src:
        from rasterio.windows import from_bounds
        win = from_bounds(W - wc_pad, S - wc_pad, E + wc_pad, N + wc_pad, src.transform)
        wc = src.read(1, window=win)
        wc_tr = rasterio.windows.transform(win, src.transform)
        wc_crs = src.crs
        wc_native = src.res[0]
wc10 = reproject_to_grid(wc, wc_tr, wc_crs, Resampling.nearest,
                         src_nodata=0, dst_dtype="uint8", dst_nodata=0)
write_tif("worldcover_aoi.tif", wc10, "uint8", 0,
          "ESA WorldCover 2021 v200 land cover class (nearest resampled to 10m UTM34N)",
          {"source": "ESA WorldCover 2021 v200", "tile": "N42E021",
           "native_res_m": "10", "resampling": "nearest 4326/10m -> 32634/10m"})
classes, counts = np.unique(wc10[wc10 > 0], return_counts=True)
ARRAYS["worldcover_aoi.tif"] = wc10
STATUS["layers"]["worldcover_aoi.tif"] = {
    "source": "ESA WorldCover 2021 v200 (CC BY 4.0)",
    "url": WC_URL, "tile": "N42E021", "crs": DST_CRS, "res_m": RES,
    "native_res_m": 10, "native_crs": "EPSG:4326",
    "resampling": "nearest", "crs_note": "reprojected from native EPSG:4326 10m",
    "class_pixel_counts": {int(c): int(n) for c, n in zip(classes, counts)},
    "class_area_km2": {int(c): round(float(n) * RES * RES / 1e6, 4) for c, n in zip(classes, counts)},
    "stats": {"valid_px": int((wc10 > 0).sum()), "min": int(classes.min()),
              "max": int(classes.max())},
}

# --------------------------------------------------------------------------- #
# 3. Copernicus DEM GLO-30 + slope
# --------------------------------------------------------------------------- #
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_N42_00_E023_00_DEM/"
           "Copernicus_DSM_COG_10_N42_00_E023_00_DEM.tif")
print("reading Copernicus DEM window ...")
pad_deg = 0.01
with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
    with rasterio.open(DEM_URL) as src:
        from rasterio.windows import from_bounds
        win = from_bounds(W - pad_deg, S - pad_deg, E + pad_deg, N + pad_deg, src.transform)
        dem_raw = src.read(1, window=win)
        dem_tr = rasterio.windows.transform(win, src.transform)
        dem_crs = src.crs
        dem_native = src.res[0]

dem_raw = dem_raw.astype("float32")
dem_raw[dem_raw < -1000] = np.nan

# DEM on the common 10 m grid (bilinear from native ~30 m DSM)
dem10 = reproject_to_grid(dem_raw, dem_tr, dem_crs, Resampling.bilinear,
                          src_nodata=np.nan, dst_nodata=np.nan)
write_tif("dem_aoi.tif", dem10, "float32", np.nan,
          "Copernicus DEM GLO-30 elevation (EGM2008, metres) bilinear to 10m UTM34N",
          {"source": "Copernicus DEM GLO-30", "tile": "N42E023",
           "native_res_m": "30", "vertical_datum": "EGM2008",
           "resampling": "bilinear 4326/30m -> 32634/10m"})
ARRAYS["dem_aoi.tif"] = dem10
STATUS["layers"]["dem_aoi.tif"] = {
    "source": "Copernicus DEM GLO-30 (ESA 2021)",
    "url": DEM_URL, "tile": "N42E023", "crs": DST_CRS, "res_m": RES,
    "native_res_m": 30, "native_crs": "EPSG:4326",
    "vertical_datum": "EGM2008 geoid", "units": "m",
    "resampling": "bilinear", "stats": stats(dem10),
}

# slope on native-ish 30 m grid, then bilinear to the 10 m common grid
buf = 120.0
sxmin = math.floor((_b[0] - buf) / 30.0) * 30.0
sxmax = math.ceil((_b[2] + buf) / 30.0) * 30.0
symin = math.floor((_b[1] - buf) / 30.0) * 30.0
symax = math.ceil((_b[3] + buf) / 30.0) * 30.0
s_tr = from_origin(sxmin, symax, 30.0, 30.0)
s_shape = (int(round((symax - symin) / 30.0)), int(round((sxmax - sxmin) / 30.0)))
dem30 = np.full(s_shape, np.nan, dtype="float32")
reproject(source=dem_raw, destination=dem30, src_transform=dem_tr, src_crs=dem_crs,
          dst_transform=s_tr, dst_crs=DST_CRS, src_nodata=np.nan, dst_nodata=np.nan,
          resampling=Resampling.bilinear)

z = dem30.astype("float64")
dzdx = np.full_like(z, np.nan)
dzdy = np.full_like(z, np.nan)
dzdx[1:-1, 1:-1] = (
    (z[1:-1, 2:] + 2 * z[2:, 2:] + z[:-2, 2:])
    - (z[1:-1, :-2] + 2 * z[2:, :-2] + z[:-2, :-2])
) / (8.0 * 30.0)
dzdy[1:-1, 1:-1] = (
    (z[:-2, 1:-1] + 2 * z[:-2, 2:] + z[:-2, :-2])
    - (z[2:, 1:-1] + 2 * z[2:, 2:] + z[2:, :-2])
) / (8.0 * 30.0)
slope30 = np.degrees(np.arctan(np.hypot(dzdx, dzdy))).astype("float32")

slope10 = np.full(DST_SHAPE, np.nan, dtype="float32")
reproject(source=slope30, destination=slope10, src_transform=s_tr, src_crs=DST_CRS,
          dst_transform=TRANSFORM, dst_crs=DST_CRS, src_nodata=np.nan, dst_nodata=np.nan,
          resampling=Resampling.bilinear)
slope10[(slope10 < 0) | (slope10 > 90)] = np.nan
write_tif("slope_aoi.tif", slope10, "float32", np.nan,
          "Slope in degrees (Horn 3x3 on 30m Copernicus DSM, bilinear to 10m)",
          {"source": "Copernicus DEM GLO-30", "method": "Horn 3x3, 30m grid",
           "units": "degrees", "resampling": "bilinear 30m -> 10m"})
ARRAYS["slope_aoi.tif"] = slope10
STATUS["layers"]["slope_aoi.tif"] = {
    "source": "Derived from Copernicus DEM GLO-30",
    "url": DEM_URL, "method": "Horn (1981) 3x3 kernel on 30m UTM34N grid, then bilinear to 10m",
    "crs": DST_CRS, "res_m": RES, "units": "degrees",
    "note": "DSM-based slope includes vegetation/buildings", "stats": stats(slope10),
}

# --------------------------------------------------------------------------- #
# 4. OSM buildings / roads + distance-to-built-up
# --------------------------------------------------------------------------- #
OVERPASS = "https://overpass-api.de/api/interpreter"
OSM_QUERY = (f"[out:json][timeout:180];"
             f"(way[\"building\"]({S},{W},{N},{E});"
             f"way[\"highway\"]({S},{W},{N},{E}););out geom;")
print("querying Overpass for buildings and roads ...")
osm = None
for attempt in range(3):
    try:
        r = requests.get(OVERPASS, params={"data": OSM_QUERY},
                         headers={"User-Agent": "TerraGuard-Research/0.1 (NASA Space Apps)"},
                         timeout=240)
        if r.status_code == 200:
            osm = r.json()
            break
        print(f"  Overpass HTTP {r.status_code}: {r.text[:200]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  Overpass error: {exc}")
    time.sleep(5 * (attempt + 1))

if osm:
    import geopandas as gpd
    from shapely.geometry import LineString, Polygon, shape
    from shapely.validation import make_valid

    bld, roads = [], []
    for el in osm.get("elements", []):
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        coords = [(p["lon"], p["lat"]) for p in el["geometry"] if "lon" in p and "lat" in p]
        if len(coords) < 2:
            continue
        tags = el.get("tags", {})
        rec = {"osm_id": el["id"]}
        if "building" in tags:
            geom = Polygon(coords) if coords[0] == coords[-1] and len(coords) >= 4 else LineString(coords)
            try:
                geom = make_valid(geom)
            except Exception:  # noqa: BLE001
                pass
            rec["geometry"] = geom
            rec["building"] = tags.get("building", "yes")
            bld.append(rec)
        if "highway" in tags:
            rec2 = {"osm_id": el["id"], "highway": tags.get("highway", "yes"),
                    "name": tags.get("name"), "geometry": LineString(coords)}
            roads.append(rec2)

    gb = gpd.GeoDataFrame(bld, geometry="geometry", crs="EPSG:4326") if bld else None
    gr = gpd.GeoDataFrame(roads, geometry="geometry", crs="EPSG:4326") if roads else None
    if gb is not None:
        gb.to_file(OUT / "osm_buildings.geojson", driver="GeoJSON")
    if gr is not None:
        gr.to_file(OUT / "osm_roads.geojson", driver="GeoJSON")
    print(f"  OSM buildings={0 if gb is None else len(gb)}, roads={0 if gr is None else len(gr)}")

    def burn(gdf) -> np.ndarray:
        if gdf is None or len(gdf) == 0:
            return np.zeros(DST_SHAPE, dtype="uint8")
        g = gdf.to_crs(DST_CRS)
        shapes = ((geom, 1) for geom in g.geometry if geom is not None and not geom.is_empty)
        return rasterize(shapes, out_shape=DST_SHAPE, transform=TRANSFORM,
                         fill=0, all_touched=True, dtype="uint8")

    built_mask = burn(gb)
    dist_built = distance_transform_edt(built_mask == 0, sampling=(RES, RES)).astype("float32")
    write_tif("dist_built_aoi.tif", dist_built, "float32", -9999.0,
              "Euclidean distance to nearest OSM building footprint (m)",
              {"source": "OpenStreetMap via Overpass API", "query_date": STATUS["generated_utc"],
               "units": "m", "method": "rasterize buildings, scipy distance_transform_edt"})
    ARRAYS["dist_built_aoi.tif"] = dist_built
    STATUS["layers"]["dist_built_aoi.tif"] = {
        "source": "OpenStreetMap contributors (ODbL) via Overpass API",
        "query": OSM_QUERY, "crs": DST_CRS, "res_m": RES, "units": "m",
        "n_buildings": 0 if gb is None else int(len(gb)),
        "n_road_ways": 0 if gr is None else int(len(gr)),
        "road_length_km": 0.0 if gr is None else round(float(gr.to_crs(DST_CRS).length.sum() / 1000), 3),
        "stats": stats(dist_built),
    }

    road_mask = burn(gr)
    dist_road = distance_transform_edt(road_mask == 0, sampling=(RES, RES)).astype("float32")
    write_tif("dist_road_aoi.tif", dist_road, "float32", -9999.0,
              "Euclidean distance to nearest OSM road (m)",
              {"source": "OpenStreetMap via Overpass API", "units": "m"})
    ARRAYS["dist_road_aoi.tif"] = dist_road
    STATUS["layers"]["dist_road_aoi.tif"] = {
        "source": "OpenStreetMap contributors (ODbL) via Overpass API",
        "crs": DST_CRS, "res_m": RES, "units": "m",
        "stats": stats(dist_road),
    }
else:
    STATUS["failures"].append({"layer": "osm", "error": "Overpass API unavailable"})
    print("  OSM layer skipped")

# --------------------------------------------------------------------------- #
# 5. Metadata
# --------------------------------------------------------------------------- #
with open(OUT / "layers_metadata.json", "w") as f:
    json.dump(STATUS, f, indent=2, default=str)
print("wrote layers_metadata.json")
print("done")
