"""Stage 7a: stream city crops of NISAR L2 GUNW (ground movement) and L3 SME2 (soil moisture).

Like Stage 4, only the city window is read over HTTPS (no full downloads). Outputs:
  data/sar/gunw/<granule>.npz   unwrappedPhase, ionospherePhaseScreen, coherence, connectedComponents, mask (80 m, EPSG:32617)
  data/sar/sme2/<granule>.npz   soilMoisture, uncertainty, retrievalQualityFlag, landCover (200 m, EPSG:6933 + lat/lon)
  data/processed/nisar_aux_catalog.parquet   one row per granule with dates, track, sizes, status
"""
from __future__ import annotations

import json
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager, get_context
from pathlib import Path

import earthaccess
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from .config import ROOT, WGS84, Config, human_size, report_file

PRODUCTS = {
    "gunw": {
        "collections": ["NISAR_L2_GUNW_BETA_V1", "NISAR_L2_GUNW_PROVISIONAL_V1", "NISAR_L2_GUNW_V1"],
        "group": "/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram",
        "layers": {"HH/unwrappedPhase": "unwrapped_phase", "HH/ionospherePhaseScreen": "ionosphere_phase",
                   "HH/coherenceMagnitude": "coherence", "HH/connectedComponents": "connected_components",
                   "mask": "mask"},
        "coords": ("xCoordinates", "yCoordinates"),
        "crs": "EPSG:32617",
        "est_bytes": 20 * 2**20,
    },
    "sme2": {
        "collections": ["NISAR_L3_SME2_BETA_V1", "NISAR_L3_SME2_PROVISIONAL_V1", "NISAR_L3_SME2_V1"],
        "group": "/science/LSAR/SME2/grids",
        "layers": {"soilMoisture": "soil_moisture", "soilMoistureUncertainty": "soil_moisture_uncertainty",
                   "retrievalQualityFlag": "retrieval_quality_flag", "surfaceQualityFlag": "surface_quality_flag",
                   "ancillaryData/landCover": "land_cover"},
        "coords": ("xCoordinates", "yCoordinates"),
        "crs": "EPSG:6933",
        "est_bytes": 10 * 2**20,
    },
}
MATURITY = {"BETA": "beta", "PROVISIONAL": "provisional"}


def _parse(product: str, name: str) -> dict:
    t = name.split("_")
    d = {"track": int(t[5]), "direction": t[6], "frame": int(t[7])}
    if product == "gunw":  # ..._<refStart>_<refEnd>_<secStart>_<secEnd>_<CRID>_...
        d["reference_time"] = pd.Timestamp(t[11], tz="UTC")
        d["secondary_time"] = pd.Timestamp(t[13], tz="UTC")
        d["crid"] = t[15]
    else:
        d["acquisition_time"] = pd.Timestamp(t[11], tz="UTC")
        d["crid"] = t[13]
    return d


def catalog(cfg: Config) -> pd.DataFrame:
    aoi = tuple(cfg.section("nisar")["aoi_bbox"])
    rows = []
    for product, spec in PRODUCTS.items():
        for sn in spec["collections"]:
            try:
                res = earthaccess.search_data(short_name=sn, bounding_box=aoi, count=-1)
            except Exception:  # noqa: BLE001 - collection may not exist yet
                res = []
            for g in res:
                u = g["umm"]
                h5 = [x for x in u["DataGranule"]["ArchiveAndDistributionInformation"] if x["Name"].endswith(".h5")]
                pts = u["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]["Boundary"]["Points"]
                rows.append({"product": product, "collection": sn,
                             "maturity": next((v for k, v in MATURITY.items() if k in sn), "validated"),
                             "granule_ur": u["GranuleUR"], "size_bytes": h5[0]["SizeInBytes"] if h5 else 0,
                             "h5_https": next((x for x in g.data_links() if x.endswith(".h5")), None),
                             "geometry": Polygon([(p["Longitude"], p["Latitude"]) for p in pts]),
                             **_parse(product, u["GranuleUR"])})
    df = gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84)
    # keep granules whose footprint covers the incident area; prefer highest maturity per acquisition key
    centre = gpd.GeoSeries.from_xy([-80.48], [43.45], crs=WGS84).iloc[0]
    df = df[df.geometry.contains(centre)].copy()
    rank = df["maturity"].map({"beta": 0, "provisional": 1, "validated": 2})
    df["key"] = df["product"] + "_" + df["granule_ur"].str.split("_").str[4:15].str.join("_")
    df = df.assign(rank=rank).sort_values(["rank", "granule_ur"]).drop_duplicates("key", keep="last")
    return df.drop(columns=["rank"]).reset_index(drop=True)


