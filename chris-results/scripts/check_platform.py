"""Validate the TerraGuard platform data contract before serving or publishing.

Checks:
  * the site registry and every referenced file exist;
  * each GeoJSON is a valid FeatureCollection with features;
  * overlay PNGs are readable and their bounds are present;
  * metrics are finite and in [0, 1] where they should be;
  * personal fields are absent from the Coryell event layer;
  * the app shell files exist.

Usage (from chris-results/):
    python scripts/check_platform.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
DATA = APP / "data"
REQUIRED_FILES = ["meta.json", "stats.json"]
PERSONAL = {"Creator", "Editor", "notes", "globalid", "length_of_time_it_took_to_compl"}


def fail(msg: str) -> None:
    print(f"FAIL  {msg}")


def ok(msg: str) -> None:
    print(f"ok    {msg}")


def check_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        fail(f"{path.relative_to(ROOT)}: {exc}")
        return None


def check_geojson(path: Path) -> int:
    fc = check_json(path)
    if not isinstance(fc, dict) or fc.get("type") != "FeatureCollection":
        fail(f"{path.relative_to(ROOT)}: not a FeatureCollection")
        return 0
    feats = fc.get("features", [])
    if not feats:
        fail(f"{path.relative_to(ROOT)}: no features")
    for f in feats[:50]:
        if "geometry" not in f or "properties" not in f:
            fail(f"{path.relative_to(ROOT)}: malformed feature")
            break
    return len(feats)


def main() -> int:
    errors_before = 0

    def err(msg: str) -> None:
        nonlocal errors_before
        errors_before += 1
        fail(msg)

    for name in ("index.html", "app.js", "style.css"):
        p = APP / name
        if p.exists():
            ok(f"app/{name}")
        else:
            err(f"missing app/{name}")

    reg = DATA / "sites.json"
    if not reg.exists():
        err("missing app/data/sites.json")
        return 1
    sites = check_json(reg)
    if not isinstance(sites, list) or not sites:
        err("sites.json is not a non-empty list")
        return 1
    ok(f"sites.json: {len(sites)} sites")

    ids = set()
    for site in sites:
        sid = site.get("id")
        if not sid:
            err("site without id")
            continue
        if sid in ids:
            err(f"duplicate site id {sid}")
        ids.add(sid)
        base = DATA / sid
        for req in REQUIRED_FILES:
            if not (base / req).exists():
                err(f"{sid}: missing {req}")

        meta = check_json(base / "meta.json") or {}
        stats = check_json(base / "stats.json") or {}
        for key in ("name", "center", "zoom", "kind"):
            if key not in meta:
                err(f"{sid}/meta.json: missing {key}")

        for key in ("network_file", "events_file", "hotspots_file", "zones_file"):
            fname = meta.get(key)
            if fname:
                path = base / fname
                if not path.exists():
                    err(f"{sid}: missing {fname}")
                else:
                    n = check_geojson(path)
                    if n:
                        ok(f"{sid}/{fname}: {n} features")

        for layer in meta.get("layers", []):
            fname = layer.get("file")
            bounds = layer.get("bounds")
            if not fname or not bounds:
                err(f"{sid}: raster layer without file/bounds")
                continue
            p = base / fname
            if not p.exists():
                err(f"{sid}: missing {fname}")
                continue
            try:
                with Image.open(p) as im:
                    im.verify()
                ok(f"{sid}/{fname}: {p.stat().st_size // 1024} KB")
            except Exception as exc:  # noqa: BLE001
                err(f"{sid}/{fname}: unreadable PNG ({exc})")
            if len(bounds) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in bounds):
                err(f"{sid}/{fname}: invalid bounds")

        m = stats.get("metrics", {})
        for key, val in m.items():
            if isinstance(val, float):
                if not math.isfinite(val):
                    err(f"{sid}: metric {key} is not finite")
                if key.endswith(("_auc", "_r2")) and not (0 <= val <= 1):
                    err(f"{sid}: metric {key}={val} outside [0,1]")

        if sid == "coryell":
            ev = check_json(base / "events.geojson") or {}
            keys = set()
            for f in ev.get("features", [])[:200]:
                keys.update(f.get("properties", {}).keys())
            bad = keys & PERSONAL
            if bad:
                err(f"coryell events expose personal fields: {sorted(bad)}")
            else:
                ok("coryell events: no personal fields")


    print()
    if errors_before:
        print(f"{errors_before} problem(s) found")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
