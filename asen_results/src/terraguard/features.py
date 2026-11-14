"""Stage 5: feature extraction -> radar_features.parquet (one row per incident x pass patch).

Feature groups (column prefixes):
  sd_*    single-date SAR statistics at the break site (centre disk) and its background ring
  chg_*   change vs. a reference built from pre-event acquisitions on the SAME comparison group
          (leave-one-out for pre-event rows) and vs. the previous acquisition on that track
  tex_*   texture (coefficient of variation, gray-level co-occurrence statistics)
  inf_*   infrastructure attributes known BEFORE the incident (no post-incident fields)
  env_*   weather / soil state at acquisition time (ERA5 via Open-Meteo, one point for the city)
  q_*     observation-quality indicators
Timing/label-side columns (delta_days, temporal_category, ...) are kept for matching and labelling,
never as model inputs: they encode knowledge of the incident.
"""
from __future__ import annotations

import json

import geopandas as gpd
import h5py
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import requests

from .config import ROOT, Config, report_file

POLS = ("hh", "hv")
WEATHER_CACHE = "open_meteo_kitchener.parquet"


# --------------------------------------------------------------------------- geometry masks
def region_masks(size: int, f: dict) -> dict[str, np.ndarray]:
    c = size // 2  # incident pixel (patch_row0 = row - size // 2)
    yy, xx = np.mgrid[:size, :size]
    r = np.hypot(yy - c, xx - c)
    return {"center": r <= f["center_radius_px"],
            "ring": (r >= f["ring_inner_px"]) & (r <= f["ring_outer_px"]),
            "texture": (np.abs(yy - c) <= f["texture_radius_px"]) & (np.abs(xx - c) <= f["texture_radius_px"])}


def _stats(a: np.ndarray, m: np.ndarray) -> tuple[float, float, float]:
    v = a[m]
    v = v[np.isfinite(v)]
    if v.size == 0:
        return np.nan, np.nan, np.nan
    return float(v.mean()), float(np.median(v)), float(v.std())


def _contrast(a: np.ndarray, masks: dict) -> dict:
    cm, cmed, cs = _stats(a, masks["center"])
    rm, rmed, rs = _stats(a, masks["ring"])
    return {"center_mean": cm, "center_median": cmed, "center_std": cs, "ring_mean": rm, "ring_std": rs,
            "contrast": cm - rm, "contrast_z": (cm - rm) / rs if rs and np.isfinite(rs) and rs > 0 else np.nan}