def _window(x, y, bounds):
    x0, y0, x1, y1 = bounds
    ci = np.where((x >= x0) & (x <= x1))[0]
    ri = np.where((y >= y0) & (y <= y1))[0]
    if not len(ci) or not len(ri):
        return None
    return slice(ri.min(), ri.max() + 1), slice(ci.min(), ci.max() + 1)


def stream_one(row: dict, bounds_by_crs: dict, out_dir: str, queue) -> dict:
    import h5py

    from .sar import https_session

    gid, product = row["granule_ur"], row["product"]
    spec = PRODUCTS[product]
    send = (lambda *a: queue.put((gid, *a))) if queue is not None else (lambda *a: None)
    out = Path(out_dir) / product / f"{gid}.npz"
    if out.exists():
        send("skip", 0)
        return {"granule_ur": gid, "status": "cached", "bytes": 0}
    t0 = time.time()
    for attempt in range(3):
        try:
            fs = https_session(earthaccess.login(strategy="netrc"))
            remote = fs.open(row["h5_https"], "rb", block_size=1 << 20, cache_type="blockcache",
                             cache_options={"maxblocks": 512})
            fetch, total = remote.cache.fetcher, {"n": 0}

            def counting(a, b, _f=fetch):
                total["n"] += b - a
                send("bytes", b - a)
                return _f(a, b)

            remote.cache.fetcher = counting
            send("stage", "open")
            h5 = h5py.File(remote, "r")
            g = h5[spec["group"]]
            x, y = g[spec["coords"][0]][:], g[spec["coords"][1]][:]
            sl = _window(x, y, bounds_by_crs[spec["crs"]])
            if sl is None:
                raise RuntimeError("city window outside granule grid")
            arrays = {"x": x[sl[1]], "y": y[sl[0]]}
            missing = []
            for path, name in spec["layers"].items():
                if path not in g:  # e.g. beta SME2 has no surfaceQualityFlag: record, don't fail
                    missing.append(path)
                    continue
                send("stage", name)
                arrays[name] = g[path][sl]
            for req in ("HH/unwrappedPhase", "soilMoisture"):
                if req in spec["layers"] and req in missing:
                    raise KeyError(f"required layer {req} missing")
            if product == "sme2":
                arrays["latitude"], arrays["longitude"] = g["latitude"][sl[0]], g["longitude"][sl[1]]
            meta = {"granule_ur": gid, "crs": spec["crs"], "window": [int(v) for v in (sl[0].start, sl[0].stop, sl[1].start, sl[1].stop)],
                    "missing_layers": missing}
            h5.close()
            remote.close()
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".part.npz")
            np.savez_compressed(tmp, meta=json.dumps(meta), **arrays)
            tmp.replace(out)
            res = {"granule_ur": gid, "status": "ok", "bytes": total["n"], "seconds": time.time() - t0,
                   "disk_bytes": out.stat().st_size}
            send("done", res)
            return res
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                send("error", f"{type(e).__name__}: {e}")
                return {"granule_ur": gid, "status": "error", "error": f"{type(e).__name__}: {e}",
                        "trace": traceback.format_exc(limit=3), "bytes": 0}
            send("stage", f"retry {attempt + 1}")
            time.sleep(5 * (attempt + 1))


