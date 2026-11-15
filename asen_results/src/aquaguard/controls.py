"""Stage 6a: control sites on the water-main network, matched to each incident.

Controls are NOT negatives. They are locations on the same kind of infrastructure with no recorded
break nearby in the study period; their label is `unknown`. They describe what "normal" change looks
like between the same acquisition dates (difference-in-differences baseline, anomaly-detection
background, evaluation reference).
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from .config import ROOT, UTM_CRS, WGS84, Config, report_file
from .sar import CityGrid, cut_patches


def _size_bucket(mm: pd.Series) -> pd.Series:
    return pd.cut(mm, [0, 150, 300, 10_000], labels=["<=150", "151-300", ">300"]).astype(str)


def candidates(cfg: Config, mains: gpd.GeoDataFrame, incidents: gpd.GeoDataFrame, t0, t1) -> gpd.GeoDataFrame:
    """Points every `sample_step_m` along mains, outside exclusion zones of recent breaks."""
    c = cfg.section("controls")
    mu = mains.to_crs(UTM_CRS)
    pts = []
    for r in mu.itertuples():
        geom = r.geometry
        for d in np.arange(c["sample_step_m"] / 2, geom.length, c["sample_step_m"]):
            p = geom.interpolate(d)
            pts.append((r.main_id, r.material, r.pipe_size_mm, r.install_year, p.x, p.y))
    cand = pd.DataFrame(pts, columns=["main_id", "material", "pipe_size_mm", "install_year", "x", "y"])
    cand = gpd.GeoDataFrame(cand, geometry=gpd.points_from_xy(cand.x, cand.y), crs=UTM_CRS)

    win = pd.Timedelta(days=c["exclusion_window_days"])
    recent = incidents[(incidents["incident_date_local"] >= (t0 - win).tz_localize(None))
                       & (incidents["incident_date_local"] <= (t1 + win).tz_localize(None))].to_crs(UTM_CRS)
    zone = recent.buffer(c["exclusion_m"]).union_all()
    cand = cand[~cand.within(zone)]
    grid = CityGrid.from_config(cfg)
    half = cfg.section("sar")["patch_size_px"] * 10 / 2 + cfg.section("sar")["filter_size"] * 10
    cand = cand[cand.x.between(grid.x0 + half, grid.x0 + grid.width * 10 - half)
                & cand.y.between(grid.y1 - grid.height * 10 + half, grid.y1 - half)]
    cand["size_bucket"] = _size_bucket(cand["pipe_size_mm"])
    return cand.reset_index(drop=True)


def select_controls(cfg: Config, cand: gpd.GeoDataFrame, sites: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """For each incident: K controls in the distance band, preferring same material and size bucket."""
    c = cfg.section("controls")
    rng = np.random.default_rng(c["seed"])
    cxy = np.c_[cand.x, cand.y]
    out = []
    for s in sites.itertuples():
        d = np.hypot(cxy[:, 0] - s.x, cxy[:, 1] - s.y)
        band = cand[(d >= c["min_distance_m"]) & (d <= c["max_distance_m"])]
        tiers = [("material+size", band[(band["material"] == s.material) & (band["size_bucket"] == s.size_bucket)]),
                 ("size", band[band["size_bucket"] == s.size_bucket]),
                 ("any", band)]
        chosen, used = [], set()
        for tier, pool in tiers:
            for j in rng.permutation(pool.index.to_numpy().copy()):
                if len(chosen) == c["per_incident"]:
                    break
                if j in used:
                    continue
                p = cand.loc[j]
                if all(np.hypot(p.x - q.x, p.y - q.y) >= c["min_spacing_m"] for q, _ in chosen):
                    chosen.append((p, tier))
                    used.add(j)
        for k, (p, tier) in enumerate(chosen):
            out.append({"control_id": f"{s.incident_id}_c{k}", "incident_id": s.incident_id, "main_id": p.main_id,
                        "match_tier": tier, "material": p.material, "pipe_size_mm": p.pipe_size_mm,
                        "install_year": p.install_year, "distance_to_incident_m": float(np.hypot(p.x - s.x, p.y - s.y)),
                        "geometry": Point(p.x, p.y)})
    return gpd.GeoDataFrame(out, geometry="geometry", crs=UTM_CRS)


def control_infra(ctl: gpd.GeoDataFrame, incidents: gpd.GeoDataFrame) -> pd.DataFrame:
    """inf_* columns for controls, computed as of the matched incident's date (no future info)."""
    inc = incidents[incidents["is_primary_record"] & ~incidents["is_cancelled"] & ~incidents["date_suspect"]]
    iu = inc.to_crs(UTM_CRS)
    when = incidents.set_index("incident_id")["incident_date_local"]
    rows = []
    for r in ctl.itertuples():
        t = when[r.incident_id]
        earlier = iu[iu["incident_date_local"] < t]
        recent = earlier[earlier["incident_date_local"] >= t - pd.Timedelta(days=5 * 365)]
        rows.append({
            "site_id": f"ctl_{r.control_id}",
            "inf_asset_material": r.material,
            "inf_asset_size_mm": r.pipe_size_mm,
            "inf_asset_year_installed": r.install_year,
            "inf_asset_age_years": (t.year - r.install_year) if pd.notna(r.install_year) else pd.NA,
            "inf_asset_depth_m": np.nan,
            "inf_prior_breaks_same_asset": int((earlier["asset_id"] == r.main_id).sum()),
            "inf_prior_breaks_within_100m_5y": int((recent.distance(r.geometry) <= 100).sum()),
        })
    out = pd.DataFrame(rows)
    out["inf_asset_year_installed"] = out["inf_asset_year_installed"].astype("Int64")
    out["inf_asset_age_years"] = pd.to_numeric(out["inf_asset_age_years"]).astype("Int64")
    return out


