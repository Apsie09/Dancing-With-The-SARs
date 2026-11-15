"""Build the TerraGuard platform dataset from the bundled case outputs.

Outputs a single static contract under ``app/data/``:

    sites.json                     site registry + metrics + caveats
    <site>/meta.json               layers, bounds, timeline, sources
    <site>/network.geojson         pipes (simplified, WGS84)
    <site>/events.geojson          labels / repairs / candidate hotspots
    <site>/hotspots.geojson        ranked candidates (raster cases)
    <site>/zones.geojson           pressure zones (Coryell)
    <site>/overlay_*.png           leak / moisture / persistence rasters
    <site>/stats.json              small charts for the site panel

Everything is generated from files already in this bundle, plus the public
Coryell ArcGIS vectors fetched by ``scripts/fetch_coryell.py``.

Usage (from chris-results/):
    python scripts/build_platform_data.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from pyproj import Transformer
from shapely.geometry import mapping
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

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
    cmap = plt.get_cmap(cmap_name)
    norm = np.clip((arr - vmin) / (vmax - vmin), 0, 1)
    norm = np.nan_to_num(norm, nan=0.0)
    rgba = (cmap(norm) * 255).astype(np.uint8)
    mask = np.isfinite(arr)
    if kind == "leak":
        # Fade the low end so the basemap remains readable.
        rgba[..., 3] = (np.clip((norm - 0.35) / 0.65, 0, 1) ** 0.9 * 220).astype(np.uint8)
    elif kind == "moisture":
        rgba[..., 3] = (np.clip(np.abs(norm - 0.5) * 2, 0, 1) ** 0.75 * 200).astype(np.uint8)
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


# --------------------------------------------------------------------------- Coryell


def _parse_size(text) -> float:
    if text is None:
        return np.nan
    s = str(text).replace('"', "").strip()
    try:
        return float(s)
    except ValueError:
        return np.nan


def _parse_loss(text) -> float:
    if text is None:
        return np.nan
    s = str(text).lower().replace(",", "")
    import re

    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return np.nan
    return float(m.group(1))


def load_coryell():
    leaks = gpd.read_file(ROOT / "data" / "coryell" / "leak_survey.geojson").to_crs(32614)
    leaks = leaks[leaks["ObjectId"] != 1611].copy()
    leaks["dt"] = pd.to_datetime(leaks["datetime"], unit="ms", utc=True, errors="coerce")
    leaks = leaks[leaks["dt"].notna()].copy()
    leaks["date"] = leaks["dt"].dt.strftime("%Y-%m-%d")
    leaks["size_in"] = leaks["line_size"].map(_parse_size)
    leaks["loss_gpm"] = leaks["approximate_water_loss_gpm"].map(_parse_loss)
    leaks["cause"] = leaks["cause_of_leak"].fillna("Unknown")
    leaks["zone"] = leaks["what_pressure_plane_did_the_lea"].fillna("Unknown")
    leaks["repair"] = leaks["type_of_repair"].fillna("Unknown")
    leaks = leaks.sort_values("dt").reset_index(drop=True)
    return leaks


def assign_pipes(leaks: gpd.GeoDataFrame, pipes: gpd.GeoDataFrame) -> pd.DataFrame:
    """Nearest pipe within 60 m; returns leak row -> pipe id."""
    joined = gpd.sjoin_nearest(
        leaks[["ObjectId", "geometry"]],
        pipes[["pipe_id", "geometry"]],
        how="left", max_distance=60, distance_col="snap_m",
    ).drop_duplicates("ObjectId")
    return joined[["ObjectId", "pipe_id", "snap_m"]]


def coryell_risk(leaks: gpd.GeoDataFrame, pipes: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict, dict]:
    """Temporal validation: pre-2023 conditions -> 2023-24 target, scored on 2025-26."""
    from scipy.spatial import cKDTree

    pipes = pipes.copy()
    pipes["pipe_id"] = np.arange(len(pipes))
    pipes["length_m"] = pipes.geometry.length
    pipes["diameter"] = pd.to_numeric(pipes["Diameter"], errors="coerce")
    pipes["diameter"] = pipes["diameter"].fillna(pipes["diameter"].median())
    pipes["year"] = pd.to_numeric(pipes["Year"], errors="coerce")
    pipes["year_missing"] = pipes["year"].isna().astype(int)
    pipes["material_pvc"] = (pipes["Material"].fillna("").str.upper() == "PVC").astype(int)
    mid = pipes.geometry.interpolate(0.5, normalized=True)
    pipes["mx"], pipes["my"] = mid.x, mid.y
    blk = 2000.0
    pipes["block"] = ((pipes["mx"] // blk).astype(int).astype(str) + "_" +
                      (pipes["my"] // blk).astype(int).astype(str))

    link = assign_pipes(leaks, pipes)
    linked = leaks.merge(link, on="ObjectId", how="left")
    linked = linked[linked["pipe_id"].notna()].copy()
    linked["pipe_id"] = linked["pipe_id"].astype(int)

    # Leak points in metric coordinates for neighbourhood counts.
    lx = np.c_[leaks.geometry.x, leaks.geometry.y]
    tree = cKDTree(lx)
    lt = leaks["dt"].astype("int64").to_numpy()

    def features(cutoff: str) -> pd.DataFrame:
        c = pd.Timestamp(cutoff, tz="UTC")
        before = linked[linked["dt"] < c]
        prior = before.groupby("pipe_id").size().rename("prior_leaks")
        last = before.groupby("pipe_id")["dt"].max()
        recent = before[before["dt"] >= c - pd.Timedelta(days=730)].groupby("pipe_id").size().rename("prior_leaks_2y")
        out = pipes[["pipe_id", "length_m", "diameter", "year", "year_missing",
                     "material_pvc", "mx", "my", "block"]].copy()
        out = out.merge(prior, on="pipe_id", how="left").merge(
            recent, on="pipe_id", how="left")
        out[["prior_leaks", "prior_leaks_2y"]] = out[["prior_leaks", "prior_leaks_2y"]].fillna(0)
        last_ns = last.reindex(out["pipe_id"]).astype("int64").to_numpy()
        out["months_since_last"] = (c.value - last_ns) / (30 * 86400 * 1e9)
        out["months_since_last"] = pd.Series(out["months_since_last"]).fillna(999)
        # Neighbourhood: leaks within 500 m of the pipe midpoint before cutoff.
        c_ns = c.value
        c2_ns = (c - pd.Timedelta(days=730)).value
        counts, counts2 = [], []
        for x, y in zip(out["mx"], out["my"]):
            idx = tree.query_ball_point((x, y), 500)
            if idx:
                t = lt[idx]
                counts.append(int((t < c_ns).sum()))
                counts2.append(int(((t < c_ns) & (t >= c2_ns)).sum()))
            else:
                counts.append(0)
                counts2.append(0)
        out["nbr_leaks_500m"] = counts
        out["nbr_leaks_2y_500m"] = counts2
        return out

    def target(cutoff: str, end: str) -> pd.Series:
        c = pd.Timestamp(cutoff, tz="UTC")
        e = pd.Timestamp(end, tz="UTC")
        sel = linked[(linked["dt"] >= c) & (linked["dt"] < e)]
        return pipes["pipe_id"].isin(sel["pipe_id"]).astype(int)

    feats_tr = features("2023-01-01")
    feats_te = features("2025-01-01")
    y_tr = target("2023-01-01", "2025-01-01").to_numpy()
    y_te = target("2025-01-01", "2026-11-12").to_numpy()
    cols = ["length_m", "diameter", "year", "year_missing", "material_pvc",
            "prior_leaks", "prior_leaks_2y", "months_since_last",
            "nbr_leaks_500m", "nbr_leaks_2y_500m"]

    # Drop pipes installed after the evaluation period.
    ok_tr = ~(feats_tr["year"] > 2022)
    ok_te = ~(feats_te["year"] > 2024)
    Xtr, ytr = feats_tr.loc[ok_tr, cols].to_numpy(), y_tr[ok_tr.to_numpy()]
    Xte, yte = feats_te.loc[ok_te, cols].to_numpy(), y_te[ok_te.to_numpy()]

    model = HistGradientBoostingClassifier(
        learning_rate=0.05, max_iter=250, max_depth=3, min_samples_leaf=25,
        l2_regularization=1.0, random_state=42,
    )
    model.fit(Xtr, ytr)
    p_te = model.predict_proba(Xte)[:, 1]

    # Transparent baseline: recency-weighted prior repairs.
    base_tr = feats_tr.loc[ok_tr, ["prior_leaks", "prior_leaks_2y", "nbr_leaks_2y_500m"]].to_numpy()
    base_te = feats_te.loc[ok_te, ["prior_leaks", "prior_leaks_2y", "nbr_leaks_2y_500m"]].to_numpy()
    bmodel = HistGradientBoostingClassifier(
        learning_rate=0.05, max_iter=120, max_depth=2, min_samples_leaf=40,
        l2_regularization=1.0, random_state=7,
    )
    bmodel.fit(base_tr, ytr)
    p_base = bmodel.predict_proba(base_te)[:, 1]

    def m(y, p):
        top = p >= np.quantile(p, 0.9)
        return {
            "auc": float(roc_auc_score(y, p)),
            "ap": float(average_precision_score(y, p)),
            "top10_capture": float(y[top].sum() / max(y.sum(), 1)),
            "base_rate": float(np.mean(y)),
            "n": int(len(y)),
            "positives": int(np.sum(y)),
        }

    metrics = {
        "link_rate": float(linked["ObjectId"].nunique() / len(leaks)),
        "snap_m_median": float(link["snap_m"].median()),
        "train": {"period": "2023-01-01..2024-12-31", **m(ytr, model.predict_proba(Xtr)[:, 1])},
        "test": {"period": "2025-01-01..2026-11-11", **m(yte, p_te)},
        "baseline_test": {"period": "2025-01-01..2026-11-11", **m(yte, p_base)},
    }

    # Score every pipe with pre-2025 conditions (the model learned on 2023-24).
    all_feats = feats_te.copy()
    all_feats["risk_raw"] = model.predict_proba(all_feats[cols].to_numpy())[:, 1]
    all_feats["risk"] = (all_feats["risk_raw"].rank(pct=True) * 100).round(1)
    all_feats["risk_percentile"] = (all_feats["risk_raw"].rank(pct=True) * 100).round(1)
    # Pipes installed after the evaluation period are not at risk yet.
    new = all_feats["year"] > 2024
    all_feats.loc[new, ["risk", "risk_percentile"]] = np.nan
    risk = all_feats[["pipe_id", "risk", "risk_percentile", "prior_leaks",
                      "prior_leaks_2y", "months_since_last", "nbr_leaks_500m",
                      "nbr_leaks_2y_500m"]]
    return risk, metrics, {"cols": cols, "model": "HistGradientBoostingClassifier"}


def coryell_site() -> dict:
    leaks = load_coryell()
    pipes = gpd.read_file(ROOT / "data" / "coryell" / "waterlines.geojson").to_crs(32614)
    zones = gpd.read_file(ROOT / "data" / "coryell" / "pressure_zones.geojson").to_crs(4326)
    risk, valid, model_meta = coryell_risk(leaks, pipes)

    pipes = pipes.reset_index(drop=True)
    pipes["pipe_id"] = np.arange(len(pipes))
    pipes = pipes.merge(risk, on="pipe_id", how="left")
    pipes = pipes.to_crs(4326)
    pipes["size_label"] = pipes["Size"].fillna("")
    pipes["material"] = pipes["Material"].fillna("Unknown")

    out = DATA / "coryell"
    out.mkdir(parents=True, exist_ok=True)
    n_pipes = write_geojson(
        pipes, out / "network.geojson",
        ["pipe_id", "size_label", "material", "risk", "risk_percentile",
         "prior_leaks", "prior_leaks_2y", "nbr_leaks_2y_500m"],
    )
    pipes[["pipe_id", "size_label", "material", "risk", "risk_percentile",
           "prior_leaks", "prior_leaks_2y", "months_since_last",
           "nbr_leaks_2y_500m"]].sort_values("risk", ascending=False).to_csv(
        out / "risk.csv", index=False)
    write_geojson(zones, out / "zones.geojson", ["Name", "SquareMiles"])

    # Leak points for the map: privacy-safe fields only.
    ev = leaks.copy()
    ev["lon"] = ev.geometry.x
    ev["lat"] = ev.geometry.y
    ev = ev.to_crs(4326)
    ev["lon"], ev["lat"] = ev.geometry.x, ev.geometry.y
    ev["date"] = ev["dt"].dt.strftime("%Y-%m-%d")
    ev["year"] = ev["dt"].dt.year
    ev = ev.rename(columns={"ObjectId": "id", "line_size": "size", "loss_gpm": "loss"})
    ev["cause"] = ev["cause"].fillna("Unknown").astype(str).str.replace("_", " ", regex=False).str.strip()
    ev["repair"] = ev["repair"].fillna("Unknown").astype(str).str.replace("_", " ", regex=False).str.strip()
    ev["zone"] = ev["zone"].fillna("Unknown").astype(str).str.replace("_", " ", regex=False).str.strip()
    n_events = write_geojson(
        ev, out / "events.geojson",
        ["id", "date", "year", "size", "loss", "cause", "repair", "zone", "lon", "lat"],
    )

    # Simple series for the panel.
    by_year = ev.groupby("year").size().to_dict()
    by_cause = ev["cause"].value_counts().to_dict()
    by_size = (ev["size"].fillna("unknown").value_counts().head(8).to_dict())
    by_month = ev.assign(month=ev["dt"].dt.strftime("%Y-%m")).groupby("month").size().to_dict()
    stats = {
        "records": int(len(ev)),
        "pipes": int(n_pipes),
        "zones": int(len(zones)),
        "period": [str(ev["date"].min()), str(ev["date"].max())],
        "nisar_window_records": int((ev["dt"] >= pd.Timestamp("2025-10-17", tz="UTC")).sum()),
        "by_year": {str(k): int(v) for k, v in by_year.items()},
        "by_cause": {str(k): int(v) for k, v in by_cause.items()},
        "by_size": {str(k): int(v) for k, v in by_size.items()},
        "by_month": dict(sorted(by_month.items())),
        "risk_validation": valid,
        "model": model_meta,
    }
    (out / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")

    return {
        "id": "coryell",
        "name": "Coryell City WSD",
        "subtitle": "Rural water district · Texas, USA",
        "country": "United States",
        "center": [-97.66, 31.50],
        "zoom": 9.4,
        "kind": "vector",
        "labels": int(len(ev)),
        "dates": 0,
        "sensors": ["Repair records", "Pipe network", "Pressure zones"],
        "status": "1,690 usable repairs · 918 pipes",
        "headline": "Seven years of point-level repairs over a rural network: a temporal repair-risk test.",
        "metrics": {
            "risk_auc": valid["test"]["auc"],
            "risk_ap": valid["test"]["ap"],
            "risk_top10": valid["test"]["top10_capture"],
            "base_rate": valid["test"]["base_rate"],
            "vv_r2": None,
            "ndmi_r2": None,
            "label_auc": None,
            "corridor_p": None,
        },
        "caveats": [
            "Coryell is a repair-history test, not a radar detection test.",
            "The source layers have no stated open licence; bundled for this hackathon only.",
            "Repair coordinates are where the crew logged the point, accuracy a few to tens of metres.",
            "NISAR chips are not bundled because they need an Earthdata login.",
        ],
    }


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


def build_coryell_site() -> dict:
    site = coryell_site()
    out = DATA / "coryell"
    stats = read_json(out / "stats.json", {})
    site["metrics"] = {
        "vv_r2": None,
        "ndmi_r2": None,
        "label_auc": None,
        "corridor_p": None,
        **site["metrics"],
    }
    meta = {
        "id": "coryell",
        "name": site["name"],
        "subtitle": site["subtitle"],
        "country": site["country"],
        "center": site["center"],
        "zoom": site["zoom"],
        "kind": "vector",
        "network_file": "network.geojson",
        "events_file": "events.geojson",
        "zones_file": "zones.geojson",
        "stats_file": "stats.json",
        "timeline": {"field": "date", "min": stats["period"][0], "max": stats["period"][1]},
        "sources": [
            "Coryell City WSD leak survey (ArcGIS, no stated licence)",
            "CCWSD waterline network (ArcGIS)",
            "CCWSD pressure planes (ArcGIS)",
        ],
        "caveats": site["caveats"],
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return site


def main() -> None:
    APP.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    sites = []
    for sid, cfg in SITE_DIRS.items():
        print(f"building {sid} ...")
        sites.append(build_raster_site(sid, cfg))
    print("building coryell ...")
    sites.append(build_coryell_site())
    (DATA / "sites.json").write_text(json.dumps(sites, indent=2), encoding="utf-8")
    print(f"wrote {DATA / 'sites.json'} ({len(sites)} sites)")


if __name__ == "__main__":
    main()
