"""Build the TerraGuard platform dataset from the bundled case outputs.

Outputs a single static contract under ``app/data/``:

    sites.json                     site registry + metrics + caveats
    <site>/meta.json               layers, bounds, timeline, sources
    <site>/network.geojson         pipes (simplified, WGS84)
    <site>/events.geojson          labels / repairs / candidate hotspots
    <site>/hotspots.geojson        ranked candidates
    <site>/overlay_*.png           leak / moisture / persistence rasters
    <site>/stats.json              small charts for the site panel

Everything is generated from the four case outputs already in this bundle.
Coryell is a normal Sentinel-1 case; its source vectors are fetched and
prepared by ``scripts/fetch_coryell.py`` and ``case_studies/prepare_coryell.py``.

Usage (from chris-results/):
    python scripts/build_platform_data.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from pyproj import Transformer
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
DATA = APP / "data"
OUT = ROOT / "outputs"
CASE = ROOT / "case_studies"

# --------------------------------------------------------------------------- helpers


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def round_coords(obj, nd=6):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, (list, tuple)):
        return [round_coords(v, nd) for v in obj]
    if isinstance(obj, dict):
        return {k: round_coords(v, nd) for k, v in obj.items()}
    return obj


def write_geojson(gdf: gpd.GeoDataFrame, path: Path, props: list[str] | None = None) -> int:
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if props is not None:
        keep = [c for c in props if c in gdf.columns]
        gdf = gdf[keep + ["geometry"]]
    feats = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        props_d = {}
        for c in gdf.columns:
            if c == "geometry":
                continue
            v = row[c]
            if isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating,)):
                v = None if not np.isfinite(v) else float(v)
            elif isinstance(v, (pd.Timestamp,)):
                v = v.strftime("%Y-%m-%d")
            elif pd.isna(v):
                v = None
            props_d[c] = v
        feats.append({"type": "Feature", "properties": props_d,
                      "geometry": round_coords(mapping(geom))})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                               separators=(",", ":")), encoding="utf-8")
    return len(feats)


def projected(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        return gdf.set_crs(4326)
    return gdf.to_crs(4326)


def simplify_network(path: Path, out: Path, tol_m: float = 1.0, props: list[str] | None = None) -> int:
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    utm = gdf.estimate_utm_crs()
    metric = gdf.to_crs(utm)
    metric["geometry"] = metric.geometry.simplify(tol_m, preserve_topology=True)
    gdf = metric.to_crs(4326)
    return write_geojson(gdf, out, props)


# --------------------------------------------------------------------------- rasters
CMAPS = {
    "leak": ("inferno", 0.0, 100.0, "Leak likelihood", "0-100"),
    "moisture": ("RdBu_r", -2.5, 2.5, "Moisture anomaly (robust z)", "z"),
    "persistence": ("viridis", 0.0, 1.0, "Dry-season persistence", "fraction"),
    "nisar": ("gray", 0.0, 255.0, "NISAR HH browse (display only)", "DN"),
}


def raster_to_png(tif: Path, out: Path, kind: str, max_px: int = 1400) -> dict | None:
    if not tif.exists():
        return None
    with rasterio.open(tif) as ds:
        scale = max(ds.width, ds.height) / max_px
        h = max(2, int(round(ds.height / max(scale, 1e-9))))
        w = max(2, int(round(ds.width / max(scale, 1e-9))))
        arr = ds.read(1, out_shape=(h, w), resampling=rasterio.enums.Resampling.average).astype("float32")
        nodata = ds.nodata
        bounds = ds.bounds
        src_crs = ds.crs
    if nodata is not None:
        arr[arr == nodata] = np.nan
    arr[~np.isfinite(arr)] = np.nan

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cmap_name, vmin, vmax, label, unit = CMAPS[kind]
    if kind == "leak" and np.isfinite(arr).any():
        # The absolute 0-100 score has very different distributions per site.
        # Stretch the display to the site's median..p99 so the top evidence is
        # visible; the evidence panel still reports the absolute score.
        vmin = float(np.nanpercentile(arr, 50))
        vmax = float(np.nanpercentile(arr, 99))
        if not np.isfinite(vmax) or vmax <= vmin:
            vmin, vmax = 0.0, 100.0
    cmap = plt.get_cmap(cmap_name)
    norm = np.clip((arr - vmin) / (vmax - vmin), 0, 1)
    norm = np.nan_to_num(norm, nan=0.0)
    rgba = (cmap(norm) * 255).astype(np.uint8)
    mask = np.isfinite(arr)
    if kind == "leak":
        # Fade the low end so the basemap remains readable.
        rgba[..., 3] = (np.clip((norm - 0.05) / 0.95, 0, 1) ** 0.8 * 220).astype(np.uint8)
    elif kind == "moisture":
        rgba[..., 3] = (np.clip(np.abs(norm - 0.5) * 2, 0, 1) ** 0.75 * 200).astype(np.uint8)
    elif kind == "nisar":
        rgba[..., 3] = (np.clip(norm * 1.1, 0, 1) * 170).astype(np.uint8)
    else:
        rgba[..., 3] = (np.clip(norm * 1.15, 0, 1) * 205).astype(np.uint8)
    rgba[~mask, 3] = 0
    Image.fromarray(rgba, "RGBA").save(out, optimize=True)

    tr = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
    lons, lats = [], []
    for x, y in ((bounds.left, bounds.bottom), (bounds.left, bounds.top),
                 (bounds.right, bounds.bottom), (bounds.right, bounds.top)):
        lon, lat = tr.transform(x, y)
        lons.append(lon)
        lats.append(lat)
    return {
        "file": out.name,
        "bounds": [min(lons), min(lats), max(lons), max(lats)],
        "label": label,
        "unit": unit,
        "kind": kind,
        "vmin": float(vmin),
        "vmax": float(vmax),
    }


def overlay_layers(site_root: Path, out_dir: Path) -> list[dict]:
    """Render the three evidence layers for one site."""
    src = {
        "leak": site_root / "outputs" / "leak_likelihood.tif",
        "moisture": site_root / "outputs" / "moisture_smooth_z.tif",
        "persistence": site_root / "outputs" / "persistence.tif",
    }
    layers = []
    for kind, tif in src.items():
        meta = raster_to_png(tif, out_dir / f"overlay_{kind}.png", kind)
        if meta:
            layers.append(meta)
    # Public NISAR browse is available for the Bulgarian AOI only. It is
    # display-only: 8-bit quicklook, not calibrated gamma0, with km-scale
    # geolocation error. Keep it out of every quantitative claim.
    if site_root == ROOT:
        nisar = raster_to_png(ROOT / "data" / "raw" / "nisar" / "nisar_hh_latest.tif",
                              out_dir / "overlay_nisar.png", "nisar")
        if nisar:
            layers.append(nisar)
    return layers


# --------------------------------------------------------------------------- metrics


def metrics_from_validation(v: dict) -> dict:
    m = v.get("model_metrics", {})
    vv = m.get("vv", {})
    nd = m.get("ndmi", {})
    le = v.get("label_evaluation") or {}
    pe = v.get("pipeline_enrichment") or {}
    out = {
        "vv_r2": vv.get("r2"),
        "vv_mae": vv.get("mae"),
        "ndmi_r2": nd.get("r2"),
        "ndmi_mae": nd.get("mae"),
        "label_auc": le.get("auc"),
        "label_percentile": le.get("median_percentile"),
        "n_labels": le.get("n_labels"),
        "corridor_p": pe.get("p_value"),
        "corridor_p95": pe.get("p_value_p95"),
        "corridor_ratio": pe.get("ratio"),
        "s1_dates": v.get("s1_dates"),
        "dry_season_dates": v.get("dry_season_dates"),
        "pixels": v.get("pixels_valid"),
        "nisar_layer": bool(v.get("nisar_layer_present")),
    }
    return out


# --------------------------------------------------------------------------- site builders
SITE_DIRS = {
    "bulgaria": {
        "root": ROOT,
        "name": "Elin Pelin",
        "subtitle": "Buried water main · Bulgaria",
        "country": "Bulgaria",
        "center": [23.6075, 42.6375],
        "zoom": 13.1,
        "network": ROOT / "data" / "vectors" / "water_main.geojson",
        "labels": None,
        "hotspots": OUT / "hotspots.csv",
        "status": "Unlabelled demonstration",
        "headline": "Weather-normalised Sentinel-1 moisture and thermal anomalies along a 3.3 km rural main.",
        "caveats": [
            "No confirmed leak: this is a screening demonstration.",
            "The corridor enrichment test is not significant (p = 0.89).",
            "NISAR layers here are public 8-bit browse imagery, display-only.",
            "The NISAR browse overlay has kilometre-scale geolocation uncertainty; never use it quantitatively.",
        ],
    },
    "aguascalientes": {
        "root": CASE / "aguascalientes",
        "name": "Aguascalientes",
        "subtitle": "Urban utility network · Mexico",
        "country": "Mexico",
        "center": [-102.2661, 21.8840],
        "zoom": 13.2,
        "network": CASE / "aguascalientes" / "data" / "vectors" / "water_main.geojson",
        "labels": CASE / "aguascalientes" / "data" / "vectors" / "labels.csv",
        "hotspots": CASE / "aguascalientes" / "outputs" / "hotspots.csv",
        "status": "50 repair records",
        "headline": "A dense 5 × 5 km urban network, 28 Sentinel-1 dates and 50 dry-season repairs.",
        "caveats": [
            "Label ranking AUC 0.526: weak positive, not significant.",
            "Repair dates are not leak-start dates.",
            "No NISAR imagery in this case.",
        ],
    },
    "calgary": {
        "root": CASE / "calgary",
        "name": "Calgary",
        "subtitle": "Trunk water network · Canada",
        "country": "Canada",
        "center": [-113.95, 51.05],
        "zoom": 13.0,
        "network": CASE / "calgary" / "data" / "vectors" / "water_main.geojson",
        "labels": CASE / "calgary" / "data" / "vectors" / "labels.csv",
        "hotspots": CASE / "calgary" / "outputs" / "hotspots.csv",
        "status": "48 main breaks",
        "headline": "A 10 × 10 km trunk network, 50 Sentinel-1 dates and 48 breaks across 2025–2026.",
        "caveats": [
            "Label ranking AUC 0.524: weak positive, not significant.",
            "The Sentinel-1 RTC archive here starts April 2025.",
            "No NISAR imagery in this case.",
        ],
    },
    "coryell": {
        "root": CASE / "coryell",
        "name": "Coryell City WSD",
        "subtitle": "Rural water district · Texas, USA",
        "country": "United States",
        "center": [-97.5307, 31.4853],
        "zoom": 13.2,
        "network": CASE / "coryell" / "data" / "vectors" / "water_main.geojson",
        "labels": CASE / "coryell" / "data" / "vectors" / "labels.csv",
        "hotspots": CASE / "coryell" / "outputs" / "hotspots.csv",
        "status": "72 repairs",
        "headline": "A 10 × 10 km rural network, 55 Sentinel-1 dates and 72 summer repairs, run through the same weather-normalised pipeline.",
        "caveats": [
            "Label ranking AUC 0.548: weak positive. Mean corridor p = 0.024, but p95 = 0.24; not a validated detector.",
            "Repair dates are report dates, not leak-start dates.",
            "The source layers have no stated open licence; bundled for the hackathon only.",
        ],
    },
}


def hotspot_events(path: Path) -> gpd.GeoDataFrame:
    df = pd.read_csv(path)
    if df.empty:
        return gpd.GeoDataFrame(columns=["score", "geometry"], geometry="geometry", crs=4326)
    for col in ("top_dates", "top_z"):
        if col in df:
            df[col] = df[col].astype(str)
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=4326)
    return gdf.rename(columns={"leak_score": "score", "moisture_z": "moisture",
                               "thermal_z": "thermal", "dist_water_m": "dist_water",
                               "top_dates": "dates"})


def build_raster_site(site_id: str, cfg: dict) -> dict:
    root = cfg["root"]
    out = DATA / site_id
    out.mkdir(parents=True, exist_ok=True)
    val_path = root / "outputs" / "validation.json"
    val = read_json(val_path, {})
    metrics = metrics_from_validation(val)

    n_net = simplify_network(cfg["network"], out / "network.geojson", 1.2)
    layers = overlay_layers(root, out)

    hotspots = hotspot_events(cfg["hotspots"])
    n_hot = write_geojson(hotspots, out / "hotspots.geojson",
                          ["score", "moisture", "persistence", "thermal", "confidence",
                           "dist_water", "landcover", "dates"])

    events = None
    if cfg["labels"] and Path(cfg["labels"]).exists():
        lab = pd.read_csv(cfg["labels"])
        lon = next(c for c in lab.columns if c.lower() in ("lon", "longitude"))
        lat = next(c for c in lab.columns if c.lower() in ("lat", "latitude"))
        lab = gpd.GeoDataFrame(lab, geometry=gpd.points_from_xy(lab[lon], lab[lat]), crs=4326)
        if "date" in lab:
            lab["year"] = pd.to_datetime(lab["date"], errors="coerce").dt.year
        n_events = write_geojson(lab, out / "events.geojson")
        events = n_events
    else:
        # Unlabelled site: expose the ranked candidates as the interactive points.
        n_events = write_geojson(hotspots, out / "hotspots.geojson",
                                 ["score", "moisture", "persistence", "thermal",
                                  "confidence", "dist_water", "landcover", "dates"])
        events = 0

    label_dates = (pd.to_datetime(pd.read_csv(cfg["labels"])["date"], errors="coerce")
                   if cfg["labels"] else pd.Series(dtype="datetime64[ns]"))
    stats = {
        "network": n_net,
        "events": events,
        "hotspots": n_hot,
        "period": ([str(label_dates.min().date()), str(label_dates.max().date())]
                   if len(label_dates.dropna()) else None),
        "by_year": ({str(k): int(v) for k, v in label_dates.dt.year.value_counts().sort_index().items()}
                    if cfg["labels"] else {}),
        "metrics": metrics,
    }
    (out / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")

    meta = {
        "id": site_id,
        "name": cfg["name"],
        "subtitle": cfg["subtitle"],
        "country": cfg["country"],
        "center": cfg["center"],
        "zoom": cfg["zoom"],
        "kind": "raster",
        "layers": layers,
        "network_file": "network.geojson",
        "events_file": "events.geojson" if events else None,
        "hotspots_file": "hotspots.geojson",
        "stats_file": "stats.json",
        "timeline": {
            "field": "date",
            "min": str(pd.to_datetime(pd.read_csv(cfg["labels"])["date"], errors="coerce").min().date()) if cfg["labels"] else None,
            "max": str(pd.to_datetime(pd.read_csv(cfg["labels"])["date"], errors="coerce").max().date()) if cfg["labels"] else None,
        },
        "sources": [
            "Sentinel-1 RTC (Planetary Computer)",
            "Sentinel-2 L2A NDMI",
            "Landsat C2 L2 LST",
            "ERA5 via Open-Meteo",
            "ESA WorldCover / Copernicus DEM / SoilGrids",
        ],
        "caveats": cfg["caveats"],
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {
        "id": site_id,
        "name": cfg["name"],
        "subtitle": cfg["subtitle"],
        "country": cfg["country"],
        "center": cfg["center"],
        "zoom": cfg["zoom"],
        "kind": "raster",
        "labels": metrics.get("n_labels") or 0,
        "dates": metrics.get("s1_dates") or 0,
        "sensors": ["Sentinel-1", "Sentinel-2", "Landsat", "ERA5"],
        "status": cfg["status"],
        "headline": cfg["headline"],
        "metrics": metrics,
        "caveats": cfg["caveats"],
    }


def main() -> None:
    APP.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    sites = []
    for sid, cfg in SITE_DIRS.items():
        print(f"building {sid} ...")
        sites.append(build_raster_site(sid, cfg))
    (DATA / "sites.json").write_text(json.dumps(sites, indent=2), encoding="utf-8")
    print(f"wrote {DATA / 'sites.json'} ({len(sites)} sites)")


if __name__ == "__main__":
    main()
