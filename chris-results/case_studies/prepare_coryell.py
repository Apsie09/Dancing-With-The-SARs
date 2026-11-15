"""Prepare the Coryell case for the shared TerraGuard pipeline.

The case is a 10 x 10 km rural AOI in UTM 14N chosen as the densest 2025-26
summer repair cell in the district. It uses the same `case.json` contract and
the same pipeline modules as Aguascalientes and Calgary.

Source vectors are fetched first with `scripts/fetch_coryell.py` (public
ArcGIS, no login; no stated licence). This script only subsets them.

Usage (from chris-results/):
    python scripts/fetch_coryell.py
    python case_studies/prepare_coryell.py
    CASE=case_studies/coryell/case.json
    TERRAGUARD_CASE=$CASE python -m pipeline.acquire --workers 16
    TERRAGUARD_CASE=$CASE python -m pipeline.model
    TERRAGUARD_CASE=$CASE python -m pipeline.make_map
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "case_studies" / "coryell"
SRC = ROOT / "data" / "coryell"

# Fixed 10 x 10 km AOI in EPSG:32614 (UTM 14N), selected from the 2025-26
# summer repairs. Keeping it fixed makes the case reproducible.
X0, Y0 = 634555.445234684, 3479328.0408293614
X1, Y1 = X0 + 10000, Y0 + 10000
UTM = 32614


def main() -> None:
    leaks_path = SRC / "leak_survey.geojson"
    net_path = SRC / "waterlines.geojson"
    if not leaks_path.exists() or not net_path.exists():
        raise SystemExit("Run scripts/fetch_coryell.py first (Coryell source vectors are git-ignored).")

    for sub in ("data/vectors", "data/static", "data/met", "data/raw", "data/interim", "outputs"):
        (CASE / sub).mkdir(parents=True, exist_ok=True)

    bb = box(X0, Y0, X1, Y1)
    tr = Transformer.from_crs(UTM, 4326, always_xy=True)
    w, s = tr.transform(X0, Y0)
    e, n = tr.transform(X1, Y1)

    net = gpd.read_file(net_path).to_crs(UTM)
    net = net[net.intersects(bb)].copy()
    net.to_crs(4326).to_file(CASE / "data/vectors/water_main.geojson", driver="GeoJSON")

    leaks = gpd.read_file(leaks_path).to_crs(UTM)
    leaks = leaks[leaks["ObjectId"] != 1611].copy()  # test entry near Galveston
    leaks["dt"] = pd.to_datetime(leaks["datetime"], unit="ms", utc=True, errors="coerce")
    leaks = leaks[leaks["dt"].notna()]
    leaks = leaks[(leaks["dt"] >= "2025-06-01") & (leaks["dt"] < "2026-10-01")]
    leaks = leaks[leaks["dt"].dt.month.isin([6, 7, 8, 9]) & leaks.geometry.within(bb)].copy()

    lon, lat = tr.transform(leaks.geometry.x.to_numpy(), leaks.geometry.y.to_numpy())
    labels = pd.DataFrame({
        "id": leaks["ObjectId"].astype(int).to_numpy(),
        "lon": lon,
        "lat": lat,
        "date": leaks["dt"].dt.strftime("%Y-%m-%d").to_numpy(),
        "activity": leaks["cause_of_leak"].fillna("").to_numpy(),
        "size": leaks["line_size"].fillna("").to_numpy(),
    })
    labels.to_csv(CASE / "data/vectors/labels.csv", index=False)

    cfg = {
        "name": "Coryell City water network · Texas, USA",
        "grid_epsg": UTM,
        "res": 20.0,
        "start": "2025-01-01",
        "end": "2026-11-15",
        "s1_orbit_state": "ascending",
        "s1_relative_orbit": 34,
        "aoi": {
            "west": w, "south": s, "east": e, "north": n,
            "center_lon": (w + e) / 2, "center_lat": (s + n) / 2,
        },
        "pipeline_geojson": "data/vectors/water_main.geojson",
        "gas_geojson": None,
        "labels_csv": "data/vectors/labels.csv",
        "dry_months": [6, 7, 8, 9],
        "dry_years": [2025, 2026],
        "train_end": "2026-01-01",
        "val_end": "2026-06-01",
        "root": "case_studies/coryell",
    }
    (CASE / "case.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"coryell: {len(net)} network features, {len(labels)} summer labels, AOI {w:.5f},{s:.5f},{e:.5f},{n:.5f}")


if __name__ == "__main__":
    main()
