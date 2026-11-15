"""Coryell (Texas) rural leak-visibility test with calibrated NISAR GCOV.

Same question as Kitchener Stages 4-6, in the most favourable setting we have: rural pipes under
fields, large leaks (median ~20 gpm), repair time logged on site. Only small windows around leaks and
their controls are streamed (no city crops, no full granules).

  pixi run coryell --dry-run      # plan + measured-chunk transfer estimate
  pixi run coryell --workers 6    # stream site windows (resumable)
  pixi run coryell --analyse      # patches -> features -> site-vs-control evaluation
"""
from __future__ import annotations

import copy
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
from shapely.geometry import Point, Polygon, box

from .config import ROOT, WGS84, Config, human_size, report_file
from .matching import categorize

GRID = "/science/LSAR/GCOV/grids/frequencyA"
MATURITY = {"NISAR_L2_GCOV_BETA_V1": "beta", "NISAR_L2_GCOV_PROVISIONAL_V1": "provisional", "NISAR_L2_GCOV_V1": "validated"}
CHUNK = 512
BYTES_PER_FLOAT_CHUNK = 1.9 * 2**20   # measured on Kitchener GCOV (gzip-1 float32 512x512)
BYTES_PER_MASK_CHUNK = 0.1 * 2**20


def _dir(cfg: Config) -> Path:
    d = ROOT / cfg.section("sar")["out_dir"] / cfg.section("coryell").get("subdir", "coryell")
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- sites
def leaks(cfg: Config) -> gpd.GeoDataFrame:
    c = cfg.section("coryell")
    L = gpd.read_file(ROOT / c["leaks"])
    L["time"] = pd.to_datetime(L["datetime"], unit="ms", utc=True, errors="coerce")
    L["gpm"] = pd.to_numeric(L["approximate_water_loss_gpm"].astype(str).str.extract(r"(\d+\.?\d*)")[0], errors="coerce")
    L = L[L["time"].notna() & L.geometry.within(box(*c["district_bbox"]))]
    out = gpd.GeoDataFrame({"leak_id": L["ObjectId"].astype(int), "time": L["time"], "gpm": L["gpm"],
                            "cause": L["cause_of_leak"], "geometry": L.geometry}, crs=WGS84)
    return out.reset_index(drop=True)


