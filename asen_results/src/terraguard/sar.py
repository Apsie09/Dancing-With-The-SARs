"""Stage 4: stream NISAR GCOV city crops (no full downloads) and extract incident patches.

Layout on disk (`[sar].out_dir`, default data/sar):
  crops/<granule>.tif        original gamma0 (HH, HV) + numberOfLooks, float32, on one shared city grid
  crops/<granule>_mask.tif   GCOV `mask` (255 fill, 0 invalid, 1..n valid sub-swath) + inputDataExceptionMask
  crops/<granule>.json       identification + processing parameters (calibration, corrections, CRID)
  patches.h5                 per-match patches: raw gamma0, filtered dB, valid mask, looks
  sar_patches.parquet        one row per patch, linking it to incident, granule, timing and quality

Raw measurements and analysis layers are kept separate. No dataset-wide normalisation happens here:
statistics for ML normalisation must come from the training split (Stage 6) to avoid leakage.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from .config import ROOT, UTM_CRS, WGS84, Config, human_size

GCOV = "/science/LSAR/GCOV"
GRID = f"{GCOV}/grids/frequencyA"
POSTING = 10.0
LATTICE_PHASE = 5.0  # pixel centres at x, y = 5 (mod 10) m, verified across all Kitchener tracks
EST_TRANSFER_PER_PASS = 200 * 2**20  # measured by `pixi run probe`: ~100-190 MB per city crop


# --------------------------------------------------------------------------- shared city grid
@dataclass(frozen=True)
class CityGrid:
    x0: float  # left edge (m)
    y1: float  # top edge (m)
    width: int
    height: int

    @classmethod
    def from_config(cls, cfg: Config) -> "CityGrid":
        aoi = gpd.GeoSeries([box(*cfg.section("nisar")["aoi_bbox"])], crs=WGS84).to_crs(UTM_CRS).iloc[0]
        minx, miny, maxx, maxy = aoi.bounds
        x0, x1 = np.floor(minx / POSTING) * POSTING, np.ceil(maxx / POSTING) * POSTING
        y0, y1 = np.floor(miny / POSTING) * POSTING, np.ceil(maxy / POSTING) * POSTING
        return cls(float(x0), float(y1), int((x1 - x0) / POSTING), int((y1 - y0) / POSTING))

    @property
    def transform(self):
        from rasterio.transform import from_origin

        return from_origin(self.x0, self.y1, POSTING, POSTING)

    def rowcol(self, x: float, y: float) -> tuple[int, int]:
        return int((self.y1 - y) // POSTING), int((x - self.x0) // POSTING)


# --------------------------------------------------------------------------- selection
def select(cfg: Config, n_incidents: int | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (granules to stream, selected matches). n_incidents=None -> every usable match."""
    s = cfg.section("sar")
    m = gpd.read_parquet(cfg.matches_parquet)
    m = m[m["match_confidence"] != "low"]
    if n_incidents is not None:
        cov = pd.read_parquet(cfg.coverage_parquet)
        inc = pd.read_parquet(cfg.incidents_parquet, columns=["incident_id", "location_suspect"])
        cov = cov.merge(inc, on="incident_id")
        cand = cov[cov["has_event_with_reference"] & cov["has_before_after"] & cov["is_primary_record"]
                   & ~cov["is_cancelled"] & ~cov["date_suspect"] & ~cov["location_suspect"]]
        cand = cand.sort_values(["n_event_window", "nearest_event_days", "n_pre"], ascending=[False, True, False])
        picked = []
        for _, c in cand.head(n_incidents).iterrows():
            g = m[(m["incident_id"] == c["incident_id"]) & (m["comparison_group"] == c["best_comparison_group"])]
            picked += [g[g["temporal_category"] == "potential_event_window"],
                       g[g["temporal_category"] == "pre_event"].nsmallest(s["max_pre_per_incident"], "abs_delta_days"),
                       g[g["temporal_category"] == "post_event"].nsmallest(s["max_post_per_incident"], "abs_delta_days")]
        m = pd.concat(picked)
    acq = gpd.read_parquet(cfg.acquisitions_parquet)
    gran = acq[acq["granule_ur"].isin(m["granule_ur"])].sort_values("start_time")
    return gran, m


