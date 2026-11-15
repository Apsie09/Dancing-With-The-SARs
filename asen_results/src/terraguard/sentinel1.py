"""Sentinel-1 (C-band, VV/VH) on Peter's Coryell samples: NISAR vs Sentinel-1 on identical leaks.

For every positive in ../pesho_coryell_data_package, pick the Sentinel-1 RTC orbit (107 or 34, both ascending)
whose last pass at or before the repair is closest (<= 12 days): that pass is t0; t-2, t-1, t+1 are the
neighbouring passes of the same orbit. The positive's 10 negatives use exactly the same passes.
20 x 20 px (10 m) windows are read from the Planetary Computer COGs (EPSG:32614, same grid family as the chips);
nothing else is downloaded.

  pixi run s1 --dry-run     # plan + transfer estimate (measured tile size)
  pixi run s1 --workers 8   # read windows -> data/sar/s1_pesho/chips.npz
  pixi run s1 --analyse     # features + boosting, same variants/metrics as `pesho-model`
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import numpy as np
import pandas as pd

from .config import ROOT, Config, human_size, report_file
from .pesho_model import PKG, _metrics, context_features

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
ROLES = ["t-2", "t-1", "t0", "t+1"]
TILE = 512


def _dir(cfg: Config):
    d = ROOT / cfg.section("sar")["out_dir"] / "s1_pesho"
    d.mkdir(parents=True, exist_ok=True)
    return d


def items(cfg: Config, start: str, end: str) -> pd.DataFrame:
    import planetary_computer as pc
    import pystac_client

    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
    res = cat.search(collections=["sentinel-1-rtc"], bbox=cfg.section("coryell")["district_bbox"], datetime=f"{start}/{end}")
    rows = [{"item_id": it.id, "time": pd.Timestamp(it.properties["datetime"]), "orbit": it.properties.get("sat:relative_orbit"),
             "platform": it.id[:3]} for it in res.items()]
    df = pd.DataFrame(rows).sort_values("time")
    df["date"] = df["time"].dt.strftime("%Y-%m-%d")
    return df.drop_duplicates(["orbit", "date"]).reset_index(drop=True)


def assign_passes(samples: pd.DataFrame, it: pd.DataFrame) -> pd.DataFrame:
    """Per positive: best orbit and its t-2..t+1 passes; negatives inherit their positive's passes."""
    pos = samples[samples["label"] == 1]
    rows = []
    for r in pos.itertuples():
        rep = pd.Timestamp(r.repair_utc)
        best = None
        for orb, g in it.groupby("orbit"):
            g = g.reset_index(drop=True)
            k = g.index[g["time"] <= rep]
            if not len(k):
                continue
            k = k[-1]
            gap = (rep - g.loc[k, "time"]).total_seconds() / 86400
            if gap <= 12 and (best is None or gap < best[0]):
                best = (gap, orb, g, k)
        if best is None:
            continue
        gap, orb, g, k = best
        ids = {role: (g.loc[k + o, "item_id"] if 0 <= k + o < len(g) else None) for role, o in zip(ROLES, (-2, -1, 0, 1))}
        rows.append({"positive_id": r.sample_id, "s1_orbit": orb, "s1_gap_days": gap, **{f"s1_{x}": ids[x] for x in ROLES}})
    pa = pd.DataFrame(rows)
    return samples.merge(pa, on="positive_id", how="inner")


def plan(cfg: Config):
    samples = pd.concat([pd.read_csv(PKG / s / "index.csv").assign(split=s) for s in ("train", "test")], ignore_index=True)
    pos_time = samples[samples["label"] == 1].set_index("sample_id")["repair_utc"]
    samples["repair_utc"] = samples["positive_id"].map(pos_time)
    t0 = pd.to_datetime(samples["repair_utc"], utc=True)
    it = items(cfg, f"{(t0.min() - pd.Timedelta(days=40)):%Y-%m-%d}", f"{(t0.max() + pd.Timedelta(days=20)):%Y-%m-%d}")
    s = assign_passes(samples, it)
    # windows per item
    jobs = {}
    for role in ROLES:
        for iid, g in s.groupby(f"s1_{role}"):
            jobs.setdefault(iid, []).extend((r.sample_id, role, r.utm_x, r.utm_y) for r in g.itertuples())
    return samples, it, s, jobs


