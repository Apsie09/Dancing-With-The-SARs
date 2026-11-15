"""Build the data bundle for the interactive map (app/index.html).

Reads the existing pipeline outputs only (no network):
  processed/risk_panel_eval.parquet   baseline break-risk scores, Dec 2025 - Oct 2026 hold-out
  processed/kitchener_water_mains     pipe geometry + attributes
  processed/seg_gcov.parquet          NISAR HH/HV per segment and pass
  processed/radar_features / control_features   break sites vs matched controls
  sar/crops/*.tif                     calibrated GCOV city crops (10 m, UTM 17N)

Writes app/data.js (window.TG) and app/img/<pass>_{rgb,chg}.webp, warped to Web Mercator.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import shapely
from PIL import Image
from pyproj import Transformer
from rasterio.warp import Resampling, calculate_default_transform, reproject
from scipy.ndimage import uniform_filter
from sklearn.metrics import roc_auc_score

from .config import Config

ROOT = Path(__file__).resolve().parents[2]
PROC, SAR, OUT = ROOT / "data" / "processed", ROOT / "data" / "sar", ROOT / "app"
NISAR_ERA = "2025-10-28"
MERC_RES = 50.0  # EPSG:3857 units, about 36 m on the ground at 43.4 N


def _b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


def _clean(o):
    """NaN -> null, so the bundle is strict JSON."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def _db(x):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(x)