# --------------------------------------------------------------------------- texture
def texture(db: np.ndarray, lin: np.ndarray, valid: np.ndarray, masks: dict, f: dict) -> dict:
    from skimage.feature import graycomatrix, graycoprops

    out = {}
    m = masks["texture"] & valid & np.isfinite(db)
    v = lin[masks["center"] & valid & np.isfinite(lin) & (lin > 0)]
    out["cv_center"] = float(v.std() / v.mean()) if v.size > 3 and v.mean() > 0 else np.nan
    if m.mean() < 0.5 * masks["texture"].mean():
        return out | {k: np.nan for k in ("glcm_contrast", "glcm_homogeneity", "glcm_energy", "glcm_correlation", "glcm_entropy")}
    rows = np.where(masks["texture"].any(1))[0]
    cols = np.where(masks["texture"].any(0))[0]
    win = db[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    lo, hi = f["glcm_db_range"]
    L = f["glcm_levels"]
    q = np.clip((np.nan_to_num(win, nan=lo) - lo) / (hi - lo) * (L - 1), 0, L - 1).astype(np.uint8)
    glcm = graycomatrix(q, distances=[1], angles=[0, np.pi / 4, np.pi / 2, 3 * np.pi / 4], levels=L,
                        symmetric=True, normed=True)
    for prop in ("contrast", "homogeneity", "energy", "correlation"):
        out[f"glcm_{prop}"] = float(graycoprops(glcm, prop).mean())
    p = glcm.mean(axis=(2, 3))
    p = p[p > 0]
    out["glcm_entropy"] = float(-(p * np.log2(p)).sum())
    return out


# --------------------------------------------------------------------------- weather
def weather(cfg: Config, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Hourly ERA5 soil/snow + daily precipitation/temperature for one Kitchener point (cached)."""
    f = cfg.section("features")
    path = cfg.path("raw_dir") / WEATHER_CACHE
    if path.exists():
        w = pd.read_parquet(path)
        if w.index.min() <= start and w.index.max() >= end - pd.Timedelta(days=1):
            return w
    params = {"latitude": f["weather_lat"], "longitude": f["weather_lon"], "timezone": "UTC",
              "start_date": f"{start:%Y-%m-%d}", "end_date": f"{end:%Y-%m-%d}",
              "hourly": "precipitation,rain,snowfall,temperature_2m,soil_moisture_0_to_7cm,"
                        "soil_temperature_0_to_7cm,snow_depth"}
    r = requests.get("https://archive-api.open-meteo.com/v1/archive", params=params, timeout=120)
    r.raise_for_status()
    h = r.json()["hourly"]
    w = pd.DataFrame(h).assign(time=lambda d: pd.to_datetime(d["time"], utc=True)).set_index("time")
    w.to_parquet(path)
    print(f"  weather cache -> {report_file(path)}  ({len(w)} hourly rows, ERA5 via Open-Meteo)")
    return w


def env_features(w: pd.DataFrame, t: pd.Timestamp) -> dict:
    t = t.floor("h")
    if t not in w.index:
        return {}
    before = lambda hours: w.loc[t - pd.Timedelta(hours=hours):t]
    at = w.loc[t]
    return {
        "env_precip_3d_mm": float(before(72)["precipitation"].sum()),
        "env_precip_7d_mm": float(before(168)["precipitation"].sum()),
        "env_precip_14d_mm": float(before(336)["precipitation"].sum()),
        "env_snowfall_7d_cm": float(before(168)["snowfall"].sum()),
        "env_air_temp_c": float(at["temperature_2m"]),
        "env_air_temp_min_72h_c": float(before(72)["temperature_2m"].min()),
        "env_soil_moisture_m3m3": float(at["soil_moisture_0_to_7cm"]),
        "env_soil_temp_c": float(at["soil_temperature_0_to_7cm"]),
        "env_snow_depth_m": float(at["snow_depth"]),
        "env_frozen_or_snow": bool(at["soil_temperature_0_to_7cm"] <= 0 or at["snow_depth"] > 0.01),
    }


# --------------------------------------------------------------------------- main
def build(cfg: Config, index_name: str = "sar_patches.parquet", h5_name: str = "patches.h5",
          infra: pd.DataFrame | None = None) -> pd.DataFrame:
    """Features for one patch set. `infra` (site_id + inf_* columns) overrides the incident lookup,
    e.g. for control sites whose infrastructure comes from the water-main network."""
    f = cfg.section("features")
    sar_dir = ROOT / cfg.section("sar")["out_dir"]
    idx = gpd.read_parquet(sar_dir / index_name).sort_values("patch_index").reset_index(drop=True)
    if "site_id" not in idx:  # patch sets cut before site_id existed
        idx["site_id"] = "inc_" + idx["incident_id"].astype(str)
    with h5py.File(sar_dir / h5_name, "r") as h5:
        db = h5["db_filtered"][:]          # (N, 2, S, S) filtered dB, NaN invalid
        lin = h5["gamma0"][:]              # (N, 2, S, S) original linear gamma0
        valid = h5["valid"][:]             # (N, S, S)
        looks = h5["numberOfLooks"][:]
    size = db.shape[-1]
    masks = region_masks(size, f)
    db = np.where(valid[:, None], db, np.nan)

    # ---- quality + single-date + texture
    rows = []
    for i in range(len(idx)):
        r = {"q_valid_frac": float(valid[i].mean()),
             "q_center_valid_frac": float(valid[i][masks["center"]].mean()),
             "q_mean_looks": float(np.nanmean(looks[i])) if np.isfinite(looks[i]).any() else np.nan}
        for b, p in enumerate(POLS):
            for k, v in _contrast(db[i, b], masks).items():
                r[f"sd_{p}_{k}"] = v
            for k, v in texture(db[i, b], lin[i, b], valid[i], masks, f).items():
                r[f"tex_{p}_{k}"] = v
        xpol = db[i, 1] - db[i, 0]  # HV/HH ratio in dB
        for k, v in _contrast(xpol, masks).items():
            r[f"sd_hvhh_{k}"] = v
        rows.append(r)
    feat = pd.concat([idx.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    feat["q_usable"] = (feat["q_valid_frac"] >= f["min_valid_frac"]) & (feat["q_center_valid_frac"] >= f["min_center_valid_frac"])

    # ---- temporal change, strictly within (incident, comparison_group)
    chg = {}
    for (iid, grp), g in feat[feat["q_usable"]].groupby(["site_id", "comparison_group"]):
        g = g.sort_values("acquisition_time")
        pre = g[g["temporal_category"] == "pre_event"]
        for j, r in g.iterrows():
            ref_rows = pre.drop(index=j, errors="ignore")  # leave-one-out for pre-event rows
            out = {"chg_n_ref": len(ref_rows)}
            if len(ref_rows):
                stack = db[ref_rows["patch_index"].to_numpy()]
                with np.errstate(all="ignore"), __import__("warnings").catch_warnings():
                    __import__("warnings").simplefilter("ignore", RuntimeWarning)  # pixels invalid in every ref
                    ref_med = np.nanmedian(stack, axis=0)
                ref_std = np.nanstd(stack, axis=0) if len(ref_rows) >= 3 else None
                out["chg_ref_span_days"] = float((ref_rows["acquisition_time"].max() - ref_rows["acquisition_time"].min()).days)
                out["chg_ref_mixed_crid"] = ref_rows["crid"].nunique() > 1 or (ref_rows["crid"] != r["crid"]).any()
                for b, p in enumerate(POLS):
                    d = db[r["patch_index"], b] - ref_med[b]
                    for k, v in _contrast(d, masks).items():
                        if k in ("center_mean", "ring_mean", "ring_std", "contrast", "contrast_z"):
                            out[f"chg_ref_{p}_{k}"] = v
                    if ref_std is not None:
                        z = d / np.where(ref_std[b] > 0.1, ref_std[b], np.nan)
                        out[f"chg_ref_{p}_temporal_z_center"] = _stats(z, masks["center"])[0]
                dx = (db[r["patch_index"], 1] - db[r["patch_index"], 0]) - (ref_med[1] - ref_med[0])
                out["chg_ref_hvhh_contrast"] = _contrast(dx, masks)["contrast"]
            prev = g[g["acquisition_time"] < r["acquisition_time"]].tail(1)
            if len(prev):
                pp = prev.iloc[0]
                out["chg_prev_days"] = (r["acquisition_time"] - pp["acquisition_time"]).total_seconds() / 86400
                for b, p in enumerate(POLS):
                    d = db[r["patch_index"], b] - db[pp["patch_index"], b]
                    c = _contrast(d, masks)
                    out[f"chg_prev_{p}_center_mean"] = c["center_mean"]
                    out[f"chg_prev_{p}_contrast"] = c["contrast"]
            chg[j] = out
    feat = feat.join(pd.DataFrame.from_dict(chg, orient="index"))

    # ---- infrastructure (pre-incident only) + incident attribute known at report time
    if infra is None:
        inc = pd.read_parquet(cfg.incidents_parquet)
        roles = json.loads(pq.read_schema(cfg.incidents_parquet).metadata[b"terraguard"])["column_roles"]
        pre_cols = [c for c, role in roles.items() if role == "pre_incident" and c in inc.columns]
        infra = inc[["incident_id", *pre_cols]].rename(columns={c: f"inf_{c}" for c in pre_cols})
        infra["site_id"] = "inc_" + infra.pop("incident_id").astype(str)
    feat = feat.drop(columns=[c for c in feat.columns if c.startswith("inf_")], errors="ignore").merge(infra, on="site_id", how="left")
    feat = feat.rename(columns={"break_type": "incident_break_type"})

    # ---- environment at acquisition time
    t0 = feat["acquisition_time"].min() - pd.Timedelta(days=15)
    t1 = feat["acquisition_time"].max() + pd.Timedelta(days=1)
    try:
        w = weather(cfg, t0, t1)
        env = pd.DataFrame([env_features(w, t) for t in feat["acquisition_time"]], index=feat.index)
        feat = feat.join(env)
    except requests.RequestException as e:
        print(f"  weather unavailable ({e}); env_* features skipped")

    # ---- tidy
    feat = feat.rename(columns={"valid_frac": "q_patch_valid_frac", "exception_frac": "q_exception_frac",
                                "outside_coverage_frac": "q_outside_coverage_frac", "maturity": "q_maturity",
                                "match_confidence": "q_match_confidence", "near_footprint_edge": "q_near_footprint_edge"})
    drop = ["hh_db_median", "hv_db_median", "mean_looks", "h5_https", "granule_size_bytes", "q_patch_valid_frac"]
    return feat.drop(columns=[c for c in drop if c in feat.columns])


COLUMN_GROUPS = {
    "identifier": ["match_id", "incident_id", "site_id", "site_type", "control_id", "granule_ur", "pass_id",
                   "patch_index", "crop_path"],
    "label_side_timing": ["delta_days", "abs_delta_days", "temporal_category", "incident_ref_time",
                          "incident_date_local", "delta_uncertainty_days", "incident_time_known", "incident_break_type",
                          "is_cancelled", "is_primary_record", "location_suspect", "date_suspect"],
}


def run(cfg: Config) -> pd.DataFrame:
    print("Stage 5 - feature extraction")
    feat = build(cfg)
    out = cfg.path("processed_dir") / "radar_features.parquet"
    groups = {g: [c for c in feat.columns if c.startswith(g + "_")] for g in ("sd", "chg", "tex", "inf", "env", "q")}
    meta = {"feature_groups": groups, **COLUMN_GROUPS,
            "model_input_allowed": groups["sd"] + groups["chg"] + groups["tex"] + groups["inf"] + groups["env"],
            "note": "label_side_timing columns encode incident knowledge: use for labels/splits only",
            "config": cfg.section("features")}
    feat.to_parquet(out)
    t = pq.read_table(out)
    pq.write_table(t.replace_schema_metadata({**(t.schema.metadata or {}), b"terraguard": json.dumps(meta, default=str).encode()}), out)
    print(f"  rows: {len(feat)} ({int(feat['q_usable'].sum())} usable), incidents: {feat['incident_id'].nunique()}")
    for g, cols in groups.items():
        print(f"  {g:4s} {len(cols):3d} columns")
    print(f"  with a pre-event reference: {int(feat['chg_n_ref'].fillna(0).gt(0).sum())} rows")
    print(f"  features -> {report_file(out)}")
    return feat
