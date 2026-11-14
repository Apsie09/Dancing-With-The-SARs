"""Build the TerraGuard interactive map and static figures.

The HTML is self-contained: every raster overlay is embedded as a base64 PNG,
so it can be opened offline and submitted as a single file.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import folium
import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.warp import reproject
from matplotlib.colors import LinearSegmentedColormap, Normalize
from PIL import Image
from pyproj import Transformer

from pipeline.config import (
    AOI,
    CASE_NAME,
    ES_STAC,
    GAS_GEOJSON,
    INTERIM,
    LABELS_CSV,
    OUTPUTS,
    PIPELINE_GEOJSON,
    S2_COLLECTION,
    analysis_grid,
    aoi_bbox,
)
from pipeline.acquire import read_to_grid

OUT_HTML = OUTPUTS / "terraguard_map.html"
OUT_PNG = OUTPUTS / "terraguard_map.png"
OUT_PROFILE = OUTPUTS / "corridor_profile.png"

MOIST_CMAP = LinearSegmentedColormap.from_list(
    "soil_moisture", ["#ca0020", "#f4a582", "#f7f7f7", "#92c5de", "#0571b0"]
)
LEAK_CMAP = LinearSegmentedColormap.from_list(
    "leak", ["#fff7ec", "#fee8c8", "#fdbb84", "#e34a33", "#b30000", "#4d0011"]
)
PERSIST_CMAP = LinearSegmentedColormap.from_list("persist", ["#ffffcc", "#a1dab4", "#41b6c4", "#225ea8", "#081d58"])
THERM_CMAP = LinearSegmentedColormap.from_list("thermal", ["#b2182b", "#f4a582", "#f7f7f7", "#92c5de", "#2166ac"])


def build_basemap() -> np.ndarray:
    """Fetch a clear summer Sentinel-2 true-colour composite over the AOI."""
    import numpy as np

    out_tif = OUTPUTS / "basemap_rgb.tif"
    out_png = OUTPUTS / "basemap_rgb.png"
    if out_tif.exists():
        with rasterio.open(out_tif) as ds:
            return np.transpose(ds.read([1, 2, 3]), (1, 2, 0))

    grid = analysis_grid()
    best = None
    for period in ("2026-06-01T00:00:00Z/2026-09-30T00:00:00Z", "2025-06-01T00:00:00Z/2025-09-30T00:00:00Z"):
        body = {
            "collections": [S2_COLLECTION],
            "bbox": aoi_bbox(),
            "datetime": period,
            "limit": 30,
            "query": {"eo:cloud_cover": {"lt": 25}},
        }
        try:
            d = requests.post(f"{ES_STAC}/search", json=body, timeout=90).json()
        except Exception as exc:  # noqa: BLE001
            print("basemap search failed", exc)
            continue
        feats = sorted(d.get("features", []), key=lambda f: f["properties"].get("eo:cloud_cover", 999))
        for f in feats[:10]:
            a = f.get("assets", {})
            if not all(k in a for k in ("red", "green", "blue", "scl")):
                continue
            scl = read_to_grid(a["scl"]["href"], grid, rasterio.enums.Resampling.nearest)
            if scl is None:
                continue
            scl = np.nan_to_num(scl, nan=0).astype("uint8")
            frac = float(np.isin(scl, [3, 8, 9, 10, 11]).mean())
            if frac > 0.15:
                continue
            bands = []
            ok = True
            for k in ("red", "green", "blue"):
                x = read_to_grid(a[k]["href"], grid, rasterio.enums.Resampling.bilinear)
                if x is None:
                    ok = False
                    break
                bands.append(x)
            if not ok:
                continue
            best = (f["properties"]["datetime"][:10], np.stack(bands, axis=-1), scl)
            break
        if best is not None:
            break
    if best is None:
        print("no clean S2 basemap found; using a neutral background")
        rgb = np.full((grid["height"], grid["width"], 3), 235, dtype="uint8")
    else:
        date, arr, scl = best
        print("basemap date", date)
        rgb = (arr - 1000.0) / 10000.0
        rgb[np.isin(scl, [3, 8, 9, 10, 11])] = np.nan
        for i in range(3):
            band = rgb[..., i]
            lo, hi = np.nanpercentile(band, [1, 99])
            band = np.clip((band - lo) / max(hi - lo, 1e-6), 0, 1) ** 0.72
            rgb[..., i] = np.nan_to_num(band, nan=0.80)
        gray = np.nanmean(rgb, axis=2, keepdims=True)
        rgb = np.clip(gray + 1.45 * (rgb - gray), 0, 1)
        rgb = (rgb * 255).astype("uint8")

    with rasterio.open(
        out_tif,
        "w",
        driver="GTiff",
        height=grid["height"],
        width=grid["width"],
        count=3,
        dtype="uint8",
        crs=grid["crs"],
        transform=grid["transform"],
        compress="deflate",
    ) as ds:
        ds.write(np.transpose(rgb, (2, 0, 1)))
    Image.fromarray(rgb).save(out_png)
    return rgb


def _rgb_uri(rgb: np.ndarray) -> str:
    img = Image.fromarray(rgb)
    if max(img.size) > 1400:
        img.thumbnail((1400, 1400), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()




def _display_network(gdf: gpd.GeoDataFrame):
    """Show trunk mains when the utility network is dense."""
    if "diam" in gdf.columns:
        diam = pd.to_numeric(gdf["diam"], errors="coerce")
        for threshold in (600, 400, 300):
            prim = gdf[diam >= threshold]
            if len(prim) >= 25:
                return prim, f"mains ≥{threshold} mm"
    if "DIAMETER" in gdf.columns:
        diam = pd.to_numeric(gdf["DIAMETER"], errors="coerce")
        for threshold in (16, 12, 8):
            prim = gdf[diam >= threshold]
            if len(prim) >= 25:
                return prim, f"mains ≥{threshold} in"
    if "TipoRed" in gdf.columns:
        prim = gdf[gdf["TipoRed"].isin(["Primaria", "Conduccion"])]
        if len(prim) > 10:
            return prim, "primary + transmission mains"
    return gdf, "all mapped mains"


def _json_ready(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Make arbitrary utility attributes safe for Folium's JSON encoder."""
    gdf = gdf.copy()
    for c in gdf.columns:
        if c == "geometry":
            continue
        if pd.api.types.is_datetime64_any_dtype(gdf[c]):
            gdf[c] = gdf[c].astype(str)
        elif gdf[c].dtype == object:
            gdf[c] = gdf[c].fillna("").astype(str)
    return gdf