# --------------------------------------------------------------------------- worker (one granule)
CONNECT_TIMEOUT_S = 30
READ_TIMEOUT_S = 90  # one 4 MB block normally arrives in a few seconds


def https_session(auth):
    """Earthdata HTTPS filesystem like earthaccess.get_fsspec_https_session(), plus socket timeouts.

    Without timeouts a request the server never answers blocks forever (seen on 2026-11-14:
    one granule hung 13+ min at `open`). A timeout raises, and stream_granule retries.
    """
    import aiohttp
    import fsspec

    return fsspec.filesystem("https", skip_instance_cache=True, client_kwargs={
        "headers": {"Authorization": f"Bearer {auth.token['access_token']}"},
        "trust_env": False,  # earthaccess: env proxies + bearer token break auth
        "timeout": aiohttp.ClientTimeout(total=None, sock_connect=CONNECT_TIMEOUT_S, sock_read=READ_TIMEOUT_S),
    })


def _scalars(group, skip=("boundingPolygon",), depth=2) -> dict:
    import h5py

    out = {}
    for k, v in group.items():
        if k in skip:
            continue
        if isinstance(v, h5py.Dataset) and v.shape == ():
            val = v[()]
            out[k] = val.decode() if isinstance(val, bytes) else (val.item() if hasattr(val, "item") else val)
        elif isinstance(v, h5py.Group) and depth > 1:
            sub = _scalars(v, skip, depth - 1)
            if sub:
                out[k] = sub
    return out


