"""Stage 6b: ML-ready dataset -> data/processed/ml_dataset.parquet.

One row = one site (incident or control) x one satellite pass. Labels follow the brief:
  confirmed_break_event      acquisition falls inside the documented break interval at the site
                             (report time -> return-to-normal, or the report day when no end is known)
  candidate_satellite_match  incident site, acquisition in the potential event window (leak NOT confirmed)
  unknown                    everything else: pre/post references at the site, and all control sites
  verified_non_leak          never assigned: no independent evidence of absence exists
`label_role` says why a row is `unknown` (site_pre_reference, site_post, site_timing_uncertain,
control_matched). Split keys group incidents with their controls, by 2 km block and by time.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .config import UTM_CRS, WGS84, Config, report_file

DID_FEATURES = ["chg_ref_hh_contrast", "chg_ref_hv_contrast", "chg_ref_hvhh_contrast",
                "chg_prev_hh_contrast", "chg_prev_hv_contrast", "sd_hh_contrast", "sd_hv_contrast"]


def labels(df: pd.DataFrame, incidents: pd.DataFrame) -> pd.DataFrame:
    inc = incidents.set_index("incident_id")
    rtn = (inc["return_to_normal"] - inc["incident_date"]).dt.total_seconds() / 86400
    end = df["incident_id"].map(rtn).where(lambda s: s > 0)
    end = end.fillna(1.0)  # no recorded end: the report day only
    site = df["site_type"] == "incident"
    cat = df["temporal_category"].astype(str)
    confirmed = site & (df["delta_days"] >= -df["delta_uncertainty_days"]) & (df["delta_days"] <= end)
    cand = site & ~confirmed & (cat == "potential_event_window")
    df["label"] = np.select([confirmed, cand], ["confirmed_break_event", "candidate_satellite_match"], "unknown")
    df["label_role"] = np.select(
        [confirmed, cand, site & (cat == "pre_event"), site & (cat == "post_event"), site, ~site],
        ["break_interval", "event_window", "site_pre_reference", "site_post", "site_timing_uncertain", "control_matched"],
        "other")
    df["label_source"] = np.where(site, "City of Kitchener water-main break record (report date, location)",
                                  "control on water-main network; no recorded break within exclusion zone/window")
    conf = df["q_match_confidence"].astype(str)
    df["label_confidence"] = np.where(~site, "n/a", np.where(df["label"] == "unknown", "n/a", conf))
    return df


def did(df: pd.DataFrame) -> pd.DataFrame:
    """Difference-in-differences vs. controls of the same incident on the same pass (controls: leave-one-out)."""
    use = df[df["q_usable"]]
    ctl = use[use["site_type"] == "control"]
    g = ctl.groupby(["incident_id", "pass_id"])[DID_FEATURES]
    s, n, ss = g.sum(), g.count(), (ctl[DID_FEATURES] ** 2).groupby([ctl["incident_id"], ctl["pass_id"]]).sum()
    key = pd.MultiIndex.from_frame(df[["incident_id", "pass_id"]])
    S, N, SS = s.reindex(key).to_numpy(), n.reindex(key).to_numpy(), ss.reindex(key).to_numpy()
    x = df[DID_FEATURES].to_numpy(dtype=float)
    own = ((df["site_type"] == "control") & df["q_usable"]).to_numpy()[:, None] & np.isfinite(x)
    S = S - np.where(own, x, 0)
    SS = SS - np.where(own, x * x, 0)
    N = N - own
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = S / N
        std = np.sqrt(np.maximum(SS / N - mean**2, 0))
        for j, f in enumerate(DID_FEATURES):
            base = f.split("_", 1)[1]
            df[f"did_{base}"] = x[:, j] - mean[:, j]
            df[f"did_{base}_z"] = np.where(std[:, j] > 0.05, (x[:, j] - mean[:, j]) / std[:, j], np.nan)
    df["did_n_controls"] = N[:, 0]
    return df


def splits(df: pd.DataFrame, incidents: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    c = cfg.section("dataset")
    iu = incidents.to_crs(UTM_CRS).set_index("incident_id")
    b = c["spatial_block_m"]
    block = (iu.geometry.x // b).astype(int).astype(str) + "_" + (iu.geometry.y // b).astype(int).astype(str)
    df["split_incident_group"] = df["incident_id"]  # incident + its controls always together
    df["split_spatial_block"] = df["incident_id"].map(block)
    # Greedy balance: biggest blocks first, each into the fold with the fewest incidents so far
    # (random tie-break, seeded). Blocks never split across folds.
    rng = np.random.default_rng(c["seed"])
    size = df.drop_duplicates("incident_id").groupby("split_spatial_block").size()
    size = size.iloc[rng.permutation(len(size))].sort_values(ascending=False, kind="stable")
    load, fold = np.zeros(c["n_folds"], int), {}
    for blk, n in size.items():
        k = int(np.argmin(load))
        fold[blk], load[k] = k, load[k] + n
    df["cv_fold"] = df["split_spatial_block"].map(fold).astype("Int64")
    df["split_time_period"] = df["acquisition_time"].dt.tz_convert(None).dt.to_period("Q").astype(str)
    df["time_holdout"] = df["acquisition_time"] >= pd.Timestamp(c["time_holdout_from"], tz="UTC")
    return df


def run(cfg: Config) -> pd.DataFrame:
    import geopandas as gpd

    print("Stage 6b - ML dataset")
    inc_feat = pd.read_parquet(cfg.path("processed_dir") / "radar_features.parquet")
    ctl_feat = pd.read_parquet(cfg.path("processed_dir") / "control_features.parquet")
    inc_feat["site_type"] = "incident"
    df = pd.concat([inc_feat, ctl_feat], ignore_index=True, sort=False)
    df["site_id"] = df["site_id"].fillna("inc_" + df["incident_id"].astype(str))
    incidents = gpd.read_parquet(cfg.incidents_parquet)
    df = labels(df, incidents)
    df = did(df)
    df = splits(df, incidents, cfg)
    df["sample_id"] = df["site_id"] + "_" + df["pass_id"]
    lead = ["sample_id", "site_id", "site_type", "incident_id", "control_id", "label", "label_role",
            "label_confidence", "label_source", "acquisition_time", "delta_days", "temporal_category",
            "comparison_group", "pass_id", "granule_ur", "patch_index", "split_incident_group",
            "split_spatial_block", "cv_fold", "split_time_period", "time_holdout"]
    df = df[[c for c in lead if c in df] + [c for c in df.columns if c not in lead]]
    geom = df.pop("geometry")
    gdf = gpd.GeoDataFrame(df, geometry=gpd.GeoSeries.from_wkb(geom) if isinstance(geom.iloc[0], bytes) else geom, crs=WGS84)

    out = cfg.path("processed_dir") / "ml_dataset.parquet"
    gdf.to_parquet(out)
    groups = {g: [c for c in gdf.columns if c.startswith(g + "_")] for g in ("sd", "chg", "tex", "inf", "env", "did", "q")}
    meta = {
        "row": "site (incident or matched control) x satellite pass",
        "model_input_allowed": groups["sd"] + groups["chg"] + groups["tex"] + groups["inf"] + groups["env"] + groups["did"],
        "quality_columns": groups["q"],
        "label_side_columns": ["label", "label_role", "label_confidence", "label_source", "delta_days",
                               "temporal_category", "incident_ref_time", "incident_date_local", "incident_break_type"],
        "split_columns": ["split_incident_group", "split_spatial_block", "cv_fold", "split_time_period", "time_holdout"],
        "patch_arrays": {"incident": "data/sar/patches.h5", "control": "data/sar/control_patches.h5",
                         "key": "patch_index within the file for the row's site_type"},
        "never_negative": "control rows are `unknown`, not negatives; verified_non_leak is never assigned",
    }
    t = pq.read_table(out)
    pq.write_table(t.replace_schema_metadata({**(t.schema.metadata or {}), b"aquaguard": json.dumps(meta).encode()}), out)

    u = gdf[gdf["q_usable"]]
    print(f"  rows: {len(gdf)} ({len(u)} usable) | sites: {gdf['site_id'].nunique()} "
          f"({(gdf.drop_duplicates('site_id')['site_type'] == 'incident').sum()} incident, "
          f"{(gdf.drop_duplicates('site_id')['site_type'] == 'control').sum()} control)")
    print("  labels (usable):", u["label"].value_counts().to_dict())
    print("  label roles (usable):", u["label_role"].value_counts().to_dict())
    print("  folds (incidents per fold):", u.drop_duplicates("incident_id")["cv_fold"].value_counts().sort_index().to_dict(),
          "| time hold-out rows:", int(u["time_holdout"].sum()))
    print(f"  dataset -> {report_file(out)}")
    return gdf