def run(cfg: Config, progress=None) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    from . import features

    print("Stage 6a - control sites on the water-main network")
    mains = gpd.read_parquet(cfg.path("processed_dir") / "kitchener_water_mains.parquet")
    incidents = gpd.read_parquet(cfg.incidents_parquet)
    sar_dir = ROOT / cfg.section("sar")["out_dir"]
    patches = gpd.read_parquet(sar_dir / "sar_patches.parquet")
    matches = gpd.read_parquet(cfg.matches_parquet)
    matches = matches[matches["match_confidence"] != "low"]
    t0, t1 = matches["acquisition_time"].min(), matches["acquisition_time"].max()

    cand = candidates(cfg, mains, incidents, t0, t1)
    print(f"  candidate points on mains (outside recent-break exclusion zones): {len(cand)}")
    sites = incidents[incidents["incident_id"].isin(patches["incident_id"])].to_crs(UTM_CRS)
    sites = sites.assign(x=sites.geometry.x, y=sites.geometry.y, material=sites["asset_material"],
                         size_bucket=_size_bucket(sites["asset_size_mm"]))
    ctl = select_controls(cfg, cand, sites)
    print(f"  controls: {len(ctl)} for {ctl['incident_id'].nunique()} incidents; match tiers {ctl['match_tier'].value_counts().to_dict()}")
    ctl_path = cfg.path("processed_dir") / "control_sites.parquet"
    ctl.to_crs(WGS84).to_parquet(ctl_path)
    print(f"  control sites -> {report_file(ctl_path)}")

    # Each control inherits its incident's passes and timing categories (same dates, other place).
    cm = matches.merge(ctl.to_crs(WGS84)[["control_id", "incident_id", "geometry"]].rename(columns={"geometry": "cgeom"}),
                       on="incident_id")
    cm = gpd.GeoDataFrame(cm.drop(columns="geometry").rename(columns={"cgeom": "geometry"}), geometry="geometry", crs=WGS84)
    cm["site_id"] = "ctl_" + cm["control_id"]
    cm["site_type"] = "control"
    cm["match_id"] = cm["control_id"] + "_" + cm["pass_id"]
    idx = cut_patches(cfg, gpd.GeoDataFrame(cm, crs=WGS84), "control_patches.h5", "control_patches.parquet",
                      progress, label="control patches")
    print(f"  control patches: {len(idx)} -> {report_file(sar_dir / 'control_patches.h5')}")

    infra = control_infra(ctl, incidents)
    feat = features.build(cfg, "control_patches.parquet", "control_patches.h5", infra=infra)
    out = cfg.path("processed_dir") / "control_features.parquet"
    feat.to_parquet(out)
    print(f"  control features: {len(feat)} rows ({int(feat['q_usable'].sum())} usable) -> {report_file(out)}")
    return ctl, feat