def _scale(x, lo, hi):
    return np.nan_to_num(np.clip((x - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)


def _mains() -> tuple[pd.DataFrame, list]:
    m = pd.read_parquet(PROC / "kitchener_water_mains.parquet").sort_values("main_id").reset_index(drop=True)
    assert m.main_id.is_unique
    lines = []
    for g in shapely.from_wkb(m.geometry.values):
        parts = getattr(g, "geoms", [g])
        lines.append([[[round(x, 5), round(y, 5)] for x, y in p.coords] for p in parts])
    return m, lines


def _risk(ids: np.ndarray) -> dict:
    ev = pd.read_parquet(PROC / "risk_panel_eval.parquet")
    months = sorted(ev.month.unique())
    # Rank over every segment-month of the hold-out, the same pool the reported top-5% capture uses.
    ev["pct"] = np.ceil(ev.m0_score.rank(ascending=False, method="first") / len(ev) * 100).clip(1, 100)
    pct = ev.pivot(index="main_id", columns="month", values="pct").reindex(index=ids, columns=months)
    y = ev.pivot(index="main_id", columns="month", values="y").reindex(index=ids, columns=months).fillna(0)
    last = ev.sort_values("month").groupby("main_id").last().reindex(ids)
    capture = {str(k): float(ev.y[ev.pct <= k].sum() / ev.y.sum()) for k in (1, 5, 10, 20)}
    per_month = [{"month": mo, "breaks": int(g.y.sum()), "in_top5": int(g.y[g.pct <= 5].sum())}
                 for mo, g in ev.groupby("month")]
    weather = ev.groupby("month")[["w_fdd", "w_tmin", "w_freeze_thaw_days"]].first().round(1)
    return {
        "months": months,
        "pct": _b64(pct.fillna(100).to_numpy(np.uint8)),
        "broke": _b64(y.to_numpy(np.uint8)),
        "prior": last.prior_breaks_seg.fillna(0).astype(int).tolist(),
        "b5y": last.breaks_seg_5y.fillna(0).astype(int).tolist(),
        "nbr2y": last.nbr_breaks_2y.fillna(0).astype(int).tolist(),
        "auc": float(roc_auc_score(ev.y, ev.m0_score)),
        "rows": int(len(ev)), "positives": int(ev.y.sum()),
        "capture": capture, "per_month": per_month,
        "weather": {mo: r.tolist() for mo, r in weather.iterrows()},
    }


def _passes(ids: np.ndarray) -> tuple[list, dict]:
    g = pd.read_parquet(PROC / "seg_gcov.parquet")
    p = (g[["granule_ur", "time", "comparison_group"]].drop_duplicates("granule_ur")
         .sort_values("time").reset_index(drop=True))
    col = {u: i for i, u in enumerate(p.granule_ur)}
    row = {int(m): i for i, m in enumerate(ids)}
    r, c = g.main_id.map(row).to_numpy(), g.granule_ur.map(col).to_numpy()
    mats = {}
    for k in ("hh_db", "hv_db"):
        a = np.full((len(ids), len(p)), -32768, np.int16)
        v = g[k].to_numpy()
        ok = np.isfinite(v)
        a[r[ok], c[ok]] = np.round(v[ok] * 100).astype(np.int16)
        mats[k] = _b64(a)
    city = g.groupby("granule_ur")[["hh_db", "hv_db"]].median().reindex(p.granule_ur).round(2)
    seg_cov = (g.dropna(subset=["hh_db"]).groupby("granule_ur").main_id.nunique().reindex(p.granule_ur) / len(ids)).fillna(0)
    passes = [{"id": u, "t": t.strftime("%Y-%m-%dT%H:%MZ"), "track": grp[:4], "frame": u.split("_")[7],
               "seg_cov": round(float(seg_cov.iloc[i]), 3),
               "city_hh": float(city.hh_db.iloc[i]), "city_hv": float(city.hv_db.iloc[i])}
              for i, (u, t, grp) in enumerate(zip(p.granule_ur, p.time, p.comparison_group))]
    return passes, {"hh": mats["hh_db"], "hv": mats["hv_db"]}


def _images(passes: list) -> list:
    """Warp each crop to Web Mercator; write an HH/HV composite and a change-vs-track-median image."""
    img = OUT / "img"
    img.mkdir(parents=True, exist_ok=True)
    grid, stack = None, {}
    for i, p in enumerate(passes):
        tif = SAR / "crops" / f"{p['id']}.tif"
        if not tif.exists():
            p["img"] = False
            continue
        with rasterio.open(tif) as s, rasterio.open(SAR / "crops" / f"{p['id']}_mask.tif") as ms:
            if grid is None:
                tr, w, h = calculate_default_transform(s.crs, "EPSG:3857", s.width, s.height, *s.bounds,
                                                       resolution=MERC_RES)
                grid = (tr, w, h)
            tr, w, h = grid
            hh, hv = s.read(1), s.read(2)
            mask = ms.read(1)
            exc = ms.read(2) if ms.count > 1 else np.zeros_like(mask)
            bad = ~((mask > 0) & (mask < 255))
            hh[bad], hv[bad] = np.nan, np.nan
            out = np.full((3, h, w), np.nan, np.float32)
            for b, src, rs in ((0, hh, Resampling.average), (1, hv, Resampling.average),
                               (2, (exc > 0).astype(np.float32), Resampling.average)):
                reproject(src, out[b], src_transform=s.transform, src_crs=s.crs, dst_transform=tr,
                          dst_crs="EPSG:3857", src_nodata=np.nan, dst_nodata=np.nan, resampling=rs)
        hh_db, hv_db = _db(out[0]), _db(out[1])
        p["img"], p["exc_frac"] = True, float(np.nanmean(out[2] > 0.5))
        p["cov"] = round(float(np.isfinite(hh_db).mean()), 3)
        rgba = np.dstack([_scale(hh_db, -18, 3), _scale(hv_db, -27, -5), _scale(hh_db - hv_db, 2, 14),
                          np.where(np.isfinite(hh_db), 255, 0).astype(np.uint8)])
        Image.fromarray(rgba, "RGBA").save(img / f"p{i}_rgb.webp", quality=82, method=4)
        # Change uses a 3x3 average in power first, to tame speckle; exception pixels are left out.
        sm = _db(uniform_filter(np.nan_to_num(out[0]), 3) / np.maximum(uniform_filter(np.isfinite(out[0]).astype("f4"), 3), 1e-6))
        sm[~np.isfinite(hh_db) | (out[2] > 0.5)] = np.nan
        stack.setdefault(p["track"], []).append((i, sm))
    for track, items in stack.items():
        med = np.nanmedian(np.stack([a for _, a in items]), axis=0)
        for i, a in items:
            d = a - med
            t = np.nan_to_num(np.clip(d / 3.0, -1, 1))
            # diverging: blue = darker than the track's median, red = brighter, transparent at no change
            rgb = np.where(t[..., None] < 0, np.array([57, 135, 229]), np.array([230, 103, 103]))
            alpha = np.where(np.isfinite(d), np.clip((np.abs(t) - 0.2) / 0.8, 0, 1) * 235, 0)
            Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8), "RGBA").save(
                img / f"p{i}_chg.webp", quality=82, method=4)
    tr, w, h = grid
    to_ll = Transformer.from_crs(3857, 4326, always_xy=True)
    west, north = to_ll.transform(tr.c, tr.f)
    east, south = to_ll.transform(tr.c + tr.a * w, tr.f + tr.e * h)
    return [[south, west], [north, east]]