def read_item(item_id: str, windows: list) -> tuple[str, dict, int]:
    """Read 20x20 VV/VH windows around each point from one Sentinel-1 RTC item."""
    import planetary_computer as pc
    import pystac_client
    import rasterio
    from rasterio.windows import Window

    for attempt in range(3):
        try:
            cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
            item = cat.get_collection("sentinel-1-rtc").get_item(item_id)
            out, tiles = {}, set()
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", VSI_CACHE="TRUE", GDAL_HTTP_MAX_RETRY="3",
                              GDAL_HTTP_TIMEOUT="60", GDAL_CACHEMAX=512):
                srcs = {p: rasterio.open(item.assets[p].href) for p in ("vv", "vh")}
                ds = srcs["vv"]
                if ds.crs.to_epsg() != 32614:
                    raise RuntimeError(f"unexpected CRS {ds.crs}")
                for sid, role, x, y in sorted(windows, key=lambda w: (w[3], w[2])):
                    r, c = ds.index(x, y)
                    w = Window(c - 10, r - 10, 20, 20)
                    if r - 10 < 0 or c - 10 < 0 or r + 10 > ds.height or c + 10 > ds.width:
                        continue
                    out[(sid, role)] = np.stack([srcs[p].read(1, window=w) for p in ("vv", "vh")]).astype("float32")
                    for rr in {(r - 10) // TILE, (r + 9) // TILE}:
                        for cc in {(c - 10) // TILE, (c + 9) // TILE}:
                            tiles.add((rr, cc))
                for v in srcs.values():
                    v.close()
            return item_id, out, len(tiles)
        except Exception:  # noqa: BLE001 - token expiry / transient HTTP: retry with a fresh signature
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def run(cfg: Config, workers: int = 8, dry_run: bool = False) -> None:
    import requests
    from rich.console import Console
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

    con = Console()
    samples, it, s, jobs = plan(cfg)
    d = _dir(cfg)
    s.to_parquet(d / "samples.parquet")
    pos = s[s["label"] == 1]
    con.print(f"Sentinel-1 RTC over Coryell: {len(it)} passes ({it['date'].min()} -> {it['date'].max()}), orbits {sorted(it['orbit'].unique())}")
    con.print(f"samples with S1 passes: {len(s)} of {len(samples)} ({len(pos)} of {int((samples['label'] == 1).sum())} positives); "
              f"median t0->repair gap {pos['s1_gap_days'].median():.1f} d; orbit use {pos['s1_orbit'].value_counts().to_dict()}")
    # measured average compressed tile size from one item
    import planetary_computer as pc
    import pystac_client
    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
    one = cat.get_collection("sentinel-1-rtc").get_item(next(iter(jobs)))
    size = int(requests.head(one.assets["vv"].href, timeout=60).headers.get("Content-Length", 0))
    import rasterio
    with rasterio.open(one.assets["vv"].href) as ds:
        n_tiles = -(-ds.width // TILE) * -(-ds.height // TILE)
    per_tile = size / n_tiles
    est_tiles = sum(min(len(w), 60) for w in jobs.values())  # upper-ish bound: one tile per window, capped per item
    con.print(f"items to read: {len(jobs)} | windows: {sum(len(w) for w in jobs.values())} | "
              f"measured tile ~{human_size(per_tile)} | estimated transfer ~{human_size(est_tiles * 2 * per_tile)} (VV+VH)")
    if dry_run:
        return
    cache = d / "chips.npz"
    chips, done_tiles = {}, 0
    with Progress(TextColumn("[bold]{task.description}"), BarColumn(), MofNCompleteColumn(), TextColumn("{task.fields[info]}"),
                  TimeElapsedColumn(), TimeRemainingColumn(), console=con) as prog:
        task = prog.add_task("S1 items", total=len(jobs), info="")
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(read_item, k, v): k for k, v in jobs.items()}
            for f in as_completed(futs):
                try:
                    iid, out, nt = f.result()
                    chips.update(out)
                    done_tiles += nt
                except Exception as e:  # noqa: BLE001
                    con.print(f"[red]FAILED {futs[f]}: {e}")
                prog.update(task, advance=1, info=f"~{human_size(done_tiles * 2 * per_tile)} transferred (est.)")
    keys = sorted(chips)
    np.savez_compressed(cache, sample_id=np.array([k[0] for k in keys]), role=np.array([k[1] for k in keys]),
                        chips=np.stack([chips[k] for k in keys]))
    con.print(f"windows read: {len(keys)} -> {report_file(cache)}  (est. transfer {human_size(done_tiles * 2 * per_tile)})")


def s1_features(cfg: Config) -> pd.DataFrame:
    d = _dir(cfg)
    s = pd.read_parquet(d / "samples.parquet")
    z = np.load(d / "chips.npz")
    yy, xx = np.mgrid[:20, :20]
    dist = np.hypot(yy - 9.5, xx - 9.5)
    centre, ring = dist <= 1.6, dist >= 5
    lin = z["chips"]                                          # (n, 2, 20, 20)
    with np.errstate(divide="ignore", invalid="ignore"):
        db = np.where(np.isfinite(lin) & (lin > 0), 10 * np.log10(lin), np.nan)
    keys = pd.DataFrame({"sample_id": z["sample_id"], "role": z["role"]})
    # pass-level normalisation: median/std over all chips of the same item (proxy for the district statistic)
    keys["item"] = [s.set_index("sample_id").at[sid, f"s1_{role}"] for sid, role in zip(keys["sample_id"], keys["role"])]
    feats = []
    for i, (sid, role, item) in enumerate(keys.itertuples(index=False)):
        f = {"sample_id": sid, "role": role, "item": item}
        for b, pol in enumerate(("vv", "vh")):
            a = db[i, b]
            f[f"{pol}"] = np.nanmean(a[centre])
            f[f"{pol}_ring"] = f[pol] - np.nanmean(a[ring])
            f[f"{pol}_tex"] = np.nanstd(a)
        f["vhvv"] = f["vh"] - f["vv"]
        feats.append(f)
    F = pd.DataFrame(feats)
    for pol in ("vv", "vh"):
        g = F.groupby("item")[pol]
        F[f"{pol}_pass_z"] = (F[pol] - g.transform("median")) / g.transform("std")
    wide = {}
    for role in ROLES:
        t = role.replace("-", "m").replace("+", "p")
        sub = F[F["role"] == role].set_index("sample_id").drop(columns=["role", "item"])
        wide[t] = sub.add_prefix(f"s1_{t}_")
    W = pd.concat(wide.values(), axis=1).reset_index()
    for a, b in (("t0", "tm1"), ("t0", "tm2"), ("tp1", "t0")):
        for v in ("vv", "vh", "vv_ring", "vh_ring"):
            ca, cb = f"s1_{a}_{v}", f"s1_{b}_{v}"
            if ca in W and cb in W:
                W[f"s1chg_{a}_{b}_{v}"] = W[ca] - W[cb]
    return s[["sample_id", "label", "group_id", "split"]].merge(W, on="sample_id", how="left")


def analyse(cfg: Config) -> None:
    from sklearn.ensemble import HistGradientBoostingClassifier

    print("Sentinel-1 vs NISAR on Peter's Coryell samples")
    rng = np.random.default_rng(42)
    S1 = s1_features(cfg)
    nis = pd.read_parquet(cfg.path("processed_dir") / "pesho_enriched.parquet")
    df = S1.merge(nis.drop(columns=["label", "group_id"]), on=["sample_id", "split"], how="inner")
    for c in ("ctx_pipe_material", "ctx_zone"):
        df[c] = df[c].astype("category")
    tr, te = df[df["split"] == "train"], df[df["split"] == "test"]
    s1_pre = [c for c in df.columns if (c.startswith("s1_t") or c.startswith("s1chg_")) and "tp1" not in c]
    s1_post = [c for c in df.columns if (c.startswith("s1_t") or c.startswith("s1chg_")) and "tp1" in c]
    nisar_pre = [c for c in df.columns if (c.startswith("sar_t") or c.startswith("chg_")) and "tp1" not in c]
    ctx = [c for c in df.columns if c.startswith("ctx_")]
    variants = {
        "NISAR L-band only (t-2..t0)": nisar_pre,
        "Sentinel-1 C-band only (t-2..t0)": s1_pre,
        "NISAR + Sentinel-1": nisar_pre + s1_pre,
        "context only (pipe + leak history)": ctx,
        "Sentinel-1 + context": s1_pre + ctx,
        "diagnostic: Sentinel-1 incl. t+1 (after repair)": s1_pre + s1_post,
    }
    rows = []
    for name, cols in variants.items():
        m = HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, max_depth=3, min_samples_leaf=40,
                                           l2_regularization=1.0, categorical_features="from_dtype", random_state=42)
        m.fit(tr[cols], tr["label"])
        p = m.predict_proba(te[cols])[:, 1]
        rows.append({"model": name, "n_features": len(cols), **_metrics(te["label"], p, te["group_id"].to_numpy(), rng)})
        print(f"  {name}: AUC {rows[-1]['auc']:.3f} {rows[-1]['auc_ci95']}, matched {rows[-1]['matched_auc']:.3f}, AP {rows[-1]['avg_precision']:.3f}")
    res = pd.DataFrame(rows)
    rep = cfg.path("reports_dir") / "s1_vs_nisar_coryell.md"
    rep.write_text("\n".join([
        f"# Sentinel-1 vs NISAR on Peter's Coryell samples\n\n_Generated {date.today()} by `pixi run s1 --analyse`._\n",
        f"Identical samples and split (train {len(tr)}, test {len(te)}, {int(te['label'].sum())} test leaks). "
        "Sentinel-1 RTC (Planetary Computer, VV/VH, 10 m), orbit per leak = closest pass <= 12 d before repair.\n",
        res.round(3).to_markdown(index=False), ""]) + "\n")
    print(f"  report -> {report_file(rep)}")