def run(cfg: Config, workers: int = 6, dry_run: bool = False) -> pd.DataFrame:
    from pyproj import Transformer
    from rich.console import Console
    from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
    from rich.table import Table

    con = Console()
    earthaccess.login(strategy="netrc")
    cat = catalog(cfg)
    out_dir = ROOT / cfg.section("sar")["out_dir"]
    cat["cached"] = [(out_dir / p / f"{g}.npz").exists() for p, g in zip(cat["product"], cat["granule_ur"])]
    path = cfg.path("processed_dir") / "nisar_aux_catalog.parquet"
    cat.to_parquet(path)

    x0, y0, x1, y1 = cfg.section("nisar")["aoi_bbox"]
    bounds = {}
    for crs in {s["crs"] for s in PRODUCTS.values()}:
        tr = Transformer.from_crs(4326, crs, always_xy=True)
        xs, ys = tr.transform([x0, x1, x0, x1], [y0, y0, y1, y1])
        bounds[crs] = (min(xs) - 500, min(ys) - 500, max(xs) + 500, max(ys) + 500)

    t = Table(title="Stage 7a plan (GUNW + SME2 city crops)")
    for c in ("product", "granules", "cached", "to stream", "remote size", "est. transfer", "dates"):
        t.add_column(c)
    for p, g in cat.groupby("product"):
        todo = g[~g["cached"]]
        tcol = "secondary_time" if p == "gunw" else "acquisition_time"
        t.add_row(p, str(len(g)), str(int(g["cached"].sum())), str(len(todo)), human_size(todo["size_bytes"].sum()),
                  f"~{human_size(len(todo) * PRODUCTS[p]['est_bytes'])}", f"{g[tcol].min():%Y-%m-%d} -> {g[tcol].max():%Y-%m-%d}")
    con.print(t)
    if dry_run:
        return cat

    todo = cat[~cat["cached"]]
    results = []
    cols = [SpinnerColumn(), TextColumn("[bold]{task.description:<30}"), BarColumn(bar_width=30), TaskProgressColumn(),
            TextColumn("{task.fields[info]}"), TimeElapsedColumn(), TimeRemainingColumn()]
    with Progress(*cols, console=con, refresh_per_second=4) as prog:
        overall = prog.add_task("all granules", total=len(cat), info="")
        prog.advance(overall, len(cat) - len(todo))
        net, per = {"b": 0}, {}
        if len(todo):
            with Manager() as mgr:
                q = mgr.Queue()
                with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as ex:
                    pending = {ex.submit(stream_one, r.drop(labels=["geometry"]).to_dict(), bounds, str(out_dir), q)
                               for _, r in todo.iterrows()}
                    while pending:
                        while not q.empty():
                            gid, kind, val = q.get()
                            if gid not in per:
                                tok = gid.split("_")
                                prod = "gunw" if "GUNW" in gid else "sme2"
                                per[gid] = {"stage": "", "b": 0, "task": prog.add_task(
                                    f"{prod} {tok[5]}{tok[6]} {tok[11][:8]}", total=PRODUCTS[prod]["est_bytes"], info="")}
                            st = per[gid]
                            if kind == "bytes":
                                st["b"] += val
                                net["b"] += val
                                prog.advance(st["task"], val)
                                prog.update(overall, info=f"{human_size(net['b'])} transferred")
                            elif kind == "stage":
                                st["stage"] = val
                            elif kind in ("done", "skip"):
                                prog.update(st["task"], visible=False)
                                continue
                            elif kind == "error":
                                prog.update(st["task"], info=f"[red]{val}"[:70])
                                continue
                            prog.update(st["task"], info=f"{st['stage']:<24} {human_size(st['b'])}")
                        for f in [f for f in pending if f.done()]:
                            pending.discard(f)
                            results.append(f.result())
                            prog.advance(overall)
                        time.sleep(0.2)
    res = pd.DataFrame(results)
    if len(res):
        ok = res[res["status"] == "ok"]
        con.print(f"streamed {len(ok)}/{len(res)}: {human_size(ok['bytes'].sum())} transferred, "
                  f"{human_size(ok['disk_bytes'].sum())} written")
        for _, e in res[res["status"] == "error"].iterrows():
            con.print(f"[red]FAILED {e['granule_ur']}: {e['error']}")
    for p in PRODUCTS:
        d = out_dir / p
        if d.exists():
            con.print(f"{p}: {len(list(d.glob('*.npz')))} crops, {human_size(sum(f.stat().st_size for f in d.glob('*.npz')))} on disk")
    con.print(f"catalogue -> {report_file(path)}")
    return cat