def controls(cfg: Config, all_leaks: gpd.GeoDataFrame, test: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Points on district pipes near each test leak, away from any other leak in +-1 year."""
    c = cfg.section("coryell")
    rng = np.random.default_rng(42)
    pipes = gpd.read_file(ROOT / c["pipes"]).to_crs(c["utm_crs"])
    pts = []
    for g, mat, dia in zip(pipes.geometry, pipes.get("Material"), pipes.get("Diameter")):
        if g is None or g.is_empty:
            continue
        for d in np.arange(12.5, g.length, 25.0):
            p = g.interpolate(d)
            pts.append((p.x, p.y, mat, dia))
    cand = pd.DataFrame(pts, columns=["x", "y", "material", "diameter_in"])
    lu = all_leaks.to_crs(c["utm_crs"])
    lxy = np.c_[lu.geometry.x, lu.geometry.y]
    lt = lu["time"].dt.tz_convert(None).to_numpy(dtype="datetime64[ns]")
    tu = test.to_crs(c["utm_crs"])
    out = []
    cxy = cand[["x", "y"]].to_numpy()
    for r, g in zip(test.itertuples(), tu.geometry):
        d = np.hypot(cxy[:, 0] - g.x, cxy[:, 1] - g.y)
        band = np.where((d >= c["control_min_m"]) & (d <= c["control_max_m"]))[0]
        near_t = np.abs((lt - r.time.tz_convert(None).to_datetime64()) / np.timedelta64(1, "D")) <= c["exclusion_days"]
        chosen = []
        for j in rng.permutation(band):
            if len(chosen) == c["controls_per_leak"]:
                break
            x, y = cxy[j]
            if (np.hypot(lxy[near_t, 0] - x, lxy[near_t, 1] - y) < c["exclusion_m"]).any():
                continue
            if all(np.hypot(x - cxy[k, 0], y - cxy[k, 1]) >= c["control_spacing_m"] for k in chosen):
                chosen.append(j)
        for k, j in enumerate(chosen):
            out.append({"control_id": f"{r.leak_id}_c{k}", "leak_id": r.leak_id, "material": cand.loc[j, "material"],
                        "diameter_in": cand.loc[j, "diameter_in"], "geometry": Point(cxy[j])})
    return gpd.GeoDataFrame(out, geometry="geometry", crs=c["utm_crs"]).to_crs(WGS84)


# --------------------------------------------------------------------------- catalogue + matching
def catalogue(cfg: Config) -> gpd.GeoDataFrame:
    c = cfg.section("coryell")
    rows = []
    for sn, mat in MATURITY.items():
        for g in earthaccess.search_data(short_name=sn, bounding_box=tuple(c["district_bbox"]), count=-1):
            u = g["umm"]
            name = u["GranuleUR"]
            t = name.split("_")
            if t[8] != "4005" or t[-3] != "F":  # full-frame 40 MHz only (..._<CRID>_N_F_J_001)
                continue
            pts = u["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]["Boundary"]["Points"]
            h5 = [x for x in u["DataGranule"]["ArchiveAndDistributionInformation"] if x["Name"].endswith(".h5")]
            rows.append({"granule_ur": name, "maturity": mat, "stack": f"{t[5]}{t[6]}_{t[7]}", "track_dir": f"{t[5]}{t[6]}",
                         "start_time": pd.Timestamp(t[11], tz="UTC"), "crid": t[13], "counter": int(t[-1]),
                         "size_bytes": h5[0]["SizeInBytes"] if h5 else 0,
                         "h5_https": next((x for x in g.data_links() if x.endswith(".h5")), None),
                         "geometry": Polygon([(p["Longitude"], p["Latitude"]) for p in pts])})
    cat = gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84)
    cat["key"] = cat["stack"] + "_" + cat["start_time"].dt.strftime("%Y%m%dT%H%M")
    cat["rank"] = cat["maturity"].map({"beta": 0, "provisional": 1, "validated": 2})
    cat = cat.sort_values(["rank", "counter"]).drop_duplicates("key", keep="last").drop(columns="rank")
    return cat.reset_index(drop=True)


def match(cfg: Config, test: gpd.GeoDataFrame, cat: gpd.GeoDataFrame) -> pd.DataFrame:
    w = cfg.section("matching")
    win = {k: tuple(w[k]) for k in ("pre_event", "potential_event_window", "post_event")}
    j = gpd.sjoin(test, cat, predicate="within")
    j["delta_days"] = (j["start_time"] - j["time"]).dt.total_seconds() / 86400
    j = j[j["delta_days"].between(win["pre_event"][0], win["post_event"][1])].copy()
    j["temporal_category"] = categorize(j["delta_days"].to_numpy(), np.zeros(len(j)), win)
    return pd.DataFrame(j.drop(columns=["geometry", "index_right"]))


def choose_stacks(cfg: Config, m: pd.DataFrame) -> list[str]:
    """Best stack per look direction: most leaks with pre + event-window passes (non-beta)."""
    m = m[m["maturity"] != "beta"]
    score = (m.groupby(["stack", "leak_id"])["temporal_category"].agg(lambda s: {"pre_event", "potential_event_window"} <= set(s))
              .groupby("stack").sum().rename("leaks_pre_event").to_frame())
    score["passes"] = m.groupby("stack")["granule_ur"].nunique()
    score["dir"] = score.index.str[3]
    n = cfg.section("coryell")["n_stacks_per_direction"]
    best = score.sort_values(["leaks_pre_event", "passes"], ascending=False).groupby("dir").head(n)
    return best.index.tolist(), score.sort_values("leaks_pre_event", ascending=False)


# --------------------------------------------------------------------------- streaming
def _window_slices(x, y, px, py, half):
    c = int(round((px - x[0]) / (x[1] - x[0])))
    r = int(round((py - y[0]) / (y[1] - y[0])))
    return r - half, r + half, c - half, c + half


def stream_granule(row: dict, sites: list[dict], half: int, out_dir: str, queue) -> dict:
    import h5py
    from pyproj import Transformer

    from .sar import https_session

    gid = row["granule_ur"]
    send = (lambda *a: queue.put((gid, *a))) if queue is not None else (lambda *a: None)
    out = Path(out_dir) / f"{gid}.npz"
    if out.exists():
        send("skip", 0)
        return {"granule_ur": gid, "status": "cached", "bytes": 0}
    t0 = time.time()
    for attempt in range(3):
        try:
            fs = https_session(earthaccess.login(strategy="netrc"))
            remote = fs.open(row["h5_https"], "rb", block_size=2 << 20, cache_type="blockcache", cache_options={"maxblocks": 2048})
            fetch, total = remote.cache.fetcher, {"n": 0}

            def counting(a, b, _f=fetch):
                total["n"] += b - a
                send("bytes", b - a)
                return _f(a, b)

            remote.cache.fetcher = counting
            send("stage", "open")
            h5 = h5py.File(remote, "r")
            g = h5[GRID]
            x, y = g["xCoordinates"][:], g["yCoordinates"][:]
            epsg = int(g["projection"][()])
            tr = Transformer.from_crs(4326, epsg, always_xy=True)
            S = 2 * half
            arrs = {k: np.full((len(sites), S, S), np.nan if k in ("hh", "hv") else 255 if k == "mask" else 0,
                               dtype="float32" if k in ("hh", "hv") else "uint16") for k in ("hh", "hv", "mask", "exc")}
            ok = np.zeros(len(sites), bool)
            # sort sites by chunk so cached blocks are reused
            xy = [tr.transform(s["lon"], s["lat"]) for s in sites]
            order = sorted(range(len(sites)), key=lambda i: (int((xy[i][1] - y[0]) / (y[1] - y[0])) // CHUNK,
                                                             int((xy[i][0] - x[0]) / (x[1] - x[0])) // CHUNK))
            for n, i in enumerate(order):
                r0, r1, c0, c1 = _window_slices(x, y, *xy[i], half)
                if r0 < 0 or c0 < 0 or r1 > len(y) or c1 > len(x):
                    continue
                for k, ds in (("hh", "HHHH"), ("hv", "HVHV"), ("mask", "mask"), ("exc", "inputDataExceptionMask")):
                    arrs[k][i] = g[ds][r0:r1, c0:c1]
                ok[i] = True
                if n % 50 == 0:
                    send("stage", f"site {n}/{len(sites)}")
            h5.close()
            remote.close()
            tmp = out.with_suffix(".part.npz")
            np.savez_compressed(tmp, site_id=np.array([s["site_id"] for s in sites]), ok=ok, epsg=epsg,
                                lattice=np.array([x[0] % 10, y[0] % 10]), **arrs)
            tmp.replace(out)
            res = {"granule_ur": gid, "status": "ok", "bytes": total["n"], "seconds": time.time() - t0,
                   "sites": int(ok.sum()), "disk_bytes": out.stat().st_size}
            send("done", res)
            return res
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                send("error", f"{type(e).__name__}: {e}")
                return {"granule_ur": gid, "status": "error", "error": f"{type(e).__name__}: {e}",
                        "trace": traceback.format_exc(limit=3), "bytes": 0}
            send("stage", f"retry {attempt + 1}")
            time.sleep(5 * (attempt + 1))


def estimate_chunks(cfg: Config, gran: pd.DataFrame, sites_by_granule: dict, half: int) -> pd.Series:
    """Distinct 512x512 chunks touched per granule, using one granule's real grid per stack."""
    import h5py
    from pyproj import Transformer

    from .sar import https_session

    fs = https_session(earthaccess.login(strategy="netrc"))
    est = {}
    for stack, g in gran.groupby("stack"):
        f = h5py.File(fs.open(g.iloc[0]["h5_https"], "rb", block_size=1 << 20, cache_type="blockcache"), "r")
        x, y = f[GRID]["xCoordinates"][:], f[GRID]["yCoordinates"][:]
        tr = Transformer.from_crs(4326, int(f[GRID]["projection"][()]), always_xy=True)
        for gid in g["granule_ur"]:
            chunks = set()
            for s in sites_by_granule[gid]:
                px, py = tr.transform(s["lon"], s["lat"])
                r0, r1, c0, c1 = _window_slices(x, y, px, py, half)
                for rr in {r0 // CHUNK, (r1 - 1) // CHUNK}:
                    for cc in {c0 // CHUNK, (c1 - 1) // CHUNK}:
                        chunks.add((rr, cc))
            est[gid] = len(chunks)
    return pd.Series(est)


# --------------------------------------------------------------------------- orchestration
def plan(cfg: Config):
    earthaccess.login(strategy="netrc")
    c = cfg.section("coryell")
    L = leaks(cfg)
    test = L[(L["time"] >= pd.Timestamp(c["nisar_from"], tz="UTC")) & (L["cause"] != "Construction_Maintenance_Induce")]
    cat = catalogue(cfg)
    m = match(cfg, test, cat)
    stacks, score = choose_stacks(cfg, m)
    if c.get("force_stacks"):  # confirmation run: a stack chosen in advance, not by score
        stacks = list(c["force_stacks"])
    m = m[m["stack"].isin(stacks) & (m["maturity"] != "beta")]
    ctl = controls(cfg, L, test[test["leak_id"].isin(m["leak_id"])])
    # site list per granule: matched leaks + their controls (controls inherit the leak's timing)
    sites_by_granule = {}
    for gid, g in m.groupby("granule_ur"):
        s = [{"site_id": f"leak_{r.leak_id}", "lon": r.geometry.x, "lat": r.geometry.y}
             for r in test[test["leak_id"].isin(g["leak_id"])].itertuples()]
        s += [{"site_id": f"ctl_{r.control_id}", "lon": r.geometry.x, "lat": r.geometry.y}
              for r in ctl[ctl["leak_id"].isin(g["leak_id"])].itertuples()]
        sites_by_granule[gid] = s
    gran = cat[cat["granule_ur"].isin(m["granule_ur"])].copy()
    return L, test, ctl, cat, m, stacks, score, gran, sites_by_granule


def run(cfg: Config, workers: int = 6, dry_run: bool = False) -> None:
    from rich.console import Console
    from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
    from rich.table import Table

    con = Console()
    half = cfg.section("sar")["patch_size_px"] // 2 + cfg.section("sar")["filter_size"]
    L, test, ctl, cat, m, stacks, score, gran, sbg = plan(cfg)
    d = _dir(cfg)
    m.to_parquet(d / "matches.parquet")
    ctl.to_parquet(d / "controls.parquet")
    test.to_parquet(d / "leaks.parquet")
    con.print(f"Coryell: {len(L)} leaks in district, {len(test)} natural/other in NISAR window; catalogue {len(cat)} GCOV granules")
    con.print(score.head(8).to_string())
    con.print(f"chosen stacks: {stacks}")
    cached = {p.stem for p in d.glob("NISAR_*.npz")}
    todo = gran[~gran["granule_ur"].isin(cached)]
    n_chunks = estimate_chunks(cfg, gran, sbg, half) if len(gran) else pd.Series(dtype=int)
    est = n_chunks * (2 * BYTES_PER_FLOAT_CHUNK + 2 * BYTES_PER_MASK_CHUNK)
    t = Table(title="Coryell stream plan (site windows only)", show_header=False)
    t.add_row("test leaks with passes", f"{m['leak_id'].nunique()} (of {len(test)})")
    t.add_row("controls", f"{len(ctl)} on district pipes")
    t.add_row("granules", f"{len(gran)} ({len(gran) - len(todo)} cached, {len(todo)} to stream)")
    t.add_row("remote size (NOT downloaded)", human_size(todo["size_bytes"].sum()))
    t.add_row("chunks per granule (measured grid)", f"median {int(n_chunks.median()) if len(n_chunks) else 0}")
    t.add_row("estimated transfer", f"~{human_size(est[est.index.isin(todo['granule_ur'])].sum())}")
    t.add_row("estimated disk", f"~{human_size(sum(len(v) for k, v in sbg.items() if k in set(todo['granule_ur'])) * (2 * half) ** 2 * 6)}")
    con.print(t)
    if dry_run or todo.empty:
        return

    results, net, per = [], {"b": 0}, {}
    cols = [SpinnerColumn(), TextColumn("[bold]{task.description:<26}"), BarColumn(bar_width=30), TaskProgressColumn(),
            TextColumn("{task.fields[info]}"), TimeElapsedColumn(), TimeRemainingColumn()]
    with Progress(*cols, console=con, refresh_per_second=4) as prog:
        overall = prog.add_task("all granules", total=len(gran), info="")
        prog.advance(overall, len(gran) - len(todo))
        with Manager() as mgr:
            q = mgr.Queue()
            with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as ex:
                pending = {ex.submit(stream_granule, r.drop(labels=["geometry"]).to_dict(), sbg[r["granule_ur"]], half, str(d), q)
                           for _, r in todo.iterrows()}
                while pending:
                    while not q.empty():
                        gid, kind, val = q.get()
                        if gid not in per:
                            tk = gid.split("_")
                            per[gid] = {"stage": "", "b": 0, "task": prog.add_task(
                                f"{tk[5]}{tk[6]} {tk[11][:8]}", total=float(est.get(gid, 100 * 2**20)), info="")}
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
                        prog.update(st["task"], info=f"{st['stage']:<16} {human_size(st['b'])}")
                    for f in [f for f in pending if f.done()]:
                        pending.discard(f)
                        results.append(f.result())
                        prog.advance(overall)
                    time.sleep(0.2)
    res = pd.DataFrame(results)
    ok = res[res["status"] == "ok"]
    con.print(f"streamed {len(ok)}/{len(res)}: {human_size(ok['bytes'].sum())} transferred, {human_size(ok['disk_bytes'].sum())} written")
    for _, e in res[res["status"] == "error"].iterrows():
        con.print(f"[red]FAILED {e['granule_ur']}: {e['error']}")
    con.print(f"[bold]data/sar/coryell on disk: {human_size(sum(p.stat().st_size for p in d.glob('*')))}")


# --------------------------------------------------------------------------- analysis
def _cfg_for_coryell(cfg: Config) -> Config:
    c2 = copy.deepcopy(cfg.raw)
    c2["features"]["weather_lat"] = cfg.section("coryell")["weather_lat"]
    c2["features"]["weather_lon"] = cfg.section("coryell")["weather_lon"]
    c2["sar"]["out_dir"] = str(Path(cfg.section("sar")["out_dir"]) / cfg.section("coryell").get("subdir", "coryell"))
    return Config(c2)


def build_patches(cfg: Config) -> pd.DataFrame:
    import h5py

    from .sar import _speckle

    c = cfg.section("coryell")
    d = _dir(cfg)
    m = pd.read_parquet(d / "matches.parquet")
    ctl = gpd.read_parquet(d / "controls.parquet")
    test = gpd.read_parquet(d / "leaks.parquet")
    pad, size = cfg.section("sar")["filter_size"], cfg.section("sar")["patch_size_px"]
    core = (slice(pad, pad + size), slice(pad, pad + size))
    files = sorted(d.glob("NISAR_*.npz"))
    rows, n = [], 0
    geo = {f"leak_{r.leak_id}": r.geometry for r in test.itertuples()}
    geo |= {f"ctl_{r.control_id}": r.geometry for r in ctl.itertuples()}
    ctl_leak = dict(zip("ctl_" + ctl["control_id"], ctl["leak_id"]))
    total = 0
    for f in files:
        with np.load(f) as zf:
            total += int(zf["ok"].sum())
    with h5py.File(d / "patches.h5", "w") as h5:
        kw = dict(chunks=(1, 2, size, size), compression="gzip", compression_opts=4, shuffle=True)
        d_raw = h5.create_dataset("gamma0", (total, 2, size, size), "float32", fillvalue=np.nan, **kw)
        d_db = h5.create_dataset("db_filtered", (total, 2, size, size), "float32", fillvalue=np.nan, **kw)
        d_valid = h5.create_dataset("valid", (total, size, size), "bool", chunks=(1, size, size), compression="gzip")
        d_looks = h5.create_dataset("numberOfLooks", (total, size, size), "float32", chunks=(1, size, size), compression="gzip")
        for fi, f in enumerate(files):
            with np.load(f) as zf:
                z = {k: zf[k] for k in zf.files}  # decompress each array ONCE (lazy npz access re-reads per call)
            gid = f.stem
            print(f"\r  patches: file {fi + 1}/{len(files)}, {n} patches", end="", flush=True)
            mg = m[m["granule_ur"] == gid].set_index("leak_id")
            for i, sid in enumerate(z["site_id"]):
                if not z["ok"][i]:
                    continue
                leak_id = int(sid.split("_")[1]) if sid.startswith("leak_") else int(ctl_leak[sid])
                if leak_id not in mg.index:
                    continue
                r = mg.loc[leak_id]
                r = r.iloc[0] if isinstance(r, pd.DataFrame) else r
                valid_big = (z["mask"][i] > 0) & (z["mask"][i] < 255) & (z["exc"][i] == 0)
                raw = np.stack([z["hh"][i][core], z["hv"][i][core]])
                dbf = np.full_like(raw, np.nan)
                for b, k in enumerate(("hh", "hv")):
                    lin = z[k][i]
                    clean = np.where(valid_big & np.isfinite(lin) & (lin > 0), lin, np.nan)
                    with np.errstate(divide="ignore", invalid="ignore"):
                        dbf[b] = 10 * np.log10(_speckle(clean, cfg.section("sar")["speckle_filter"], pad, c["enl"])[core])
                valid = valid_big[core] & np.isfinite(raw[0]) & (raw[0] > 0)
                d_raw[n], d_db[n], d_valid[n], d_looks[n] = raw, dbf, valid, np.full((size, size), c["enl"], "float32")
                rows.append({"patch_index": n, "site_id": sid, "site_type": "incident" if sid.startswith("leak_") else "control",
                             "incident_id": leak_id, "granule_ur": gid, "pass_id": f"{r['track_dir']}_{r['start_time']:%Y%m%d}",
                             "comparison_group": f"{r['stack']}_A40MHz_HH+HV", "acquisition_time": r["start_time"],
                             "crid": r["crid"], "maturity": r["maturity"], "delta_days": r["delta_days"],
                             "abs_delta_days": abs(r["delta_days"]), "temporal_category": r["temporal_category"],
                             "match_confidence": "high", "valid_frac": float(valid.mean()),
                             "exception_frac": float((z["exc"][i][core] > 0).mean()),
                             "outside_coverage_frac": float((z["mask"][i][core] == 255).mean()),
                             "match_id": f"{sid}_{gid}", "geometry": geo[sid]})
                n += 1
    print()
    idx = gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84)
    idx.to_parquet(d / "sar_patches.parquet")
    return idx


def analyse(cfg: Config) -> None:
    from scipy.stats import wilcoxon

    from . import features
    from .signal_check import _auc, _bh

    d = _dir(cfg)
    print("Coryell analysis")
    idx = build_patches(cfg)
    print(f"  patches: {len(idx)} ({(idx['site_type'] == 'incident').sum()} leak, {(idx['site_type'] == 'control').sum()} control)"
          f" -> {report_file(d / 'patches.h5')}")
    test = gpd.read_parquet(d / "leaks.parquet")
    ctl = gpd.read_parquet(d / "controls.parquet")
    infra = pd.concat([pd.DataFrame({"site_id": "ctl_" + ctl["control_id"], "inf_pipe_material": ctl["material"],
                                     "inf_pipe_diameter_in": pd.to_numeric(ctl["diameter_in"], errors="coerce")}),
                       pd.DataFrame({"site_id": "leak_" + test["leak_id"].astype(str), "inf_pipe_material": None,
                                     "inf_pipe_diameter_in": np.nan})])
    feat = features.build(_cfg_for_coryell(cfg), "sar_patches.parquet", "patches.h5", infra=infra)
    feat = feat.merge(test[["leak_id", "gpm"]].rename(columns={"leak_id": "incident_id"}), on="incident_id", how="left")
    feat.to_parquet(d / "coryell_features.parquet")
    print(f"  features: {len(feat)} rows ({int(feat['q_usable'].sum())} usable) -> {report_file(d / 'coryell_features.parquet')}")

    u = feat[feat["q_usable"]].copy()
    u["cat"] = u["temporal_category"].astype(str)
    rng = np.random.default_rng(0)
    strata = {"all leaks": u["gpm"].notna() | True, "gpm >= 20": u["gpm"] >= 20, "gpm >= 50": u["gpm"] >= 50,
              "gpm >= 100": u["gpm"] >= 100}
    rows = []
    for sname, sel in strata.items():
        v0 = u[sel]
        for window in ("potential_event_window", "post_event", "pre_event"):
            w = v0[v0["cat"] == window]
            for feat_name in ("chg_ref_hh_contrast", "chg_ref_hv_contrast", "chg_prev_hh_contrast", "sd_hh_contrast", "sd_hv_contrast"):
                for kind, sign in (("|x|", None), ("+x (brighter)", 1), ("-x (darker)", -1)):
                    v = w[["incident_id", "site_type", feat_name]].dropna()
                    if v.empty:
                        continue
                    sc = v[feat_name].abs() if sign is None else sign * v[feat_name]
                    pos, neg = sc[v["site_type"] == "incident"].to_numpy(), sc[v["site_type"] == "control"].to_numpy()
                    ids = v["incident_id"].unique()
                    g = {i: (sc[(v["incident_id"] == i) & (v["site_type"] == "incident")].to_numpy(),
                             sc[(v["incident_id"] == i) & (v["site_type"] == "control")].to_numpy()) for i in ids}
                    boots = []
                    for _ in range(500):
                        pick = rng.choice(ids, len(ids))
                        boots.append(_auc(np.concatenate([g[i][0] for i in pick]), np.concatenate([g[i][1] for i in pick])))
                    lo, hi = np.nanpercentile(boots, [2.5, 97.5]) if len(ids) > 5 else (np.nan, np.nan)
                    rows.append({"stratum": sname, "window": window, "score": f"{kind} {feat_name}", "n_leaks": len(ids),
                                 "n_site_rows": len(pos), "n_control_rows": len(neg), "auc": _auc(pos, neg),
                                 "ci95_lo": lo, "ci95_hi": hi})
    auc = pd.DataFrame(rows)
    # paired DiD per leak x stack: (site - control mean) change, event vs pre
    did = []
    for sname, sel in strata.items():
        v = u[sel]
        for feat_name in ("chg_ref_hh_contrast", "chg_ref_hv_contrast"):
            site = v[v["site_type"] == "incident"].set_index(["incident_id", "pass_id"])[feat_name]
            cm = v[v["site_type"] == "control"].groupby(["incident_id", "pass_id"])[feat_name].mean()
            dd = (site - cm).dropna().rename("did").reset_index().merge(
                v[["incident_id", "pass_id", "cat", "comparison_group"]].drop_duplicates(["incident_id", "pass_id"]))
            per = dd.groupby(["incident_id", "comparison_group", "cat"])["did"].mean().unstack("cat")
            for test_w in ("potential_event_window", "post_event"):
                if "pre_event" not in per or test_w not in per:
                    continue
                pair = per[["pre_event", test_w]].dropna()
                if len(pair) < 6:
                    continue
                diff = pair[test_w] - pair["pre_event"]
                did.append({"stratum": sname, "feature": feat_name, "comparison": f"{test_w} vs pre", "n": len(pair),
                            "median_diff_db": float(diff.median()), "p": wilcoxon(diff).pvalue})
    did = pd.DataFrame(did)
    did["q_bh"] = _bh(did["p"]) if len(did) else []
    auc["q_note"] = ""
    rep = cfg.path("reports_dir") / f"{cfg.section('coryell').get('subdir', 'coryell')}_signal.md"
    best = auc.sort_values("auc", ascending=False).head(10)
    rep.write_text("\n".join([
        "# Coryell (Texas) rural leak visibility with calibrated NISAR GCOV\n",
        f"Leaks: Coryell City WSD repair records in the NISAR window (natural/other causes), stacks {sorted(u['comparison_group'].unique())}. "
        f"Controls: {cfg.section('coryell')['controls_per_leak']} per leak on district pipes, "
        f"{cfg.section('coryell')['control_min_m']}-{cfg.section('coryell')['control_max_m']} m away, no other leak within "
        f"{cfg.section('coryell')['exclusion_m']} m / +-{cfg.section('coryell')['exclusion_days']} d. Same passes; same features as Kitchener.\n",
        "## Site vs control AUC (0.5 = chance; CI = bootstrap over leaks)", auc.drop(columns="q_note").round(3).to_markdown(index=False), "",
        "## Highest AUCs (beware multiple comparisons)", best.drop(columns="q_note").round(3).to_markdown(index=False), "",
        "## Difference-in-differences (site - control mean), event/post vs pre, paired per leak x stack",
        did.round(3).to_markdown(index=False) if len(did) else "(not enough pairs)", ""]) + "\n")
    with pd.option_context("display.width", 220, "display.max_rows", 400):
        ev = auc[(auc["window"] == "potential_event_window")].round(3)
        print(ev.drop(columns="q_note").to_string(index=False))
        print()
        print(did.round(3).to_string(index=False))
    print(f"  report -> {report_file(rep)}")


# --------------------------------------------------------------------------- confirmation (pre-registered)
def confirm_config(cfg: Config) -> Config:
    c2 = copy.deepcopy(cfg.raw)
    c2["coryell"]["subdir"] = "coryell_confirm"
    c2["coryell"]["force_stacks"] = ["163A_017"]
    return Config(c2)


def per_site_drop(u: pd.DataFrame, feat: str, sites: str) -> pd.DataFrame:
    """Pre-registered metric (docs/CORYELL_CONFIRMATION_PREREG.md): per site, mean over passes of
    (site value - mean of the same leak's controls on that pass, excluding itself) in the leaking window
    [-60, +14] d minus the same in the after window [+30, +120] d."""
    ctl = u[u["site_type"] == "control"]
    ref = ctl.groupby(["incident_id", "pass_id"])[feat].agg(["sum", "count"])
    s = u[u["site_type"] == sites].join(ref, on=["incident_id", "pass_id"])
    own = s["site_type"] == "control"
    s["ref"] = np.where(own, (s["sum"] - s[feat]) / (s["count"] - 1), s["sum"] / s["count"])
    s["did"] = s[feat] - s["ref"]
    s["phase"] = np.select([s["delta_days"].between(-60, 14), s["delta_days"].between(30, 120)], ["leaking", "after"], "other")
    per = s[s["phase"] != "other"].groupby(["site_id", "phase"]).agg(did=("did", "mean"), gpm=("gpm", "first"),
                                                                     incident_id=("incident_id", "first")).unstack("phase")
    out = pd.DataFrame({"incident_id": per[("incident_id", "leaking")], "gpm": per[("gpm", "leaking")],
                        "drop": per[("did", "leaking")] - per[("did", "after")]}).dropna(subset=["drop"])
    return out


def confirm_test(cfg: Config) -> None:
    from scipy.stats import wilcoxon

    ccfg = confirm_config(cfg)
    d = _dir(ccfg)
    f = pd.read_parquet(d / "coryell_features.parquet")
    u = f[f["q_usable"]]
    disc_used = set(pd.read_parquet(ROOT / cfg.section("sar")["out_dir"] / "coryell" / "coryell_features.parquet",
                                    columns=["incident_id"])["incident_id"]) if (ROOT / cfg.section("sar")["out_dir"] / "coryell" / "coryell_features.parquet").exists() else set()
    rng = np.random.default_rng(7)
    rows = []

    def summarise(name, x, alternative):
        boot = [np.mean(rng.choice(x, len(x))) for _ in range(5000)] if len(x) else [np.nan]
        p = wilcoxon(x, alternative=alternative).pvalue if len(x) >= 6 else np.nan
        rows.append({"test": name, "n": len(x), "mean_drop_db": float(np.mean(x)) if len(x) else np.nan,
                     "ci95": f"[{np.percentile(boot, 2.5):+.2f}, {np.percentile(boot, 97.5):+.2f}]",
                     "share_dropped": f"{np.mean(np.asarray(x) > 0):.0%}" if len(x) else "", "p": p})

    leak = per_site_drop(u, "sd_hh_contrast", "incident")
    ctl = per_site_drop(u, "sd_hh_contrast", "control")
    summarise("PRIMARY: HH leak sites (one-sided, drop > 0)", leak["drop"].to_numpy(), "greater")
    summarise("PLACEBO: HH controls vs other controls (two-sided)", ctl["drop"].to_numpy(), "two-sided")
    summarise("secondary: HV leak sites (one-sided)", per_site_drop(u, "sd_hv_contrast", "incident")["drop"].to_numpy(), "greater")
    summarise("secondary: HH leaks >= 50 gpm (one-sided)", leak.loc[leak["gpm"] >= 50, "drop"].to_numpy(), "greater")
    summarise("secondary: HH leaks NOT in discovery set (one-sided)",
              leak.loc[~leak["incident_id"].isin(disc_used), "drop"].to_numpy(), "greater")
    res = pd.DataFrame(rows)
    prim, plac = res.iloc[0], res.iloc[1]
    passed = (prim["p"] < 0.05) and (prim["mean_drop_db"] > 0) and (plac["p"] >= 0.05)
    verdict = ("CONFIRMED: the pre-registered effect replicates on the held-out stack 163A_017." if passed else
               "NOT CONFIRMED: the pre-registered criterion was not met on the held-out stack 163A_017.")
    rep = cfg.path("reports_dir") / "coryell_confirmation.md"
    rep.write_text("\n".join([
        "# Coryell confirmation test (pre-registered)\n",
        "Rules: `docs/CORYELL_CONFIRMATION_PREREG.md` (written before the 163A_017 data was downloaded).\n",
        res.round(4).to_markdown(index=False), "", f"**{verdict}**", ""]) + "\n")
    with pd.option_context("display.width", 200):
        print(res.round(4).to_string(index=False))
    print(f"\n  {verdict}\n  report -> {report_file(rep)}")
