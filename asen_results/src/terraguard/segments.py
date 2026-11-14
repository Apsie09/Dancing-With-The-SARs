"""Stage 7b: sample NISAR layers along every water-main segment -> long tables (segment x acquisition).

  seg_gcov.parquet  HH/HV dB at the pipe (5x5 boxcar) + contrast vs ~400 m surroundings      (10 m GCOV crops)
  seg_gunw.parquet  local LOS displacement [mm] (pair, high-passed vs ~2 km) + coherence    (80 m GUNW crops)
  seg_sme2.parquet  soil moisture [m3/m3] (recommended retrievals; 3x3 neighbourhood fill)  (200 m SME2 crops)

Sign convention of the GUNW displacement follows -(phase - ionosphere) * lambda / 4pi and has not been
validated against ground truth; features use magnitudes and within-segment changes, so only consistency matters.
"""
from __future__ import annotations

import json
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy.ndimage import uniform_filter

from .config import ROOT, UTM_CRS, Config, report_file

WAVELENGTH_M = 0.2384  # NISAR L-band (1257.5 MHz)


def nanmean_filter(a: np.ndarray, size: int) -> np.ndarray:
    ok = np.isfinite(a)
    num = uniform_filter(np.where(ok, a, 0.0), size, mode="nearest")
    den = uniform_filter(ok.astype(float), size, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0.05, num / den, np.nan)


def segment_points(mains: gpd.GeoDataFrame, step: float = 10.0) -> pd.DataFrame:
    mu = mains.to_crs(UTM_CRS).reset_index(drop=True)
    seg, xs, ys = [], [], []
    for i, geom in enumerate(mu.geometry):
        L = geom.length
        ds = np.arange(step / 2, L, step) if L > step else np.array([L / 2])
        for d in ds:
            p = geom.interpolate(d)
            seg.append(i)
            xs.append(p.x)
            ys.append(p.y)
    return pd.DataFrame({"seg": seg, "x": xs, "y": ys}), mu["main_id"].to_numpy()


def _index(px: np.ndarray, py: np.ndarray, xc: np.ndarray, yc: np.ndarray):
    """Nearest pixel (row, col) for points given 1-D pixel-centre coordinate arrays; -1 outside."""
    dx, dy = xc[1] - xc[0], yc[1] - yc[0]
    col = np.round((px - xc[0]) / dx).astype(int)
    row = np.round((py - yc[0]) / dy).astype(int)
    ok = (col >= 0) & (col < len(xc)) & (row >= 0) & (row < len(yc))
    return np.where(ok, row, -1), np.where(ok, col, -1)