def _breaks_and_evidence() -> list:
    inc = pd.read_parquet(PROC / "kitchener_incidents.parquet")
    inc = inc[(inc.incident_date >= NISAR_ERA) & ~inc.is_cancelled]
    rf = pd.read_parquet(PROC / "radar_features.parquet")
    cf = pd.read_parquet(PROC / "control_features.parquet")
    rf, cf = rf[rf.q_usable.astype(bool)], cf[cf.q_usable.astype(bool)]
    # Each site is shown as its deviation from its own median on that track, so a site that is
    # permanently bright (a building next to it) is not mistaken for a change.
    key = ["incident_id", "comparison_group"]
    rf = rf.dropna(subset=["sd_hh_contrast"]).copy()
    cf = cf.dropna(subset=["sd_hh_contrast"]).copy()
    rf["dev"] = rf.sd_hh_contrast - rf.groupby(key).sd_hh_contrast.transform("median")
    cf["dev"] = cf.sd_hh_contrast - cf.groupby(key + ["control_id"]).sd_hh_contrast.transform("median")
    ctl = cf.groupby(["incident_id", "granule_ur"]).dev.agg(["median", "min", "max"]).reset_index()
    ev = rf[["incident_id", "granule_ur", "comparison_group", "delta_days", "dev"]].merge(
        ctl, on=["incident_id", "granule_ur"], how="left")
    out = []
    for r in inc.itertuples():
        e = ev[ev.incident_id == r.incident_id].sort_values("delta_days")
        series = {}
        for grp, g in e.groupby("comparison_group"):
            series[grp[:4]] = {"d": g.delta_days.round(1).tolist(), "site": g.dev.round(2).tolist(),
                               "med": g["median"].round(2).tolist(), "lo": g["min"].round(2).tolist(),
                               "hi": g["max"].round(2).tolist()}
        s = lambda v: None if pd.isna(v) else v  # noqa: E731
        out.append({"id": int(r.incident_id), "lon": round(r.lon, 6), "lat": round(r.lat, 6),
                    "date": r.incident_date_local.strftime("%Y-%m-%d"), "type": s(r.break_type),
                    "nature": s(r.break_nature), "street": s(r.street),
                    "main": None if pd.isna(r.asset_id) else int(r.asset_id),
                    "material": s(r.asset_material), "size": s(r.asset_size_mm),
                    "year": None if pd.isna(r.asset_year_installed) else int(r.asset_year_installed),
                    "ev": series})
    return out


def _temperature() -> dict:
    w = pd.read_parquet(ROOT / "data" / "raw" / "open_meteo_daily_kitchener.parquet")
    if not isinstance(w.index, pd.DatetimeIndex):
        w.index = pd.to_datetime(w[[c for c in w.columns if "date" in c or c == "time"][0]])
    w = w.loc["2025-12-01":"2026-10-31", "temperature_2m_mean"]
    return {"t": [d.strftime("%Y-%m-%d") for d in w.index], "c": w.round(1).tolist()}


def run(cfg: Config) -> None:
    OUT.mkdir(exist_ok=True)
    m, lines = _mains()
    ids = m.main_id.to_numpy()
    passes, series = _passes(ids)
    bounds = _images(passes)
    data = {
        "mains": {"id": ids.tolist(), "lines": lines, "material": m.material.fillna("?").tolist(),
                  "size": m.pipe_size_mm.fillna(0).astype(int).tolist(),
                  "year": m.install_year.fillna(0).astype(int).tolist(),
                  "len": m.length_m.round(0).astype(int).tolist()},
        "risk": _risk(ids), "passes": passes, "series": series, "img_bounds": bounds,
        "breaks": _breaks_and_evidence(), "temp": _temperature(),
    }
    js = OUT / "data.js"
    js.write_text("window.TG=" + json.dumps(_clean(data), separators=(",", ":"), allow_nan=False) + ";")
    n_img = len(list((OUT / "img").glob("*.webp")))
    size = sum(f.stat().st_size for f in (OUT / "img").glob("*.webp"))
    r = data["risk"]
    print(f"app/data.js {js.stat().st_size / 1e6:.1f} MB; {n_img} images {size / 1e6:.1f} MB")
    print(f"{len(ids)} segments, {len(passes)} passes, {len(data['breaks'])} breaks; "
          f"hold-out AUC {r['auc']:.3f}, top-5% capture {r['capture']['5']:.3f}")
