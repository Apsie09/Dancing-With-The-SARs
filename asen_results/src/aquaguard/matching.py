"""Stage 3: match incidents to candidate NISAR acquisitions (pre / around / post the reported date).

The reported incident date does not prove a leak was active at acquisition time. The
`potential_event_window` category is a matching hypothesis, not observed leakage.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import UTM_CRS, Config, human_size, report_file

CATEGORIES = ["pre_event", "potential_event_window", "post_event", "timing_uncertain"]


def incident_reference_time(inc: pd.DataFrame, tz: str) -> tuple[pd.Series, pd.Series]:
    """Reference time (UTC) and its half-width uncertainty in days.

    Exact timestamps are used when a real clock time is known; date-only records are
    referenced to local noon on the reported day with +/-0.5 day uncertainty.
    """
    noon = (inc["incident_date_local"] + pd.Timedelta(hours=12)).dt.tz_localize(tz).dt.tz_convert("UTC")
    ref = inc["incident_date"].where(inc["incident_time_known"], noon)
    unc = np.where(inc["incident_time_known"], 0.0, 0.5)
    return ref, pd.Series(unc, index=inc.index)


def categorize(delta: np.ndarray, unc: np.ndarray, windows: dict[str, tuple[float, float]]) -> np.ndarray:
    """Assign a window only if the whole uncertainty interval [delta-unc, delta+unc] lies inside it."""
    lo, hi = delta - unc, delta + unc
    out = np.full(delta.shape, "timing_uncertain", dtype=object)
    for name in ("pre_event", "potential_event_window", "post_event"):
        a, b = windows[name]
        out[(lo >= a) & (hi <= b)] = name
    return out


def confidence(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    flags = {
        "beta_product": df["maturity"].eq("beta"),
        "partial_frame": ~df["full_frame"],
        "date_suspect": df["date_suspect"],
        "cancelled_incident": df["is_cancelled"],
        "timing_uncertain": df["temporal_category"].eq("timing_uncertain"),
        "near_footprint_edge": df["near_footprint_edge"],
        "possible_duplicate": ~df["is_primary_record"],
        "location_suspect": df["location_suspect"],
    }
    low_keys = ["beta_product", "partial_frame", "date_suspect", "cancelled_incident", "timing_uncertain"]
    reasons = pd.Series([""] * len(df), index=df.index)
    for k, m in flags.items():
        reasons = reasons.where(~m, reasons + np.where(reasons == "", "", ";") + k)
    low = np.logical_or.reduce([flags[k].to_numpy() for k in low_keys])
    medium = (flags["near_footprint_edge"].to_numpy() | flags["possible_duplicate"].to_numpy()
              | flags["location_suspect"].to_numpy())
    level = np.where(low, "low", np.where(medium, "medium", "high"))
    return pd.Series(level, index=df.index), reasons


def match(incidents: gpd.GeoDataFrame, acq: gpd.GeoDataFrame, cfg: Config) -> gpd.GeoDataFrame:
    m = cfg.section("matching")
    tz = cfg.section("incidents")["local_timezone"]
    windows = {k: tuple(m[k]) for k in ("pre_event", "potential_event_window", "post_event")}
    dmin, dmax = windows["pre_event"][0], windows["post_event"][1]

    acq = acq[acq["is_preferred"] & acq["collection"].isin(m["use_collections"])].copy()
    inc = incidents.copy()
    inc["ref_time"], inc["delta_uncertainty_days"] = incident_reference_time(inc, tz)

    # Spatial: incident point inside the acquisition footprint.
    pairs = gpd.sjoin(inc, acq, how="inner", predicate="within", lsuffix="inc", rsuffix="acq")
    pairs["delta_days"] = (pairs["start_time"] - pairs["ref_time"]).dt.total_seconds() / 86400
    pairs = pairs[(pairs["delta_days"] >= dmin - 0.5) & (pairs["delta_days"] <= dmax + 0.5)].copy()

    # Distance from the incident to the footprint boundary (the footprint is a coarse outline, so
    # points close to it may fall in no-data margins of the actual raster).
    fp = acq.geometry.to_crs(UTM_CRS).boundary
    pts = gpd.GeoSeries(pairs.geometry, crs=inc.crs).to_crs(UTM_CRS)
    pairs["edge_distance_m"] = [pt.distance(fp.loc[i]) for pt, i in zip(pts, pairs["index_acq"])]
    pairs["near_footprint_edge"] = pairs["edge_distance_m"] < cfg.section("nisar")["edge_buffer_m"]

    # One observation per incident per pass: adjacent frames of the same pass are the same
    # measurement; keep the frame where the incident lies deepest inside the footprint.
    pairs = (pairs.sort_values("edge_distance_m", ascending=False)
                  .drop_duplicates(["incident_id", "pass_id"]))

    pairs["temporal_category"] = categorize(pairs["delta_days"].to_numpy(),
                                            pairs["delta_uncertainty_days"].to_numpy(), windows)
    pairs.loc[pairs["date_suspect"], "temporal_category"] = "timing_uncertain"
    pairs["temporal_category"] = pd.Categorical(pairs["temporal_category"], categories=CATEGORIES)
    pairs["match_confidence"], pairs["confidence_reasons"] = confidence(pairs)

    out = pairs.rename(columns={"start_time": "acquisition_time"})[[
        "incident_id", "granule_ur", "pass_id", "comparison_group", "stack_id", "track", "direction",
        "frame", "collection", "maturity", "crid", "product_version", "freq_a_pols",
        "freq_a_bandwidth_mhz", "posting_m_nominal", "full_frame", "acquisition_time", "ref_time",
        "incident_date_local", "incident_time_known", "delta_days", "delta_uncertainty_days",
        "temporal_category", "edge_distance_m", "near_footprint_edge", "break_type", "is_cancelled",
        "is_primary_record", "location_suspect", "date_suspect", "match_confidence", "confidence_reasons", "size_bytes",
        "h5_https", "geometry"]].rename(columns={"ref_time": "incident_ref_time",
                                                 "size_bytes": "granule_size_bytes"})
    out["abs_delta_days"] = out["delta_days"].abs()
    out = out.sort_values(["incident_ref_time", "incident_id", "acquisition_time"]).reset_index(drop=True)
    out.insert(0, "match_id", out["incident_id"].astype(str) + "_" + out["pass_id"])
    return gpd.GeoDataFrame(out, geometry="geometry", crs=inc.crs)


def coverage_summary(matches: pd.DataFrame, incidents: pd.DataFrame, acq: pd.DataFrame,
                     cfg: Config) -> pd.DataFrame:
    """One row per incident: NISAR period / coverage flags and best consistent before/after set."""
    m = cfg.section("matching")
    use = acq[acq["is_preferred"] & acq["collection"].isin(m["use_collections"])]
    t0, t1 = use["start_time"].min(), use["start_time"].max()
    inc = incidents[["incident_id", "incident_date_local", "break_type", "is_cancelled",
                     "is_primary_record", "date_suspect", "geometry"]].copy()
    local_day = inc["incident_date_local"].dt.tz_localize("UTC")
    inc["in_nisar_period"] = (local_day >= t0.floor("D")) & (local_day <= t1)
    union = use.geometry.union_all()
    inc["in_footprint"] = inc.geometry.within(union)

    rows = []
    good = matches[matches["match_confidence"] != "low"]
    for iid, g in good.groupby("incident_id"):
        best, before_after, event_ref = None, False, False
        for grp, gg in g.groupby("comparison_group"):
            cats = set(gg["temporal_category"].astype(str))
            pre, ev, post = "pre_event" in cats, "potential_event_window" in cats, "post_event" in cats
            before_after |= pre and post   # a valid pair must come from ONE comparison group
            event_ref |= pre and ev
            score = (pre and ev) * 4 + (pre and post) * 2 + ev + post
            if best is None or score > best[0]:
                best = (score, grp, gg)
        _, grp, gg = best
        def nearest(cat):
            s = gg.loc[gg["temporal_category"] == cat, "delta_days"]
            return s.abs().min() if len(s) else np.nan
        rows.append({
            "incident_id": iid,
            "n_matches_usable": len(g),
            "best_comparison_group": grp,
            "n_pre": int((gg["temporal_category"] == "pre_event").sum()),
            "n_event_window": int((gg["temporal_category"] == "potential_event_window").sum()),
            "n_post": int((gg["temporal_category"] == "post_event").sum()),
            "nearest_pre_days": nearest("pre_event"),
            "nearest_event_days": nearest("potential_event_window"),
            "nearest_post_days": nearest("post_event"),
            "mixed_processing_versions": gg["crid"].nunique() > 1,
            "has_before_after": before_after,
            "has_event_with_reference": event_ref,
        })
    summ = pd.DataFrame(rows)
    out = inc.drop(columns="geometry").merge(summ, on="incident_id", how="left")
    out["n_matches_usable"] = out["n_matches_usable"].fillna(0).astype(int)
    for c in ("n_pre", "n_event_window", "n_post"):
        out[c] = out[c].fillna(0).astype(int)
    for c in ("has_before_after", "has_event_with_reference", "mixed_processing_versions"):
        out[c] = out[c].fillna(False).astype(bool)
    return out


def run(cfg: Config) -> gpd.GeoDataFrame:
    from . import catalog, incidents

    print("Stage 3 - spatiotemporal matching")
    inc, acq = incidents.load(cfg), catalog.load(cfg)
    matches = match(inc, acq, cfg)
    matches.to_parquet(cfg.matches_parquet, schema_version="1.0.0")
    cov = coverage_summary(matches, inc, acq, cfg)
    cov.to_parquet(cfg.coverage_parquet)

    print(f"  matches: {len(matches)} (incident x pass) for {matches['incident_id'].nunique()} incidents")
    print("  by category:   ", matches["temporal_category"].value_counts(sort=False).to_dict())
    print("  by confidence: ", matches["match_confidence"].value_counts().to_dict())
    print(f"  incidents with consistent before+after: {int(cov['has_before_after'].sum())}, "
          f"with pre + event-window: {int(cov['has_event_with_reference'].sum())}")
    usable = matches[matches["match_confidence"] != "low"]
    n_gran = usable["granule_ur"].nunique()
    print(f"  SAR NEEDED for usable matches: {n_gran} granules = "
          f"{human_size(usable.drop_duplicates('granule_ur')['granule_size_bytes'].sum())} remote "
          f"(stream crops only; see report for crop-size estimates)")
    print(f"  matches  -> {report_file(cfg.matches_parquet)}")
    print(f"  coverage -> {report_file(cfg.coverage_parquet)}")
    return matches
