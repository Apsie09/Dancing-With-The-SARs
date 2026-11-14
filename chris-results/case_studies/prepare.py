"""Prepare the two ground-truth case studies.

Case 1: Aguascalientes, Mexico — utility water network (Tuberias.shp) and
        cleaned leak repairs (2019-2022), EPSG:32613.
Case 2: Calgary, Canada — public water main network (Socrata w6h9-w33i) and
        water main breaks (Socrata dpcu-jr23), EPSG:32611.

The heavy source repositories are expected in /tmp/opencode/cases:
  /tmp/opencode/cases/aguas   (github.com/erickfama/rs_leaks)
  /tmp/opencode/cases/calgary (breaks.csv downloaded)

Run:
  ~/.pixi/bin/pixi run python case_studies/prepare.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "case_studies"
SRC = Path("/tmp/opencode/cases")


def _write_case(name: str, cfg: dict, network: gpd.GeoDataFrame, labels: pd.DataFrame) -> None:
    root = CASES / name
    for sub in ("data/vectors", "data/static", "data/met", "data/raw", "data/interim", "outputs"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    network.to_crs(4326).to_file(root / "data/vectors/water_main.geojson", driver="GeoJSON")
    labels.to_csv(root / "data/vectors/labels.csv", index=False)
    cfg["root"] = f"case_studies/{name}"
    (root / "case.json").write_text(json.dumps(cfg, indent=2))
    print(f"{name}: network {len(network)} features, labels {len(labels)}, AOI {cfg['aoi']}")


def prepare_aguascalientes() -> None:
    src = SRC / "aguas"
    leaks = pd.read_csv(src / "data/clean/leaks_clean_download.csv")
    net = gpd.read_file(src / "data/shp/Tuberias.shp").to_crs(32613)

    x0, y0, x1, y1 = 780000.0, 2420000.0, 785000.0, 2425000.0
    bb = box(x0, y0, x1, y1)
    net = net[net.intersects(bb)].copy()
    water = net[net["WATERTYPE"].fillna("Potable").str.lower().eq("potable")] if "WATERTYPE" in net else net

    leaks["date"] = pd.to_datetime(leaks["fecha_de_i"], errors="coerce")
    sel = leaks[
        leaks["x"].between(x0, x1)
        & leaks["y"].between(y0, y1)
        & leaks["date"].between("2022-01-01", "2022-12-31")
        & leaks["date"].dt.month.isin([1, 2, 3, 4, 5, 11, 12])
    ].copy()
    tr = Transformer.from_crs(32613, 4326, always_xy=True)
    lon, lat = tr.transform(sel["x"].to_numpy(), sel["y"].to_numpy())
    labels = pd.DataFrame(
        {
            "id": sel["id"].astype(int).to_numpy(),
            "lon": lon,
            "lat": lat,
            "date": sel["date"].dt.strftime("%Y-%m-%d").to_numpy(),
            "activity": sel["actividad"].fillna("").to_numpy(),
        }
    )
    aoi_bb = gpd.GeoSeries([bb], crs=32613).to_crs(4326).iloc[0]
    w, s, e, n = aoi_bb.bounds
    cfg = {
        "name": "Aguascalientes water network · Mexico",
        "grid_epsg": 32613,
        "res": 20.0,
        "start": "2022-01-01",
        "end": "2023-01-01",
        "s1_orbit_state": "ascending",
        "s1_relative_orbit": 151,
        "aoi": {
            "west": float(w),
            "south": float(s),
            "east": float(e),
            "north": float(n),
            "center_lon": float((w + e) / 2),
            "center_lat": float((s + n) / 2),
        },
        "pipeline_geojson": "data/vectors/water_main.geojson",
        "gas_geojson": None,
        "labels_csv": "data/vectors/labels.csv",
        "dry_months": [1, 2, 3, 4, 5, 11, 12],
        "dry_years": [2022],
        "train_end": "2022-09-01",
        "val_end": "2022-11-01",
    }
    _write_case("aguascalientes", cfg, water, labels)


def prepare_calgary() -> None:
    dst = CASES / "calgary"
    raw = dst / "data/raw"
    raw.mkdir(parents=True, exist_ok=True)
    src = SRC / "calgary"
    breaks = pd.read_csv(src / "breaks.csv", parse_dates=["break_date"])
    breaks["lon"] = breaks["point"].str.extract(r"POINT \(([-0-9.]+)")[0].astype(float)
    breaks["lat"] = breaks["point"].str.extract(r"POINT \([-0-9.]+ ([-0-9.]+)\)")[0].astype(float)

    # 10 x 10 km AOI over the densest summer-break cell (NW Calgary)
    w, s, e, n = -114.00, 51.00, -113.90, 51.10
    bb = box(w, s, e, n)
    sel = breaks[
        breaks["lon"].between(w, e)
        & breaks["lat"].between(s, n)
        & breaks["break_date"].between("2022-01-01", "2025-12-31")
        & breaks["break_date"].dt.month.isin([6, 7, 8, 9])
    ].copy()
    labels = pd.DataFrame(
        {
            "id": sel.index.astype(int).to_numpy(),
            "lon": sel["lon"].to_numpy(),
            "lat": sel["lat"].to_numpy(),
            "date": sel["break_date"].dt.strftime("%Y-%m-%d").to_numpy(),
            "break_type": sel["break_type"].to_numpy(),
        }
    )

    # public water main network: Socrata GeoJSON pages, cached
    net_cache = raw / "calgary_watermain.geojson"
    if not net_cache.exists():
        feats = []
        for offset in range(0, 61000, 20000):
            url = "https://data.calgary.ca/resource/w6h9-w33i.geojson"
            r = requests.get(url, params={"$limit": 20000, "$offset": offset}, timeout=180)
            r.raise_for_status()
            feats.extend(r.json().get("features", []))
            print("  network page", offset, len(feats))
        net_cache.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    net = gpd.read_file(net_cache)
    net = net[net.intersects(bb)].copy()

    cfg = {
        "name": "Calgary water network · Canada",
        "grid_epsg": 32611,
        "res": 20.0,
        "start": "2022-01-01",
        "end": "2026-01-01",
        "s1_orbit_state": "ascending",
        "s1_relative_orbit": 122,
        "aoi": {
            "west": w,
            "south": s,
            "east": e,
            "north": n,
            "center_lon": (w + e) / 2,
            "center_lat": (s + n) / 2,
        },
        "pipeline_geojson": "data/vectors/water_main.geojson",
        "gas_geojson": None,
        "labels_csv": "data/vectors/labels.csv",
        "dry_months": [6, 7, 8, 9],
        "dry_years": [2022, 2023, 2024, 2025],
        "train_end": "2024-10-01",
        "val_end": "2025-01-01",
    }
    _write_case("calgary", cfg, net, labels)


if __name__ == "__main__":
    prepare_aguascalientes()
    prepare_calgary()