def stream_granule(row: dict, grid: CityGrid, out_dir: str, block_size: int, layers: list[str], queue) -> dict:
    """Stream the city window of one granule onto the shared grid and write GeoTIFFs + metadata JSON."""
    import earthaccess
    import h5py
    import rasterio

    gid = row["granule_ur"]
    send = (lambda *a: queue.put((gid, *a))) if queue is not None else (lambda *a: None)
    out = Path(out_dir) / "crops"
    tif, mtif, meta_path = out / f"{gid}.tif", out / f"{gid}_mask.tif", out / f"{gid}.json"
    if tif.exists() and mtif.exists() and meta_path.exists():
        send("skip", 0)
        return {"granule_ur": gid, "status": "cached", "bytes": 0, "seconds": 0.0}

    t0 = time.time()
    fs = https_session(earthaccess.login(strategy="netrc"))
    for attempt in range(3):
        try:
            remote = fs.open(row["h5_https"], "rb", block_size=block_size, cache_type="blockcache",
                             cache_options={"maxblocks": 256})
            cache, fetch = remote.cache, remote.cache.fetcher
            total = {"n": 0}

            def counting(start, end, _fetch=fetch):
                total["n"] += end - start
                send("bytes", end - start)
                return _fetch(start, end)

            cache.fetcher = counting
            send("stage", "open")
            h5 = h5py.File(remote, "r")
            g = h5[GRID]
            x, y = g["xCoordinates"][:], g["yCoordinates"][:]
            if abs(x[0] % POSTING - LATTICE_PHASE) > 1e-6 or abs(y[0] % POSTING - LATTICE_PHASE) > 1e-6:
                raise RuntimeError(f"grid phase mismatch ({x[0] % 10}, {y[0] % 10}); needs resampling")
            # Target pixel centres -> source indices (same lattice, so a pure offset).
            cx0 = int(round((grid.x0 + POSTING / 2 - x[0]) / POSTING))
            ry0 = int(round((y[0] - (grid.y1 - POSTING / 2)) / POSTING))
            src_c = slice(max(cx0, 0), min(cx0 + grid.width, len(x)))
            src_r = slice(max(ry0, 0), min(ry0 + grid.height, len(y)))
            dst_c = slice(src_c.start - cx0, src_c.stop - cx0)
            dst_r = slice(src_r.start - ry0, src_r.stop - ry0)
            if src_c.stop <= src_c.start or src_r.stop <= src_r.start:
                raise RuntimeError("granule does not overlap the city grid")

            def read(name, dtype, fill):
                send("stage", name)
                arr = np.full((grid.height, grid.width), fill, dtype=dtype)
                arr[dst_r, dst_c] = g[name][src_r, src_c]
                return arr

            pols = [p for p in ("HHHH", "HVHV") if p in g]
            bands = {p: read(p, "float32", np.nan) for p in pols}
            looks = read("numberOfLooks", "float32", np.nan) if "numberOfLooks" in layers else None
            mask = read("mask", "uint16", 255)
            exc = read("inputDataExceptionMask", "uint16", 0) if "inputDataExceptionMask" in layers else None

            send("stage", "metadata")
            meta = {
                "granule_ur": gid,
                "polarizations": pols,
                "identification": _scalars(h5["/science/LSAR/identification"]),
                "processing_parameters": _scalars(h5[f"{GCOV}/metadata/processingInformation/parameters"],
                                                  skip=("runConfigurationContents", "xCoordinates", "yCoordinates")),
                "run_configuration": h5[f"{GCOV}/metadata/processingInformation/parameters/runConfigurationContents"][()].decode(),
                "source_window": {"rows": [src_r.start, src_r.stop], "cols": [src_c.start, src_c.stop]},
                "city_grid": {"x0": grid.x0, "y1": grid.y1, "width": grid.width, "height": grid.height,
                              "posting_m": POSTING, "crs": UTM_CRS},
                "radiometry": "gamma0 (RTC), linear power; sigma0 = gamma0 * rtcGammaToSigmaFactor (not stored)",
            }
            h5.close()
            remote.close()

            send("stage", "write")
            out.mkdir(parents=True, exist_ok=True)
            prof = dict(driver="GTiff", width=grid.width, height=grid.height, crs=UTM_CRS, transform=grid.transform,
                        tiled=True, blockxsize=512, blockysize=512, compress="deflate", BIGTIFF="IF_SAFER")
            data = [bands[p] for p in pols] + ([looks] if looks is not None else [])
            names = [f"gamma0_{p[:2]}" for p in pols] + (["numberOfLooks"] if looks is not None else [])
            tags = {"granule_ur": gid, "radiometry": meta["radiometry"],
                    "crid": meta["identification"].get("compositeReleaseId", ""),
                    "product_version": meta["identification"].get("productVersion", "")}
            tmp = tif.with_suffix(".tif.part")
            with rasterio.open(tmp, "w", count=len(data), dtype="float32", nodata=np.nan, predictor=3, **prof) as ds:
                for i, (arr, nm) in enumerate(zip(data, names), 1):
                    ds.write(arr, i)
                    ds.set_band_description(i, nm)
                ds.update_tags(**tags)
            mdata = [mask] + ([exc] if exc is not None else [])
            mtmp = mtif.with_suffix(".tif.part")
            with rasterio.open(mtmp, "w", count=len(mdata), dtype="uint16", predictor=2, **prof) as ds:
                for i, (arr, nm) in enumerate(zip(mdata, ["mask", "inputDataExceptionMask"]), 1):
                    ds.write(arr, i)
                    ds.set_band_description(i, nm)
                ds.update_tags(**tags)
            meta_path.write_text(json.dumps(meta, indent=1, default=str))
            os.replace(tmp, tif)
            os.replace(mtmp, mtif)
            valid = (mask > 0) & (mask < 255)
            res = {"granule_ur": gid, "status": "ok", "bytes": total["n"], "seconds": time.time() - t0,
                   "valid_frac": float(valid.mean()),
                   "disk_bytes": tif.stat().st_size + mtif.stat().st_size + meta_path.stat().st_size}
            send("done", res)
            return res
        except Exception as e:  # noqa: BLE001 - report and retry, never kill the whole run
            if attempt == 2:
                res = {"granule_ur": gid, "status": "error", "error": f"{type(e).__name__}: {e}",
                       "trace": traceback.format_exc(limit=3), "bytes": 0, "seconds": time.time() - t0}
                send("error", res["error"])
                return res
            send("stage", f"retry {attempt + 1}")
            time.sleep(5 * (attempt + 1))