def _agg(seg: np.ndarray, vals: dict, n_seg: int) -> pd.DataFrame:
    """Mean of each value array per segment (NaN-aware), plus number of valid points."""
    out = {}
    first = next(iter(vals.values()))
    ok0 = np.isfinite(first)
    out["n_valid_pts"] = np.bincount(seg[ok0], minlength=n_seg)
    for k, v in vals.items():
        ok = np.isfinite(v)
        s = np.bincount(seg[ok], weights=v[ok], minlength=n_seg)
        n = np.bincount(seg[ok], minlength=n_seg)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[k] = np.where(n > 0, s / n, np.nan)
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- GCOV (10 m)
def gcov(cfg: Config, pts: pd.DataFrame, main_ids: np.ndarray) -> pd.DataFrame:
    sar_dir = ROOT / cfg.section("sar")["out_dir"] / "crops"
    acq = gpd.read_parquet(cfg.acquisitions_parquet).set_index("granule_ur")
    tables = []
    crops = sorted(p for p in sar_dir.glob("*.tif") if not p.stem.endswith("_mask"))
    for k, tif in enumerate(crops):
        gid = tif.stem
        with rasterio.open(tif) as ds, rasterio.open(tif.with_name(gid + "_mask.tif")) as ms:
            hh, hv = ds.read(1), ds.read(2)
            mk = ms.read(1)
            exc = ms.read(2) if ms.count > 1 else np.zeros_like(mk)
            t = ds.transform
            xc = t.c + t.a * (np.arange(ds.width) + 0.5)
            yc = t.f + t.e * (np.arange(ds.height) + 0.5)
        valid = (mk > 0) & (mk < 255) & (exc == 0) & (hh > 0) & (hv > 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            dbh = np.where(valid, 10 * np.log10(hh), np.nan)
            dbv = np.where(valid, 10 * np.log10(hv), np.nan)
        sh, sv = nanmean_filter(dbh, 5), nanmean_filter(dbv, 5)
        bh, bv = nanmean_filter(dbh, 41), nanmean_filter(dbv, 41)
        r, c = _index(pts["x"].to_numpy(), pts["y"].to_numpy(), xc, yc)
        inside = r >= 0
        seg = pts["seg"].to_numpy()[inside]
        rr, cc = r[inside], c[inside]
        tab = _agg(seg, {"hh_db": sh[rr, cc], "hv_db": sv[rr, cc], "hh_contrast": sh[rr, cc] - bh[rr, cc],
                         "hv_contrast": sv[rr, cc] - bv[rr, cc]}, len(main_ids))
        a = acq.loc[gid]
        tab["main_id"] = main_ids
        tab["granule_ur"] = gid
        tab["time"] = a["start_time"]
        tab["comparison_group"] = a["comparison_group"]
        tables.append(tab[tab["n_valid_pts"] > 0])
        print(f"\r  gcov {k + 1}/{len(crops)}", end="", flush=True)
    print()
    return pd.concat(tables, ignore_index=True)


# --------------------------------------------------------------------------- GUNW (80 m)
def gunw(cfg: Config, pts: pd.DataFrame, main_ids: np.ndarray) -> pd.DataFrame:
    d = ROOT / cfg.section("sar")["out_dir"] / "gunw"
    cat = pd.read_parquet(cfg.path("processed_dir") / "nisar_aux_catalog.parquet").set_index("granule_ur")
    tables = []
    files = sorted(d.glob("*.npz"))
    for k, f in enumerate(files):
        z = np.load(f)
        unw, ion, coh = z["unwrapped_phase"], z["ionosphere_phase"], z["coherence"]
        cc, mask = z["connected_components"], z["mask"]
        ok = np.isfinite(unw) & (cc > 0) & (coh >= 0.3) & (mask != 255) & ((mask & 0xFF) > 0)
        ion = np.where(np.isfinite(ion), ion, 0.0)
        disp = np.where(ok, -(unw - ion) * WAVELENGTH_M / (4 * np.pi) * 1000.0, np.nan)  # mm
        local = disp - nanmean_filter(disp, 25)   # remove >~2 km trends (atmosphere, orbit, ionosphere residual)
        r, c = _index(pts["x"].to_numpy(), pts["y"].to_numpy(), z["x"], z["y"])
        inside = r >= 0
        seg = pts["seg"].to_numpy()[inside]
        rr, cc_ = r[inside], c[inside]
        tab = _agg(seg, {"los_local_mm": local[rr, cc_], "coherence": np.where(ok, coh, np.nan)[rr, cc_]}, len(main_ids))
        a = cat.loc[f.stem]
        tab["main_id"] = main_ids
        tab["granule_ur"] = f.stem
        tab["reference_time"], tab["time"] = a["reference_time"], a["secondary_time"]
        tab["track_dir"] = f"{a['track']:03d}{a['direction']}"
        tab["city_valid_frac"] = float(ok.mean())
        tables.append(tab[tab["n_valid_pts"] > 0])
        print(f"\r  gunw {k + 1}/{len(files)}", end="", flush=True)
    print()
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()


# --------------------------------------------------------------------------- SME2 (200 m)
def sme2(cfg: Config, pts: pd.DataFrame, main_ids: np.ndarray) -> pd.DataFrame:
    d = ROOT / cfg.section("sar")["out_dir"] / "sme2"
    cat = pd.read_parquet(cfg.path("processed_dir") / "nisar_aux_catalog.parquet").set_index("granule_ur")
    tr = Transformer.from_crs(UTM_CRS, "EPSG:6933", always_xy=True)
    ex, ey = tr.transform(pts["x"].to_numpy(), pts["y"].to_numpy())
    tables = []
    files = sorted(d.glob("*.npz"))
    for k, f in enumerate(files):
        z = np.load(f)
        sm, q = z["soil_moisture"].astype(float), z["retrieval_quality_flag"]
        good = (q != -9999) & ((q & 1) == 0) & (sm >= 0) & (sm <= 0.7)
        direct = np.where(good, sm, np.nan)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            filled = np.where(good, sm, nanmean_filter(direct, 3))
        r, c = _index(ex, ey, z["x"], z["y"])
        inside = r >= 0
        seg = pts["seg"].to_numpy()[inside]
        rr, cc = r[inside], c[inside]
        tab = _agg(seg, {"soil_moisture": filled[rr, cc], "sm_direct": direct[rr, cc]}, len(main_ids))
        tab["sm_from_neighbourhood"] = tab["soil_moisture"].notna() & tab["sm_direct"].isna()
        a = cat.loc[f.stem]
        tab["main_id"] = main_ids
        tab["granule_ur"] = f.stem
        tab["time"] = a["acquisition_time"]
        tab["track_dir"] = f"{a['track']:03d}{a['direction']}"
        tab["city_sm_median"] = float(np.nanmedian(direct)) if np.isfinite(direct).any() else np.nan
        tab["city_good_frac"] = float(good.mean())
        tables.append(tab[tab["soil_moisture"].notna()].drop(columns="sm_direct"))
        print(f"\r  sme2 {k + 1}/{len(files)}", end="", flush=True)
    print()
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()


def run(cfg: Config) -> None:
    print("Stage 7b - sample NISAR layers along water-main segments")
    mains = gpd.read_parquet(cfg.path("processed_dir") / "kitchener_water_mains.parquet")
    pts, main_ids = segment_points(mains)
    print(f"  {len(main_ids)} segments -> {len(pts)} sample points (10 m spacing)")
    out = cfg.path("processed_dir")
    for name, fn in (("seg_gcov", gcov), ("seg_gunw", gunw), ("seg_sme2", sme2)):
        tab = fn(cfg, pts, main_ids)
        if len(tab):
            path = out / f"{name}.parquet"
            tab.to_parquet(path)
            print(f"  {name}: {len(tab)} rows, {tab['main_id'].nunique()} segments, "
                  f"{tab['granule_ur'].nunique()} acquisitions -> {report_file(path)}")
        else:
            print(f"  {name}: no input crops yet")
