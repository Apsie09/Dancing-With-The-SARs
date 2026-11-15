"""Acquire and align multi-sensor data over the AquaGuard study area.

Sources
-------
Sentinel-1 RTC (C-band, gamma0, 10 m)  -> Planetary Computer STAC (SAS-signed)
Sentinel-2 L2A (NDMI, NDVI, SCL)       -> AWS Earth Search (public COGs)
Landsat 8/9 C2 L2 (LST, QA)            -> Planetary Computer STAC (SAS-signed)
ERA5 weather                           -> Open-Meteo archive API
WorldCover / Copernicus DEM            -> public AWS / ESA buckets
OSM pipelines                          -> extracted by scripts/extract_pipelines.py
NISAR GCOV                             -> scripts/nisar_extract.py (separate)

Everything is resampled onto one 20 m EPSG:32634 grid.  The S1 stack is the
backbone: dates are grouped and adjacent RTC tiles are mosaicked.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds
from scipy.ndimage import distance_transform_edt
from tqdm import tqdm

from pipeline.config import (
    AOI,
    ASF_SEARCH,
    DATA,
    END,
    ES_STAC,
    INTERIM,
    LANDSAT_COLLECTION,
    MET,
    OUTPUTS,
    PC_STAC,
    RAW,
    S1_COLLECTION,
    S1_ORBIT_STATE,
    S1_RELATIVE_ORBIT,
    S2_COLLECTION,
    PIPELINE_GEOJSON,
    GAS_GEOJSON,
    CASE_NAME,
    START,
    STATIC,
    VECTORS,
    analysis_grid,
    aoi_bbox,
    aoi_wkt,
    save_grid,
)

os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF,.tiff")



# --------------------------------------------------------------------------- #
# STAC helpers
# --------------------------------------------------------------------------- #
def search_pc(collection: str, datetime_range: str, extra: dict | None = None) -> list[dict]:
    body = {
        "collections": [collection],
        "bbox": aoi_bbox(),
        "datetime": datetime_range,
        "limit": 100,
    }
    if extra:
        body.update(extra)
    items: list[dict] = []
    url = f"{PC_STAC}/search"
    while True:
        r = requests.post(url, json=body, timeout=120)
        r.raise_for_status()
        d = r.json()
        items += d.get("features", [])
        nxt = [l for l in d.get("links", []) if l.get("rel") == "next"]
        if not nxt:
            break
        nbody = nxt[0].get("body")
        if nbody:
            body = nbody
        else:
            body["token"] = nxt[0].get("href")
    return items


def search_es(collection: str, datetime_range: str, extra: dict | None = None) -> list[dict]:
    body = {
        "collections": [collection],
        "bbox": aoi_bbox(),
        "datetime": datetime_range,
        "limit": 100,
    }
    if extra:
        body.update(extra)
    items: list[dict] = []
    url = f"{ES_STAC}/search"
    while True:
        r = requests.post(url, json=body, timeout=120)
        r.raise_for_status()
        d = r.json()
        items += d.get("features", [])
        nxt = [l for l in d.get("links", []) if l.get("rel") == "next"]
        if not nxt:
            break
        nbody = nxt[0].get("body")
        if nbody:
            body = nbody
        else:
            body["token"] = nxt[0].get("href")
    return items


# --------------------------------------------------------------------------- #
# Raster reading
# --------------------------------------------------------------------------- #
def _window_for(ds: rasterio.DatasetReader, bbox4326: list[float]):
    b = transform_bounds("EPSG:4326", ds.crs, *bbox4326, densify_pts=21)
    win = from_bounds(*b, ds.transform).round_offsets().round_lengths()
    return win.intersection(Window(0, 0, ds.width, ds.height))


def read_to_grid(
    url: str,
    grid: dict,
    resampling: Resampling = Resampling.bilinear,
    out_dtype: str = "float32",
) -> np.ndarray | None:
    """Read a remote raster window and reproject it onto the common grid."""
    try:
        with rasterio.open(url) as ds:
            win = _window_for(ds, aoi_bbox())
            if win.width < 1 or win.height < 1:
                return None
            src = ds.read(1, window=win, out_dtype=out_dtype)
            dest = np.full((grid["height"], grid["width"]), np.nan, dtype=out_dtype)
            reproject(
                source=src,
                destination=dest,
                src_transform=ds.window_transform(win),
                src_crs=ds.crs,
                dst_transform=grid["transform"],
                dst_crs=grid["crs"],
                src_nodata=None,
                dst_nodata=np.nan,
                resampling=resampling,
                num_threads=1,
            )
            return dest
    except Exception as exc:  # noqa: BLE001 - remote reads fail in many ways
        print(f"    read failed: {Path(url).name[:60]} :: {type(exc).__name__}: {exc}")
        return None


def _mask_s1(a: np.ndarray) -> np.ndarray:
    a = a.astype("float32")
    a[~np.isfinite(a)] = np.nan
    a[a <= 0] = np.nan
    a[a == -32768] = np.nan
    return a


# --------------------------------------------------------------------------- #
# Sentinel-1 RTC
# --------------------------------------------------------------------------- #
def acquire_s1(grid: dict, workers: int = 8, max_dates: int | None = None) -> None:
    print("S1: searching Planetary Computer ...")
    items = search_pc(
        S1_COLLECTION,
        f"{START}T00:00:00Z/{END}T00:00:00Z",
    )
    items = [
        f
        for f in items
        if f["properties"].get("sat:orbit_state") == S1_ORBIT_STATE
        and f["properties"].get("sat:relative_orbit") == S1_RELATIVE_ORBIT
    ]
    print(f"S1: {len(items)} items on orbit {S1_RELATIVE_ORBIT}/{S1_ORBIT_STATE}")

    by_date: dict[str, list[dict]] = {}
    for f in items:
        date = f["properties"]["datetime"][:10]
        by_date.setdefault(date, []).append(f)
    dates = sorted(by_date)
    if max_dates:
        # keep an even sample across the record for a quick test
        idx = np.linspace(0, len(dates) - 1, min(max_dates, len(dates))).round().astype(int)
        dates = [dates[i] for i in sorted(set(idx))]
    print(f"S1: {len(dates)} unique dates, {len(items)} tiles, workers={workers}")

    import planetary_computer as pc

    def fetch_date(date: str):
        vv_tiles, vh_tiles = [], []
        for f in by_date[date]:
            signed = pc.sign(f)
            for pol, sink in (("vv", vv_tiles), ("vh", vh_tiles)):
                if pol not in signed.get("assets", {}):
                    continue
                a = read_to_grid(signed["assets"][pol]["href"], grid, Resampling.bilinear)
                if a is not None:
                    sink.append(a)
        if not vv_tiles:
            return date, None, None, 0.0
        vv = np.nanmean(np.stack(vv_tiles), axis=0)
        vh = np.nanmean(np.stack(vh_tiles), axis=0)
        vv = _mask_s1(vv)
        vh = _mask_s1(vh)
        with np.errstate(divide="ignore", invalid="ignore"):
            vv_db = 10.0 * np.log10(vv)
            vh_db = 10.0 * np.log10(vh)
        valid = float(np.isfinite(vv_db).mean())
        return date, vv_db, vh_db, valid

    vv_list, vh_list, ok_dates, valid_frac = [], [], [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_date, d): d for d in dates}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="S1"):
            try:
                d, vv, vh, valid = fut.result()
            except Exception as exc:  # noqa: BLE001
                print("S1 date failed", futures[fut], exc)
                continue
            if vv is None or valid < 0.35:
                continue
            vv_list.append(vv.astype("float32"))
            vh_list.append(vh.astype("float32"))
            ok_dates.append(d)
            valid_frac.append(valid)

    order = np.argsort(ok_dates)
    vv = np.stack([vv_list[i] for i in order])
    vh = np.stack([vh_list[i] for i in order])
    dates_arr = np.array([ok_dates[i] for i in order])
    valid_arr = np.array([valid_frac[i] for i in order], dtype="float32")
    platforms = np.array([by_date[d][0]["properties"].get("platform", "?") for d in dates_arr])
    np.savez_compressed(
        RAW / "s1_stack.npz",
        vv=vv,
        vh=vh,
        dates=dates_arr,
        valid=valid_arr,
        platforms=platforms,
    )
    print(f"S1 saved: {vv.shape}, median valid {np.median(valid_arr):.2f}")


# --------------------------------------------------------------------------- #
# Sentinel-2
# --------------------------------------------------------------------------- #
def acquire_s2(grid: dict, workers: int = 8, max_cloud: int = 40, max_dates: int | None = None) -> None:
    print("S2: searching Earth Search ...")
    items = search_es(
        S2_COLLECTION,
        f"{START}T00:00:00Z/{END}T00:00:00Z",
        {"query": {"eo:cloud_cover": {"lt": max_cloud}}},
    )
    # one item per day (prefer lowest cloud)
    best: dict[str, dict] = {}
    for f in items:
        d = f["properties"]["datetime"][:10]
        cc = f["properties"].get("eo:cloud_cover", 999)
        if d not in best or cc < best[d]["properties"].get("eo:cloud_cover", 999):
            best[d] = f
    dates = sorted(best)
    if max_dates and len(dates) > max_dates:
        idx = np.linspace(0, len(dates) - 1, max_dates).round().astype(int)
        dates = [dates[i] for i in sorted(set(idx))]
    print(f"S2: {len(dates)} candidate dates (cloud < {max_cloud}%)")

    def fetch(date: str):
        f = best[date]
        a = f.get("assets", {})
        need = ["nir08", "swir16", "nir", "red", "scl"]
        if any(k not in a for k in need):
            return None
        nir08 = read_to_grid(a["nir08"]["href"], grid, Resampling.bilinear)
        swir16 = read_to_grid(a["swir16"]["href"], grid, Resampling.bilinear)
        nir = read_to_grid(a["nir"]["href"], grid, Resampling.bilinear)
        red = read_to_grid(a["red"]["href"], grid, Resampling.bilinear)
        scl = read_to_grid(a["scl"]["href"], grid, Resampling.nearest)
        if any(x is None for x in (nir08, swir16, nir, red, scl)):
            return None
        scl = np.nan_to_num(scl, nan=0).astype("uint8")

        def refl(x):
            x = x.astype("float32")
            x[~np.isfinite(x)] = np.nan
            x[x <= 0] = np.nan
            return (x - 1000.0) / 10000.0

        n8, s16, n, r = refl(nir08), refl(swir16), refl(nir), refl(red)
        with np.errstate(divide="ignore", invalid="ignore"):
            ndmi = (n8 - s16) / (n8 + s16)
            ndvi = (n - r) / (n + r)
        cloud = np.isin(scl, [3, 8, 9, 10, 11]) | (scl == 0)
        ndmi[cloud] = np.nan
        ndvi[cloud] = np.nan
        frac = float(cloud.mean())
        if frac > 0.65:
            return None
        return date, ndmi.astype("float32"), ndvi.astype("float32"), frac

    ndmi_l, ndvi_l, dates_l, cloud_l = [], [], [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, d) for d in dates]
        for fut in tqdm(as_completed(futures), total=len(futures), desc="S2"):
            try:
                out = fut.result()
            except Exception as exc:  # noqa: BLE001
                print("S2 failed", exc)
                continue
            if out is None:
                continue
            d, ndmi, ndvi, frac = out
            ndmi_l.append(ndmi)
            ndvi_l.append(ndvi)
            dates_l.append(d)
            cloud_l.append(frac)
    order = np.argsort(dates_l)
    np.savez_compressed(
        RAW / "s2_stack.npz",
        ndmi=np.stack([ndmi_l[i] for i in order]),
        ndvi=np.stack([ndvi_l[i] for i in order]),
        dates=np.array([dates_l[i] for i in order]),
        cloud=np.array([cloud_l[i] for i in order], dtype="float32"),
    )
    print(f"S2 saved: {len(dates_l)} dates")


# --------------------------------------------------------------------------- #
# Landsat thermal
# --------------------------------------------------------------------------- #
def acquire_landsat(grid: dict, workers: int = 6, max_cloud: int = 40, max_dates: int | None = None) -> None:
    print("Landsat: searching Planetary Computer ...")
    items = search_pc(
        LANDSAT_COLLECTION,
        f"{START}/{END}",
        {"query": {"eo:cloud_cover": {"lt": max_cloud}}},
    )
    best: dict[str, dict] = {}
    for f in items:
        d = f["properties"]["datetime"][:10]
        cc = f["properties"].get("eo:cloud_cover", 999)
        if d not in best or cc < best[d]["properties"].get("eo:cloud_cover", 999):
            best[d] = f
    dates = sorted(best)
    if max_dates and len(dates) > max_dates:
        idx = np.linspace(0, len(dates) - 1, max_dates).round().astype(int)
        dates = [dates[i] for i in sorted(set(idx))]
    print(f"Landsat: {len(dates)} candidate dates (cloud < {max_cloud}%)")

    import planetary_computer as pc

    def fetch(date: str):
        f = pc.sign(best[date])
        a = f.get("assets", {})
        if "lwir11" not in a or "qa_pixel" not in a:
            return None
        lst_dn = read_to_grid(a["lwir11"]["href"], grid, Resampling.bilinear)
        qa = read_to_grid(a["qa_pixel"]["href"], grid, Resampling.nearest)
        if lst_dn is None or qa is None:
            return None
        qa = np.nan_to_num(qa, nan=0).astype("uint16")
        cloud = (qa & ((1 << 1) | (1 << 3) | (1 << 4))) != 0
        cloud |= qa == 0
        lst = lst_dn.astype("float32") * 0.00341802 + 149.0 - 273.15
        lst[cloud] = np.nan
        frac = float(cloud.mean())
        if frac > 0.65:
            return None
        return date, lst.astype("float32"), frac

    lst_l, dates_l, cloud_l = [], [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, d) for d in dates]
        for fut in tqdm(as_completed(futures), total=len(futures), desc="LST"):
            try:
                out = fut.result()
            except Exception as exc:  # noqa: BLE001
                print("Landsat failed", exc)
                continue
            if out is None:
                continue
            d, lst, frac = out
            lst_l.append(lst)
            dates_l.append(d)
            cloud_l.append(frac)
    order = np.argsort(dates_l)
    np.savez_compressed(
        RAW / "lst_stack.npz",
        lst=np.stack([lst_l[i] for i in order]) if lst_l else np.empty((0, grid["height"], grid["width"])),
        dates=np.array([dates_l[i] for i in order]),
        cloud=np.array([cloud_l[i] for i in order], dtype="float32"),
    )
    print(f"Landsat saved: {len(dates_l)} dates")


# --------------------------------------------------------------------------- #
# Weather (fallback if the static/weather agent has not produced the file)
# --------------------------------------------------------------------------- #
def acquire_weather() -> None:
    out = MET / "weather_daily.csv"
    if out.exists():
        print("Weather: using", out)
        return
    print("Weather: fetching Open-Meteo ERA5 archive ...")
    hourly = [
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
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": AOI["center_lat"],
        "longitude": AOI["center_lon"],
        "start_date": "2022-01-01",
        "end_date": "2026-11-14",
        "hourly": ",".join(hourly),
        "timezone": "UTC",
    }
    r = requests.get(url, params=params, timeout=180)
    r.raise_for_status()
    d = r.json()
    h = d["hourly"]
    df = pd.DataFrame({"time": pd.to_datetime(h["time"])})
    for k in hourly:
        if k in h:
            df[k] = h[k]
    df = df.set_index("time")
    daily = pd.DataFrame(
        {
            "precip_sum": df["precipitation"].resample("1D").sum(),
            "temp_mean": df["temperature_2m"].resample("1D").mean(),
            "temp_min": df["temperature_2m"].resample("1D").min(),
            "temp_max": df["temperature_2m"].resample("1D").max(),
            "rh_mean": df["relative_humidity_2m"].resample("1D").mean(),
            "radiation_sum": df["shortwave_radiation"].resample("1D").sum(),
            "et0_sum": df["et0_fao_evapotranspiration"].resample("1D").sum(),
            "sm0_7": df["soil_moisture_0_to_7cm"].resample("1D").mean(),
            "sm7_28": df["soil_moisture_7_to_28cm"].resample("1D").mean(),
            "sm28_100": df["soil_moisture_28_to_100cm"].resample("1D").mean(),
            "vpd_mean": df["vapor_pressure_deficit"].resample("1D").mean(),
            "wind_mean": df["wind_speed_10m"].resample("1D").mean(),
        }
    )
    daily.index.name = "date"
    daily.round(4).to_csv(out)
    print("Weather saved", out, daily.shape)


# --------------------------------------------------------------------------- #
# Static layers (fallback copies; agent work preferred)
# --------------------------------------------------------------------------- #
def _crop_public(url: str, out: Path, resampling: Resampling = Resampling.nearest) -> None:
    if out.exists():
        print("Static exists", out)
        return
    a = read_to_grid(url, analysis_grid(), resampling)
    if a is None:
        print("Static FAILED", url)
        return
    g = analysis_grid()
    with rasterio.open(
        out,
        "w",
        driver="GTiff",
        height=g["height"],
        width=g["width"],
        count=1,
        dtype="float32",
        crs=g["crs"],
        transform=g["transform"],
        compress="deflate",
        nodata=np.nan,
    ) as ds:
        ds.write(a.astype("float32"), 1)
    print("Static saved", out)


def _tile_name(lat: float, lon: float, degrees: int) -> str:
    lat0 = int(np.floor(lat / degrees) * degrees)
    lon0 = int(np.floor(lon / degrees) * degrees)
    ns = "N" if lat0 >= 0 else "S"
    ew = "E" if lon0 >= 0 else "W"
    return f"{ns}{abs(lat0):02d}{ew}{abs(lon0):03d}"


def _dem_tile_name(lat: float, lon: float) -> str:
    """Copernicus DEM 30 m COG tile names use N31_00_W098_00, not N31W098."""
    lat0 = int(np.floor(lat))
    lon0 = int(np.floor(lon))
    ns = "N" if lat0 >= 0 else "S"
    ew = "E" if lon0 >= 0 else "W"
    return f"{ns}{abs(lat0):02d}_00_{ew}{abs(lon0):03d}_00"


def acquire_static() -> None:
    # WorldCover 3x3 degree tiles and Copernicus DEM 1x1 degree tiles.
    wc = _tile_name(AOI["south"], AOI["west"], 3)
    dem = _dem_tile_name(AOI["south"], AOI["west"])
    _crop_public(
        f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{wc}_Map.tif",
        STATIC / "worldcover_aoi.tif",
        Resampling.nearest,
    )
    _crop_public(
        f"https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{dem}_DEM/Copernicus_DSM_COG_10_{dem}_DEM.tif",
        STATIC / "dem_aoi.tif",
        Resampling.bilinear,
    )
    slope_path = STATIC / "slope_aoi.tif"
    if not slope_path.exists() and (STATIC / "dem_aoi.tif").exists():
        with rasterio.open(STATIC / "dem_aoi.tif") as ds:
            dem = ds.read(1).astype("float32")
            gy, gx = np.gradient(dem, abs(ds.transform.e), ds.transform.a)
            slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
            profile = ds.profile.copy()
            profile.update(dtype="float32", count=1, compress="deflate", nodata=np.nan)
        with rasterio.open(slope_path, "w", **profile) as out:
            out.write(slope, 1)
        print("slope saved", slope_path)


# --------------------------------------------------------------------------- #
# Pipeline corridor priors
# --------------------------------------------------------------------------- #
def make_corridors(grid: dict) -> None:
    import geopandas as gpd

    g = analysis_grid()
    jobs = [("water_main", PIPELINE_GEOJSON)]
    if GAS_GEOJSON and Path(GAS_GEOJSON).exists():
        jobs.append(("gas", GAS_GEOJSON))
    if (VECTORS / "water_pipelines.geojson").exists():
        jobs.append(("water", VECTORS / "water_pipelines.geojson"))
    for name, path in jobs:
        if not path or not Path(path).exists():
            print("corridor missing", path)
            continue
        gdf = gpd.read_file(path).to_crs(g["crs"])
        if name == "gas" and "substance" in gdf.columns:
            gdf = gdf[gdf["substance"] == "gas"]
        if not len(gdf):
            continue
        mask = rasterize(
            [(geom, 1) for geom in gdf.geometry],
            out_shape=(g["height"], g["width"]),
            transform=g["transform"],
            fill=0,
            all_touched=True,
            dtype="uint8",
        )
        if mask.max() == 0:
            print("corridor raster empty", name)
            continue
        dist = distance_transform_edt(mask == 0, sampling=(g["res"], g["res"]))
        dist = dist.astype("float32")
        out = INTERIM / f"dist_{name}.tif"
        with rasterio.open(
            out,
            "w",
            driver="GTiff",
            height=g["height"],
            width=g["width"],
            count=1,
            dtype="float32",
            crs=g["crs"],
            transform=g["transform"],
            compress="deflate",
        ) as ds:
            ds.write(dist, 1)
        print(f"corridor {name}: {int(mask.sum())} px, max dist {dist.max():.0f} m -> {out}")


# --------------------------------------------------------------------------- #
def manifest() -> None:
    meta = {
        "case": CASE_NAME,
        "aoi": AOI,
        "s1_orbit": [S1_RELATIVE_ORBIT, S1_ORBIT_STATE],
        "generated": datetime.utcnow().isoformat() + "Z",
        "sources": {
            "s1": "Planetary Computer sentinel-1-rtc (C-band gamma0)",
            "s2": "AWS Earth Search sentinel-2-l2a",
            "landsat": "Planetary Computer landsat-c2-l2",
            "weather": "Open-Meteo ERA5 archive",
            "worldcover": "ESA WorldCover 2021 v200",
            "dem": "Copernicus DEM GLO-30",
            "nisar": "ASF NISAR GCOV (public)",
        },
    }
    (RAW / "manifest.json").write_text(json.dumps(meta, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["s1", "s2", "lst", "weather", "static", "corridors"], default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-s1-dates", type=int, default=None)
    ap.add_argument("--max-s2-dates", type=int, default=220)
    ap.add_argument("--max-lst-dates", type=int, default=120)
    args = ap.parse_args()

    grid = save_grid()
    if args.only in (None, "static"):
        acquire_static()
    if args.only in (None, "weather"):
        acquire_weather()
    if args.only in (None, "corridors"):
        make_corridors(grid)
    if args.only in (None, "s1"):
        acquire_s1(grid, args.workers, args.max_s1_dates)
    if args.only in (None, "s2"):
        acquire_s2(grid, args.workers, max_dates=args.max_s2_dates)
    if args.only in (None, "lst"):
        acquire_landsat(grid, args.workers, max_dates=args.max_lst_dates)
    manifest()
    print("done")


if __name__ == "__main__":
    main()
