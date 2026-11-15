"""Fetch the public Coryell City WSD vector layers used by the TerraGuard platform.

Only the open ArcGIS query endpoints are used; no Earthdata login is needed.
The source layers have **no stated licence** (see data/coryell/README.md), so
they are bundled for this hackathon demonstration only.

Usage (from chris-results/):
    python scripts/fetch_coryell.py
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "coryell"

AGOL = "https://services9.arcgis.com/AIKMFC1P7gpNycCX/arcgis/rest/services"
LAYERS = {
    "leak_survey": f"{AGOL}/survey123_7d36ae6d371c488ba8699e7c34bb1588/FeatureServer/0",
    "waterlines": f"{AGOL}/CCWSDWaterline2026/FeatureServer/16",
    "pressure_zones": f"{AGOL}/CCWSD_Leak_Density_WFL1/FeatureServer/19",
}
DATE_FIELDS = {"CreationDate", "EditDate", "datetime"}


def query_layer(url: str) -> dict:
    feats: list[dict] = []
    offset = 0
    while True:
        r = requests.get(
            f"{url}/query",
            timeout=120,
            params=dict(where="1=1", outFields="*", outSR=4326, f="geojson",
                        resultOffset=offset, resultRecordCount=1000),
        )
        r.raise_for_status()
        batch = r.json().get("features", [])
        feats.extend(batch)
        offset += len(batch)
        if len(batch) < 1000:
            break
    return {"type": "FeatureCollection", "features": feats}


def write_csv(fc: dict, path: Path) -> None:
    keys = list(fc["features"][0]["properties"])
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(keys + ["longitude", "latitude"])
        for f in fc["features"]:
            p = f["properties"]
            xy = (f.get("geometry") or {}).get("coordinates", [None, None])[:2]
            row = []
            for k in keys:
                v = p.get(k)
                if k in DATE_FIELDS and v:
                    v = datetime.fromtimestamp(v / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                row.append(v)
            w.writerow(row + xy)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, url in LAYERS.items():
        fc = query_layer(url)
        if name == "waterlines":
            for f in fc["features"]:
                f["properties"].pop("Notes", None)
        path = OUT / f"{name}.geojson"
        path.write_text(json.dumps(fc), encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: {len(fc['features'])} features")
        if name == "leak_survey":
            write_csv(fc, OUT / "leak_survey.csv")
            print(f"{(OUT / 'leak_survey.csv').relative_to(ROOT)} written")


if __name__ == "__main__":
    main()