# --------------------------------------------------------------------------- patches
def _speckle(lin: np.ndarray, kind: str, size: int, enl: float) -> np.ndarray:
    """NaN-aware speckle filter on linear intensity (Lee or boxcar).

    The Lee filter's speckle variance comes from the product's own equivalent number of looks:
    for multilooked intensity, CV^2 = 1 / ENL (`numberOfLooks`)."""
    from scipy.ndimage import uniform_filter

    if kind == "none":
        return lin
    ok = np.isfinite(lin)
    z = np.where(ok, lin, 0.0)
    w = uniform_filter(ok.astype("float64"), size)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = uniform_filter(z, size) / w
        if kind == "boxcar":
            out = mean
        else:
            sq = uniform_filter(z * z, size) / w
            var = np.maximum(sq - mean**2, 0)
            noise = 1.0 / max(enl, 1.0) if np.isfinite(enl) else 0.25  # speckle CV^2
            k = np.clip((var - noise * mean**2) / np.maximum(var * (1 + noise), 1e-12), 0, 1)
            out = mean + k * (z - mean)
    return np.where(ok, out, np.nan).astype("float32")


def extract_patches(cfg: Config, progress=None) -> pd.DataFrame:
    """Cut a patch around every usable match whose granule crop exists (crops cover the whole city)."""
    m = gpd.read_parquet(cfg.matches_parquet)
    m = m[(m["match_confidence"] != "low")].copy()
    m["site_id"] = "inc_" + m["incident_id"].astype(str)
    m["site_type"] = "incident"
    return cut_patches(cfg, m, "patches.h5", "sar_patches.parquet", progress, label="patches")