def _png_uri(arr: np.ndarray, cmap, vmin: float, vmax: float, alpha: float = 0.8, alpha_ramp: bool = False, center: float | None = None) -> str:
    if isinstance(cmap, str):
        cmap = matplotlib.colormaps.get_cmap(cmap)
    a = arr.astype("float32")
    norm = Normalize(vmin=vmin, vmax=vmax, clip=True)
    rgba = cmap(norm(np.nan_to_num(a, nan=vmin)))
    finite = np.isfinite(a)
    if alpha_ramp:
        if center is not None:
            strength = np.clip(np.abs(a - center) / max(vmax - center, 1e-6), 0, 1) ** 0.8
        else:
            strength = np.clip((a - vmin) / max(vmax - vmin, 1e-6), 0, 1) ** 0.9
        rgba[..., 3] = np.where(finite, alpha * strength, 0)
    else:
        rgba[..., 3] = np.where(finite, alpha, 0)
    img = Image.fromarray((rgba * 255).astype("uint8"), mode="RGBA")
    # keep the HTML small but detailed enough for a 5 km AOI
    if max(img.size) > 900:
        img.thumbnail((900, 900), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _chart_uri(dates, series, title: str) -> str:
    fig, ax = plt.subplots(figsize=(4.0, 1.9), dpi=130)
    d = pd.to_datetime(dates)
    ax.plot(d, series, color="#0b6623", lw=1.2)
    ax.axhline(0, color="0.5", lw=0.6)
    ax.axhline(0.5, color="#d95f0e", lw=0.6, ls="--")
    # shade dry seasons
    for y in sorted(set(d.year)):
        ax.axvspan(pd.Timestamp(f"{y}-06-01"), pd.Timestamp(f"{y}-10-01"), color="#f0e6c8", alpha=0.5, lw=0)
    ax.set_title(title, fontsize=7, loc="left")
    ax.tick_params(labelsize=5)
    ax.set_ylabel("z", fontsize=5)
    for s in ax.spines.values():
        s.set_linewidth(0.4)
    fig.tight_layout(pad=0.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _bounds(grid):
    t = grid["transform"]
    x0, y0 = t.c, t.f - grid["height"] * grid["res"]
    x1, y1 = t.c + grid["width"] * grid["res"], t.f
    tr = Transformer.from_crs(grid["crs"], "EPSG:4326", always_xy=True)
    lon0, lat0 = tr.transform(x0, y0)
    lon1, lat1 = tr.transform(x1, y1)
    return [[lat0, lon0], [lat1, lon1]]


def _panel(validation, hotspots) -> str:
    p = validation.get("pipeline_enrichment", {})
    hs = hotspots[0] if hotspots else {}
    p95 = p.get("p_value_p95")
    pval = f"{p95:.3f}" if isinstance(p95, (int, float)) else "n/a"
    return f"""
    <div style="position:fixed;top:14px;left:14px;z-index:9999;width:370px;
      background:rgba(255,255,255,0.95);border:1px solid #b8b8b8;border-radius:10px;
      padding:14px 16px;font-family:Inter,Arial,sans-serif;color:#1b1b1b;
      box-shadow:0 4px 18px rgba(0,0,0,0.18);font-size:12px;line-height:1.45;">
      <div style="font-size:18px;font-weight:700;letter-spacing:0.2px;">TerraGuard</div>
      <div style="font-size:11px;color:#555;margin-bottom:8px;">{CASE_NAME}</div>
      <div style="background:#f4f7f4;border-radius:7px;padding:8px 10px;margin-bottom:8px;">
        <b>Satellite leak screening.</b> A weather-normalised model asks: where is the ground
        wetter (and cooler) than rainfall, soil and vegetation can explain during the dry season?
        Anomalies near the mapped water network are ranked for field inspection.
      </div>
      <div style="display:flex;gap:10px;margin-bottom:8px;">
        <div><div style="font-size:19px;font-weight:700;">{validation.get('s1_dates','–')}</div>
          <div style="font-size:10px;color:#666;">Sentinel-1 dates</div></div>
        <div><div style="font-size:19px;font-weight:700;">{validation.get('dry_season_dates','–')}</div>
          <div style="font-size:10px;color:#666;">dry-season scenes</div></div>
        <div><div style="font-size:19px;font-weight:700;">{hs.get('leak_score','–')}</div>
          <div style="font-size:10px;color:#666;">top score / 100</div></div>
        <div><div style="font-size:19px;font-weight:700;">{pval}</div>
          <div style="font-size:10px;color:#666;">corridor p (n.s. &gt; 0.05)</div></div>
      </div>
      <div style="font-size:11px;color:#444;margin-bottom:6px;"><b>Layers</b> (top-right control)</div>
      <div style="font-size:11px;">
        <span style="display:inline-block;width:10px;height:10px;background:#b30000;border-radius:2px;"></span>
        Leak likelihood (relative, corridor-weighted)<br>
        <span style="display:inline-block;width:10px;height:10px;background:#01665e;border-radius:2px;"></span>
        Soil-moisture anomaly (dry-season, 0–100)<br>
        <span style="display:inline-block;width:10px;height:10px;background:#2166ac;border-radius:2px;"></span>
        Thermal cooling anomaly (positive = cooler)<br>
        <span style="display:inline-block;width:10px;height:10px;background:#225ea8;border-radius:2px;"></span>
        Persistence (fraction of dry dates wet)<br>
        <span style="display:inline-block;width:10px;height:10px;background:#000;border-radius:2px;"></span>
        Hotspots &middot; water network &middot; labels
      </div>
      <div style="margin-top:8px;font-size:10px;color:#666;">
        Score is a <i>screening priority</i>, not a confirmed leak. No metre-level localisation:
        the analysis grid is 20 m and the evidence is multi-date, not a single image. The pipeline
        enrichment test is not significant in this AOI (p&nbsp;&gt;&nbsp;0.05); the hotspots are candidates
        for field checking, not detections.
      </div>
    </div>
    """


def _legend() -> str:
    return """
    <div style="position:fixed;bottom:26px;left:14px;z-index:9999;width:250px;
      background:rgba(255,255,255,0.94);border:1px solid #b8b8b8;border-radius:9px;
      padding:10px 12px;font-family:Inter,Arial,sans-serif;font-size:10px;color:#222;">
      <div style="font-weight:700;margin-bottom:4px;">Leak likelihood</div>
      <div style="height:10px;border-radius:2px;background:linear-gradient(90deg,#fff7ec,#fdbb84,#e34a33,#b30000,#4d0011);"></div>
      <div style="display:flex;justify-content:space-between;color:#555;"><span>low</span><span>high</span></div>
      <div style="font-weight:700;margin-top:7px;margin-bottom:4px;">Soil-moisture anomaly (z)</div>
      <div style="height:10px;border-radius:2px;background:linear-gradient(90deg,#8c510a,#f6e8c3,#5ab4ac,#01665e);"></div>
      <div style="display:flex;justify-content:space-between;color:#555;"><span>dry (−1.5σ)</span><span>wet (+1.5σ)</span></div>
      <div style="margin-top:6px;color:#666;">Weather-normalised residual, June–September 2022–2026. Base: Esri World Imagery.</div>
    </div>
    """


def build_html() -> None:
    grid = analysis_grid()
    scores = np.load(OUTPUTS / "scores.npz", allow_pickle=True)
    validation = json.loads((OUTPUTS / "validation.json").read_text())
    hotspots = json.loads((OUTPUTS / "hotspots.json").read_text())
    bounds = _bounds(grid)
    leak_vmax = 20.0
    if LABELS_CSV:
        leak_vmax = max(10.0, min(60.0, float(np.nanpercentile(scores["leak_score"], 99))))
        leak_vmax = round(leak_vmax / 5) * 5

    m = folium.Map(location=[AOI["center_lat"], AOI["center_lon"]], zoom_start=14, tiles=None, control_scale=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics",
        name="Esri World Imagery (reference)",
        max_zoom=19,
        show=True,
        zindex=0,
    ).add_to(m)

    rgb = build_basemap()
    folium.raster_layers.ImageOverlay(
        image=_rgb_uri(rgb),
        bounds=bounds,
        name="Sentinel-2 true colour (summer)",
        opacity=1.0,
        interactive=False,
        show=False,
        zindex=1,
    ).add_to(m)

    layers = [
        ("Leak likelihood (study period)", scores["leak_score"], LEAK_CMAP, 0, leak_vmax, 0.95, True, True, None),
        ("Soil-moisture anomaly (z)", scores["moist_smooth"], MOIST_CMAP, -1.5, 1.5, 0.88, True, False, 0.0),
        ("Thermal cooling anomaly", scores["thermal"], THERM_CMAP, -2, 3, 0.62, False, False, None),
        ("Persistence", scores["persist"] * 100, PERSIST_CMAP, 0, 100, 0.62, False, False, None),
        ("Confidence", scores["confidence"], "Greys", 0, 100, 0.45, False, False, None),
    ]
    for name, arr, cmap, vmin, vmax, alpha, ramp, show, center in layers:
        folium.raster_layers.ImageOverlay(
            image=_png_uri(arr, cmap, vmin, vmax, alpha=alpha, alpha_ramp=ramp, center=center),
            bounds=bounds,
            name=name,
            opacity=1.0,
            interactive=False,
            cross_origin=False,
            zindex=2 if show else 3,
            show=show,
        ).add_to(m)

    # annual moisture layers (optional, good for storytelling)
    years = list(scores["years"])
    for i, y in enumerate(years):
        arr = scores["year_moist"][i]
        folium.raster_layers.ImageOverlay(
            image=_png_uri(arr, MOIST_CMAP, -1.5, 1.5, alpha=0.65),
            bounds=bounds,
            name=f"Moisture anomaly {int(y)}",
            opacity=1.0,
            interactive=False,
            show=False,
        ).add_to(m)

    # pipelines
    water_path = PIPELINE_GEOJSON
    if water_path and Path(water_path).exists():
        water_full = gpd.read_file(water_path).to_crs("EPSG:4326")
        water_full, net_label = _display_network(water_full)
        keep = [c for c in ["substance", "location", "osm_id", "TipoRed", "MATERIAL", "DIAMETER", "FACILITYID", "p_zone", "material", "diam", "year"] if c in water_full.columns]
        water = _json_ready(water_full[keep + ["geometry"]].copy())
        water["geometry"] = water.geometry.simplify(0.00001, preserve_topology=True)
        tip = None
        if all(c in water.columns for c in ["substance", "location", "osm_id"]):
            tip = folium.GeoJsonTooltip(fields=["substance", "location", "osm_id"], aliases=["Substance", "Placement", "OSM ID"])
        elif "TipoRed" in water.columns:
            tip = folium.GeoJsonTooltip(fields=["TipoRed", "MATERIAL", "DIAMETER"], aliases=["Type", "Material", "Diameter"])
        folium.GeoJson(
            water.__geo_interface__,
            name=f"Water network — {net_label} ({len(water)} segments)",
            style_function=lambda _: {"color": "#00e5ff", "weight": 0.7, "opacity": 0.65},
            tooltip=tip,
        ).add_to(m)
        water_utm = water_full.to_crs(grid["crs"])
        buf = gpd.GeoDataFrame(
            geometry=water_utm.geometry.buffer(60).simplify(3.0),
            crs=grid["crs"],
        ).to_crs(4326)
        folium.GeoJson(
            buf.__geo_interface__,
            name="60 m inspection corridor",
            style_function=lambda _: {"color": "#00e5ff", "weight": 1, "dashArray": "3,5", "fillColor": "#00e5ff", "fillOpacity": 0.05},
        ).add_to(m)
    allp = GAS_GEOJSON
    if allp and Path(allp).exists():
        pipes = _json_ready(gpd.read_file(allp).to_crs("EPSG:4326"))
        gas = pipes[pipes["substance"] == "gas"] if "substance" in pipes.columns else pipes.iloc[0:0]
        if len(gas):
            folium.GeoJson(
                gas.__geo_interface__,
                name="Gas transmission line",
                style_function=lambda _: {"color": "#ffb000", "weight": 2.5, "dashArray": "5,5", "opacity": 0.9},
                tooltip=folium.GeoJsonTooltip(fields=["substance", "operator"], aliases=["Substance", "Operator"]),
            ).add_to(m)


    # ground-truth labels (case studies)
    if LABELS_CSV and Path(LABELS_CSV).exists():
        labels = pd.read_csv(LABELS_CSV)
        lon_col = next((c for c in labels.columns if c.lower() in ("lon", "longitude")), None)
        lat_col = next((c for c in labels.columns if c.lower() in ("lat", "latitude")), None)
        if lon_col and lat_col:
            fg = folium.FeatureGroup(name=f"Ground-truth labels ({len(labels)})", show=True)
            for _, row in labels.iterrows():
                dtxt = f"<br>{row.get('date', '')}" if "date" in labels.columns else ""
                folium.CircleMarker(
                    location=[float(row[lat_col]), float(row[lon_col])],
                    radius=3,
                    color="#ffd400",
                    weight=1,
                    fill=True,
                    fill_color="#ffd400",
                    fill_opacity=0.9,
                    tooltip=f"Ground truth{dtxt}",
                ).add_to(fg)
            fg.add_to(m)

    # NISAR overlays if the extraction has produced rasters
    nisar_dir = OUTPUTS.parent / "data" / "raw" / "nisar"
    used_nisar = False
    if nisar_dir.exists():
        for p in sorted(nisar_dir.glob("*.tif")):
            name = p.name.lower()
            if "change" not in name and "latest" not in name:
                continue
            try:
                with rasterio.open(p) as ds:
                    a = ds.read(1).astype("float32")
                    nd = ds.nodata
                    if nd is not None:
                        a[a == nd] = np.nan
                    # resample to the analysis grid
                    from rasterio.warp import reproject

                    dest = np.full((grid["height"], grid["width"]), np.nan, "float32")
                    reproject(
                        source=a,
                        destination=dest,
                        src_transform=ds.transform,
                        src_crs=ds.crs,
                        dst_transform=grid["transform"],
                        dst_crs=grid["crs"],
                        src_nodata=np.nan,
                        dst_nodata=np.nan,
                        resampling=rasterio.enums.Resampling.bilinear,
                    )
            except Exception:
                continue
            if np.isfinite(dest).mean() < 0.05:
                continue
            if "change" in name and "hh" in name:
                label = "HH change (Jun→Oct 2026)"
            elif "change" in name and "hv" in name:
                label = "HV change (Jun→Oct 2026)"
            elif "latest" in name:
                label = "HH latest browse (Oct 2026)"
            else:
                label = p.stem.replace("_", " ")
            if "change" in name:
                vmin, vmax = np.nanpercentile(dest, [5, 95])
                cmap = LinearSegmentedColormap.from_list("nisar_change", ["#2166ac", "#f7f7f7", "#b2182b"])
            else:
                vmin, vmax = np.nanpercentile(dest, [2, 98])
                cmap = "gray"
            folium.raster_layers.ImageOverlay(
                image=_png_uri(dest, cmap, vmin, vmax, alpha=0.62 if "change" in name else 0.42),
                bounds=bounds,
                name=f"NISAR L-band: {label}",
                opacity=1.0,
                interactive=False,
                show=False,
            ).add_to(m)
            used_nisar = True

    # hotspots
    residual_path = INTERIM / "residual_cubes.npz"
    cubes = np.load(residual_path, allow_pickle=True) if residual_path.exists() else None
    for h in hotspots:
        chart = ""
        if cubes is not None:
            r, c = h["row"], h["col"]
            nb = cubes["z_moist"][:, max(0, r - 1) : r + 2, max(0, c - 1) : c + 2].astype("float32")
            series = np.nanmean(nb, axis=(1, 2))
            chart = f'<img src="{_chart_uri(cubes["dates"], series, "moisture residual at hotspot")}" style="width:330px;margin-top:6px;">'
        color = "#b30000" if h["leak_score"] >= 90 else "#e34a33" if h["leak_score"] >= 75 else "#fdbb84"
        html = f"""
        <div style="font-family:Inter,Arial,sans-serif;font-size:12px;width:350px;">
          <div style="font-size:15px;font-weight:700;">Hotspot #{h['id']} &middot; score {h['leak_score']}/100</div>
          <div style="color:#555;margin-bottom:4px;">{h['lat']:.5f}, {h['lon']:.5f}</div>
          <table style="font-size:11px;border-collapse:collapse;">
            <tr><td style="padding:2px 8px 2px 0;">Moisture residual</td><td><b>{h['moisture_z']} σ</b></td></tr>
            <tr><td style="padding:2px 8px 2px 0;">Persistence</td><td><b>{h['persistence']:.0%}</b> of dry dates</td></tr>
            <tr><td style="padding:2px 8px 2px 0;">Thermal cooling</td><td><b>{h['thermal_z']} σ</b></td></tr>
            <tr><td style="padding:2px 8px 2px 0;">Distance to water main</td><td><b>{h['dist_water_m']:.0f} m</b></td></tr>
            <tr><td style="padding:2px 8px 2px 0;">Distance to gas line</td><td>{h['dist_gas_m']:.0f} m</td></tr>
            <tr><td style="padding:2px 8px 2px 0;">Confidence</td><td>{h['confidence']:.0f}/100</td></tr>
            <tr><td style="padding:2px 8px 2px 0;">Land cover</td><td>{h.get('landcover')}</td></tr>
          </table>
          <div style="font-size:10px;color:#666;margin-top:4px;">Strongest dry-season dates: {', '.join(h.get('top_dates', [])[:3])}</div>
          {chart}
          <div style="font-size:9px;color:#888;margin-top:4px;">Screening priority; field verification required.</div>
        </div>
        """
        folium.CircleMarker(
            location=[h["lat"], h["lon"]],
            radius=9 if h["leak_score"] >= 90 else 7,
            color="#ffffff",
            weight=1.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.95,
            popup=folium.Popup(html, max_width=380),
            tooltip=f"Hotspot #{h['id']} · score {h['leak_score']}/100 · {h['dist_water_m']:.0f} m from main",
            name=f"Hotspot #{h['id']}",
        ).add_to(m)

    # panels
    m.get_root().html.add_child(folium.Element(_panel(validation, hotspots)))
    m.get_root().html.add_child(folium.Element(_legend()))
    folium.LayerControl(collapsed=False, position="topright").add_to(m)
    folium.LatLngPopup().add_to(m)

    if not used_nisar:
        m.get_root().html.add_child(
            folium.Element(
                '<div style="position:fixed;bottom:26px;right:14px;z-index:9999;background:#fff3cd;'
                'border:1px solid #ffc107;border-radius:8px;padding:8px 10px;font:11px Arial;'
                'max-width:260px;">NISAR layer not found in this run. The map remains fully functional; '
                'run <code>scripts/nisar_extract.py</code> to add the L-band layer.</div>'
            )
        )
    else:
        m.get_root().html.add_child(
            folium.Element(
                '<div style="position:fixed;bottom:26px;right:14px;z-index:9999;background:#e8f4ff;'
                'border:1px solid #7fb3d5;border-radius:8px;padding:8px 10px;font:11px Arial;'
                'max-width:290px;">NISAR L-band layers are public ASF GCOV browse imagery '
                '(8-bit, relative), shown for L-band context and change. The quantitative score uses '
                'Sentinel-1 C-band, Sentinel-2 and Landsat.</div>'
            )
        )

    m.save(OUT_HTML)
    print("saved", OUT_HTML, OUT_HTML.stat().st_size / 1e6, "MB")


def build_static() -> None:
    grid = analysis_grid()
    scores = np.load(OUTPUTS / "scores.npz", allow_pickle=True)
    hotspots = json.loads((OUTPUTS / "hotspots.json").read_text())
    water = gpd.read_file(PIPELINE_GEOJSON).to_crs(grid["crs"])
    water, net_label = _display_network(water)
    leak_vmax = 20.0
    if LABELS_CSV:
        leak_vmax = round(max(10.0, min(60.0, float(np.nanpercentile(scores["leak_score"], 99)))) / 5) * 5
    if GAS_GEOJSON and Path(GAS_GEOJSON).exists():
        allp = gpd.read_file(GAS_GEOJSON).to_crs(grid["crs"])
        gas = allp[allp["substance"] == "gas"] if "substance" in allp.columns else allp.iloc[0:0]
    else:
        gas = gpd.GeoDataFrame(geometry=[], crs=grid["crs"])

    ext = [
        grid["west"],
        grid["east"],
        grid["south"],
        grid["north"],
    ]
    rgb = build_basemap()
    tr = Transformer.from_crs("EPSG:4326", grid["crs"], always_xy=True)
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.2), dpi=180)
    for ax, arr, cmap, vmin, vmax, title, alpha in [
        (axes[0], scores["moist_smooth"], MOIST_CMAP, -1.5, 1.5, "Soil-moisture anomaly (dry-season z)", 0.72),
        (axes[1], scores["leak_score"], LEAK_CMAP, 0, leak_vmax, f"Leak likelihood (corridor-weighted, 0–{leak_vmax:g}+)", 0.9),
    ]:
        ax.set_xlim(ext[0], ext[1])
        ax.set_ylim(ext[2], ext[3])
        ax.imshow(rgb, extent=ext, origin="upper", zorder=1)
        base = np.abs(arr) if title.startswith("Soil") else arr
        strength = np.nan_to_num(np.clip(base / (vmax * 0.8), 0, 1) ** 0.7, nan=0.0)
        im = ax.imshow(
            np.ma.masked_invalid(arr),
            extent=ext,
            origin="upper",
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            alpha=0.12 + 0.82 * strength,
            interpolation="bilinear",
            zorder=3,
        )
        water.buffer(60).plot(ax=ax, facecolor="none", edgecolor="#00e5ff", linewidth=0.8, linestyle=":", zorder=4)
        water.plot(ax=ax, color="#00e5ff", linewidth=0.7, alpha=0.7, zorder=5)
        if len(gas):
            gas.plot(ax=ax, color="#ffb000", linewidth=1.2, linestyle="--", zorder=4)
        for h in hotspots[:8]:
            hx, hy = tr.transform(h["lon"], h["lat"])
            ax.scatter(hx, hy, s=55, c="#ffffff", edgecolors="#4d0011", linewidths=1.2, zorder=7)
            ax.annotate(str(h["id"]), (hx, hy), xytext=(4, 4), textcoords="offset points", fontsize=6, color="white", zorder=8)
        ax.set_title(title, fontsize=12, loc="left")
        ax.set_xticks([])
        ax.set_yticks([])
        cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
        cb.ax.tick_params(labelsize=7)
    fig.suptitle(
        f"TerraGuard — {CASE_NAME} · weather-normalised multi-sensor screening",
        fontsize=12,
        x=0.01,
        ha="left",
    )
    fig.text(
        0.01,
        0.01,
        "Cyan: mapped water network. Orange dashed: gas transmission line (if present). "
        "Scores are screening priorities, not confirmed leaks.",
        fontsize=6.5,
        color="#333",
    )
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    fig.savefig(OUT_PNG, bbox_inches="tight")
    plt.close(fig)
    print("saved", OUT_PNG)