def cut_patches(cfg: Config, m: gpd.GeoDataFrame, h5_name: str, index_name: str, progress=None,
                label: str = "patches") -> gpd.GeoDataFrame:
    """Cut one patch per row of `m` (needs granule_ur, site_id, point geometry) from the cached crops."""
    import h5py
    import rasterio
    from rasterio.windows import Window

    s = cfg.section("sar")
    out_dir = ROOT / s["out_dir"]
    grid = CityGrid.from_config(cfg)
    size, pad = s["patch_size_px"], s["filter_size"]
    have = {p.stem for p in (out_dir / "crops").glob("*.tif") if not p.stem.endswith("_mask")}
    m = m[m["granule_ur"].isin(have)].sort_values(["granule_ur", "site_id"]).reset_index(drop=True)
    if m.empty:
        return gpd.GeoDataFrame()
    utm = gpd.GeoSeries(m.geometry, crs=WGS84).to_crs(UTM_CRS)
    n = len(m)
    h5_path = out_dir / h5_name
    tmp = h5_path.with_suffix(".h5.part")
    rows = []
    task = progress.add_task(label, total=n, info="") if progress else None
    with h5py.File(tmp, "w") as h5:
        kw = dict(chunks=(1, 2, size, size), compression="gzip", compression_opts=4, shuffle=True)
        d_raw = h5.create_dataset("gamma0", (n, 2, size, size), "float32", fillvalue=np.nan, **kw)
        d_db = h5.create_dataset("db_filtered", (n, 2, size, size), "float32", fillvalue=np.nan, **kw)
        d_valid = h5.create_dataset("valid", (n, size, size), "bool", chunks=(1, size, size), compression="gzip")
        d_looks = h5.create_dataset("numberOfLooks", (n, size, size), "float32", chunks=(1, size, size),
                                    compression="gzip", shuffle=True)
        h5.attrs.update({"channels": json.dumps(["HH", "HV"]), "patch_size_px": size, "posting_m": POSTING,
                         "crs": UTM_CRS, "speckle_filter": s["speckle_filter"], "filter_size": pad,
                         "gamma0": "original linear gamma0 (RTC), invalid pixels kept as-is; use `valid`",
                         "db_filtered": "10*log10(speckle-filtered gamma0), NaN where invalid"})
        for gid, grp in m.groupby("granule_ur", sort=False):
            with rasterio.open(out_dir / "crops" / f"{gid}.tif") as ds, \
                 rasterio.open(out_dir / "crops" / f"{gid}_mask.tif") as ms:
                band_names = list(ds.descriptions)
                for i, r in grp.iterrows():
                    pt = utm.loc[i]
                    row, col = grid.rowcol(pt.x, pt.y)
                    r0, c0 = row - size // 2, col - size // 2
                    win = Window(c0 - pad, r0 - pad, size + 2 * pad, size + 2 * pad)
                    big = ds.read(window=win, boundless=True, fill_value=np.nan)
                    mk = ms.read(window=win, boundless=True, fill_value=255)
                    exc = mk[1] if mk.shape[0] > 1 else np.zeros_like(mk[0])
                    valid_big = (mk[0] > 0) & (mk[0] < 255) & (exc == 0)
                    core = (slice(pad, pad + size), slice(pad, pad + size))
                    looks_big = (big[band_names.index("numberOfLooks")] if "numberOfLooks" in band_names
                                 else np.full(big.shape[1:], np.nan, "float32"))
                    looks = looks_big[core]
                    enl = float(np.nanmedian(looks_big)) if np.isfinite(looks_big).any() else np.nan
                    raw = np.full((2, size, size), np.nan, "float32")
                    dbf = np.full((2, size, size), np.nan, "float32")
                    for b, pol in enumerate(("gamma0_HH", "gamma0_HV")):
                        if pol not in band_names:
                            continue
                        lin = big[band_names.index(pol)]
                        raw[b] = lin[core]
                        clean = np.where(valid_big & np.isfinite(lin) & (lin > 0), lin, np.nan)
                        with np.errstate(divide="ignore", invalid="ignore"):
                            dbf[b] = 10 * np.log10(_speckle(clean, s["speckle_filter"], pad, enl)[core])
                    valid = valid_big[core] & np.isfinite(raw[0]) & (raw[0] > 0)
                    k = len(rows)
                    d_raw[k], d_db[k], d_valid[k], d_looks[k] = raw, dbf, valid, looks
                    x0, y1 = grid.x0 + c0 * POSTING, grid.y1 - r0 * POSTING
                    rows.append({**{c: r[c] for c in m.columns if c != "geometry"},
                                 "patch_index": k, "patch_row0": r0, "patch_col0": c0,
                                 "patch_geometry_utm": box(x0, y1 - size * POSTING, x0 + size * POSTING, y1).wkt,
                                 "valid_frac": float(valid.mean()),
                                 # inputDataExceptionMask != 0 (e.g. qFSP-H1 sample slip): measured on
                                 # Kitchener to bias HH by ~-1 to -1.5 dB, so these pixels are invalid.
                                 "exception_frac": float((exc[core] > 0).mean()),
                                 "outside_coverage_frac": float((mk[0][core] == 255).mean()),
                                 "hh_db_median": float(np.nanmedian(dbf[0])) if np.isfinite(dbf[0]).any() else np.nan,
                                 "hv_db_median": float(np.nanmedian(dbf[1])) if np.isfinite(dbf[1]).any() else np.nan,
                                 "mean_looks": float(np.nanmean(looks)) if np.isfinite(looks).any() else np.nan,
                                 "crop_path": str((out_dir / "crops" / f"{gid}.tif").relative_to(ROOT)),
                                 "geometry": r["geometry"]})
                    if progress:
                        progress.advance(task)
    os.replace(tmp, h5_path)
    idx = gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84)
    idx.to_parquet(out_dir / index_name)
    return idx