def build_profile() -> None:
    grid = analysis_grid()
    scores = np.load(OUTPUTS / "scores.npz", allow_pickle=True)
    water = gpd.read_file(PIPELINE_GEOJSON).to_crs(grid["crs"])
    water, _ = _display_network(water)
    line = max(water.geometry, key=lambda g: g.length)
    if line.geom_type.startswith("Multi"):
        line = max(line.geoms, key=lambda g: g.length)
    length = line.length
    dists = np.arange(0, length, 25.0)
    pts = [line.interpolate(d) for d in dists]
    arr_map = {
        "Leak score": scores["leak_score"],
        "Moisture z": scores["moist_dry"],
        "Persistence": scores["persist"],
    }
    vals = {k: [] for k in arr_map}
    for p in pts:
        c = int((p.x - grid["west"]) / grid["res"])
        r = int((grid["north"] - p.y) / grid["res"])
        if 0 <= r < grid["height"] and 0 <= c < grid["width"]:
            for k, a in arr_map.items():
                vals[k].append(float(a[r, c]))
        else:
            for k in arr_map:
                vals[k].append(np.nan)
    fig, ax = plt.subplots(figsize=(11, 3.6), dpi=160)
    ax.plot(dists / 1000, vals["Moisture z"], color="#01665e", lw=1.6, label="Moisture residual z")
    ax.axhline(0, color="0.5", lw=0.6)
    ax.set_xlabel("distance along water main (km)")
    ax.set_ylabel("moisture residual z", color="#01665e")
    ax.tick_params(axis="y", labelcolor="#01665e")
    ax.grid(alpha=0.25)
    ax2 = ax.twinx()
    ax2.plot(dists / 1000, vals["Leak score"], color="#b30000", lw=1.4, label="Leak score")
    ax2.set_ylabel("leak score (0–60)", color="#b30000")
    ax2.tick_params(axis="y", labelcolor="#b30000")
    ax2.set_ylim(0, 60)
    ax.set_title("Corridor profile — where the dry-season anomaly persists")
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT_PROFILE, bbox_inches="tight")
    plt.close(fig)
    print("saved", OUT_PROFILE)


if __name__ == "__main__":
    build_html()
    build_static()
    build_profile()