# --------------------------------------------------------------------------- orchestration + progress UI
def run(cfg: Config, n_incidents: int | None = None, use_all: bool = False, workers: int | None = None,
        dry_run: bool = False) -> None:
    from multiprocessing import Manager

    from rich.console import Console
    from rich.progress import (BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TaskProgressColumn,
                               TextColumn, TimeElapsedColumn, TimeRemainingColumn)
    from rich.table import Table

    s = cfg.section("sar")
    con = Console()
    n = None if use_all else (n_incidents or s["default_incidents"])
    gran, sel = select(cfg, n)
    out_dir = ROOT / s["out_dir"]
    cached = {p.stem for p in (out_dir / "crops").glob("*.json")} if (out_dir / "crops").exists() else set()
    todo = gran[~gran["granule_ur"].isin(cached)]
    grid = CityGrid.from_config(cfg)

    t = Table(title="Stage 4 plan", show_header=False)
    t.add_row("selection", "all usable matches" if n is None else f"top {n} incidents ({sel['incident_id'].nunique()} selected)")
    t.add_row("matches selected", str(len(sel)))
    t.add_row("granules", f"{len(gran)} ({len(gran) - len(todo)} already cached, {len(todo)} to stream)")
    t.add_row("remote size of those granules", human_size(todo["size_bytes"].sum()) + "  (NOT downloaded)")
    t.add_row("estimated network transfer", f"~{human_size(len(todo) * EST_TRANSFER_PER_PASS)}")
    t.add_row("city grid", f"{grid.width} x {grid.height} px @ 10 m ({grid.width / 100:.1f} x {grid.height / 100:.1f} km)")
    t.add_row("estimated disk (crops)", f"~{human_size(len(todo) * grid.width * grid.height * 4 * 3 * 0.8)}")
    t.add_row("workers / block size", f"{workers or s['workers']} / {s['block_size_mb']} MB")
    con.print(t)
    if dry_run:
        return

    results = []
    columns = [SpinnerColumn(), TextColumn("[bold]{task.description:<34}"), BarColumn(bar_width=30),
               TaskProgressColumn(), TextColumn("{task.fields[info]}"), TimeElapsedColumn()]
    with Progress(*columns, TimeRemainingColumn(), console=con, refresh_per_second=4) as prog:
        overall = prog.add_task("all granules", total=len(gran), info="")
        net = {"bytes": 0}
        prog.advance(overall, len(gran) - len(todo))  # already cached
        if len(todo):
            per: dict[str, dict] = {}
            with Manager() as mgr:
                q = mgr.Queue()
                with ProcessPoolExecutor(max_workers=workers or s["workers"], mp_context=get_context("spawn")) as ex:
                    pending = {ex.submit(stream_granule, row.to_dict(), grid, str(out_dir),
                                         int(s["block_size_mb"] * 2**20), s["quality_layers"], q)
                               for _, row in todo.iterrows()}
                    while pending:
                        while not q.empty():
                            gid, kind, val = q.get()
                            if gid not in per:
                                tok = gid.split("_")
                                per[gid] = {"stage": "start", "bytes": 0, "task": prog.add_task(
                                    f"{tok[5]}{tok[6]} f{tok[7]} {tok[11][:8]}", total=EST_TRANSFER_PER_PASS, info="")}
                            st = per[gid]
                            if kind == "bytes":
                                st["bytes"] += val
                                net["bytes"] += val
                                prog.advance(st["task"], val)
                                prog.update(overall, info=f"{human_size(net['bytes'])} transferred")
                            elif kind == "stage":
                                st["stage"] = val
                            elif kind == "done":
                                prog.update(st["task"], visible=False)
                                continue
                            elif kind == "error":
                                prog.update(st["task"], info=f"[red]error: {val}"[:70])
                                continue
                            elif kind == "skip":
                                prog.update(st["task"], visible=False)
                                continue
                            prog.update(st["task"], info=f"{st['stage']:<22} {human_size(st['bytes'])}")
                        for f in [f for f in pending if f.done()]:
                            pending.discard(f)
                            results.append(f.result())
                            prog.advance(overall)
                        time.sleep(0.2)
        res = pd.DataFrame(results)
        prog.update(overall, info=f"{human_size(net['bytes'])} transferred")
        idx = extract_patches(cfg, prog)

    if len(res):
        ok = res[res["status"] == "ok"]
        log = out_dir / "stream_log.parquet"
        old = pd.read_parquet(log) if log.exists() else pd.DataFrame()
        pd.concat([old, res.drop(columns=["trace"], errors="ignore")]).to_parquet(log)
        con.print(f"\nstreamed {len(ok)}/{len(res)} granules: {human_size(ok['bytes'].sum())} transferred, "
                  f"{human_size(ok['disk_bytes'].sum())} written, mean {ok['seconds'].mean():.0f} s/granule")
        for _, e in res[res["status"] == "error"].iterrows():
            con.print(f"[red]FAILED {e['granule_ur']}: {e['error']}")
    disk = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    con.print(f"patches: {len(idx)} from {idx['granule_ur'].nunique() if len(idx) else 0} granules, "
              f"{idx['incident_id'].nunique() if len(idx) else 0} incidents -> data/sar/patches.h5 + sar_patches.parquet")
    con.print(f"[bold]data/sar total on disk: {human_size(disk)}")
