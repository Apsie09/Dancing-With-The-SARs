"""Stage 2: discover NISAR L2 GCOV acquisitions over the study area (metadata only, no login, no download)."""
from __future__ import annotations

import earthaccess
import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, box

from .config import MATURITY, MATURITY_RANK, UTM_CRS, WGS84, Config, human_size, report_file

# Nominal GCOV frequency-A posting by range bandwidth (MHz -> m). NOT VERIFIED: confirm from the
# HDF5 grid spacing (xCoordinateSpacing) before Stage 4 relies on it.
NOMINAL_POSTING_M = {20: 20, 40: 10}


def _attrs(umm: dict) -> dict:
    return {a["Name"]: a["Values"] for a in umm.get("AdditionalAttributes", [])}


def _first(d: dict, k: str, default=None):
    v = d.get(k)
    return v[0] if v else default


def _bandwidth(a: dict, key: str) -> int | None:
    v = _first(a, key)
    return int(float(v)) if v else None


def _footprint(umm: dict) -> Polygon:
    gp = umm["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]
    return Polygon([(p["Longitude"], p["Latitude"]) for p in gp["Boundary"]["Points"]])


def _url(umm: dict, prefix: str, suffix: str) -> str | None:
    for u in umm.get("RelatedUrls", []):
        if u["URL"].startswith(prefix) and u["URL"].endswith(suffix):
            return u["URL"]
    return None


def parse_granule(umm: dict, collection: str) -> dict:
    a = _attrs(umm)
    name = umm["GranuleUR"]
    tok = name.split("_")  # NISAR_L2_PR_GCOV_<cycle>_<track>_<A|D>_<frame>_<mode>_<pols>_..._<CRID>_..._<counter>
    files = umm["DataGranule"]["ArchiveAndDistributionInformation"]
    h5 = next((f for f in files if f["Name"].endswith(".h5")), {})
    bw_a = _bandwidth(a, "FREQUENCY_A_RANGE_BANDWIDTH")
    bw_b = _bandwidth(a, "FREQUENCY_B_RANGE_BANDWIDTH")
    instr = umm["Platforms"][0]["Instruments"][0]
    look = next((ch["Value"] for ch in instr.get("Characteristics", []) if ch["Name"] == "LookDirection"), None)
    track, direction = int(_first(a, "TRACK_NUMBER")), _first(a, "ASCENDING_DESCENDING")[0]
    return {
        "granule_ur": name,
        "collection": collection,
        "maturity": MATURITY[collection],
        "start_time": pd.Timestamp(umm["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]),
        "end_time": pd.Timestamp(umm["TemporalExtent"]["RangeDateTime"]["EndingDateTime"]),
        "cycle": int(tok[4]),
        "track": track,
        "direction": direction,
        "frame": int(_first(a, "FRAME_NUMBER")),
        "stack_id": _first(a, "STACK_ID"),
        "look_direction": look,
        "orbit_number": umm.get("OrbitCalculatedSpatialDomains", [{}])[0].get("OrbitNumber"),
        "orbit_type": _first(a, "ORBIT_TYPE"),
        "radar_mode": tok[8],
        "pol_mode": tok[9],
        "freq_a_pols": _first(a, "FREQUENCY_A_POLARIZATION_CONCAT"),
        "freq_a_bandwidth_mhz": bw_a,
        "freq_b_pols": _first(a, "FREQUENCY_B_POLARIZATION_CONCAT"),
        "freq_b_bandwidth_mhz": bw_b,
        "posting_m_nominal": NOMINAL_POSTING_M.get(bw_a),
        "posting_verified": False,
        "full_frame": _first(a, "FULL_FRAME") == "TRUE",
        "joint_observation": _first(a, "JOINT_OBSERVATION") == "TRUE",
        "product_version": _first(a, "PRODUCT_VERSION"),
        "crid": tok[13],
        "product_counter": int(tok[-1]),
        "production_time": pd.Timestamp(umm["DataGranule"].get("ProductionDateTime")),
        "size_bytes": int(h5.get("SizeInBytes", 0)),
        "h5_https": _url(umm, "https://", ".h5"),
        "h5_s3": _url(umm, "s3://", ".h5"),
        "browse_png": _url(umm, "https://", "_LATLON.png"),
        "geometry": _footprint(umm),
    }


def search(cfg: Config) -> gpd.GeoDataFrame:
    c = cfg.section("nisar")
    rows = []
    for sn in c["collections"]:
        res = earthaccess.search_data(short_name=sn, bounding_box=tuple(c["aoi_bbox"]),
                                      temporal=(c["temporal_start"], c["temporal_end"]), count=-1)
        print(f"  {sn:32s} {len(res):4d} granules")
        rows += [parse_granule(g["umm"], sn) for g in res]
    if not rows:
        raise RuntimeError("no NISAR granules found for the AOI")
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84)


def annotate(gdf: gpd.GeoDataFrame, cfg: Config, incidents: gpd.GeoDataFrame | None) -> gpd.GeoDataFrame:
    gdf = gdf.sort_values("start_time").reset_index(drop=True)
    # Reprocessed copies (_001 -> _002): keep the highest product counter.
    base = gdf["granule_ur"].str.rsplit("_", n=1).str[0]
    gdf["is_superseded"] = gdf["product_counter"] < gdf.groupby(base)["product_counter"].transform("max")
    # The same pass published in several collections (e.g. beta and provisional): keep highest maturity.
    gdf["maturity_rank"] = gdf["maturity"].map(MATURITY_RANK)
    gdf["acquisition_key"] = gdf["stack_id"] + "_" + gdf["radar_mode"] + "_" + gdf["start_time"].dt.strftime("%Y%m%dT%H%M%S")
    live = gdf[~gdf["is_superseded"]].sort_values(["maturity_rank", "production_time"], ascending=False)
    best = live.drop_duplicates("acquisition_key").index
    gdf["is_preferred"] = gdf.index.isin(best)
    # Pass = one satellite overpass; adjacent frames (e.g. 127D 066/067) belong to the same pass.
    gdf["pass_id"] = (gdf["track"].astype(str).str.zfill(3) + gdf["direction"] + "_"
                      + gdf["start_time"].dt.strftime("%Y%m%d"))
    # Observations are directly comparable only with the same viewing geometry (track + direction),
    # bandwidth and polarisations. Processing version (CRID) differences are recorded, not hidden.
    gdf["comparison_group"] = (gdf["track"].astype(str).str.zfill(3) + gdf["direction"] + "_A"
                               + gdf["freq_a_bandwidth_mhz"].astype(str) + "MHz_"
                               + gdf["freq_a_pols"].fillna("NA"))

    aoi = gpd.GeoSeries([box(*cfg.section("nisar")["aoi_bbox"])], crs=WGS84).to_crs(UTM_CRS).iloc[0]
    fp = gdf.geometry.to_crs(UTM_CRS)
    gdf["aoi_overlap_frac"] = fp.intersection(aoi).area / aoi.area
    if incidents is not None:
        pts = incidents.geometry
        gdf["n_incidents_inside"] = [int(pts.within(g).sum()) for g in gdf.geometry]
    return gdf.drop(columns="maturity_rank")


def run(cfg: Config) -> gpd.GeoDataFrame:
    print("Stage 2 - NISAR GCOV catalogue (CMR metadata only)")
    gdf = search(cfg)
    incidents = None
    if cfg.incidents_parquet.exists():
        incidents = gpd.read_parquet(cfg.incidents_parquet)
    gdf = annotate(gdf, cfg, incidents)
    gdf.to_parquet(cfg.acquisitions_parquet, schema_version="1.0.0")

    use = gdf[gdf["is_preferred"]]
    print(f"  granules: {len(gdf)} found, {len(use)} preferred "
          f"({int(gdf['is_superseded'].sum())} superseded, {len(gdf) - len(use) - int(gdf['is_superseded'].sum())} duplicate passes in a lower-maturity collection)")
    print(f"  date range: {use['start_time'].min():%Y-%m-%d} -> {use['start_time'].max():%Y-%m-%d}")
    for grp, g in use.groupby("comparison_group"):
        print(f"   {grp:28s} {len(g):3d} acq  frames {sorted(int(f) for f in g["frame"].unique())}  maturity {g["maturity"].value_counts().to_dict()}")
    print(f"  REMOTE SAR VOLUME (preferred granules, full HDF5): {human_size(use['size_bytes'].sum())}"
          f"  (mean {human_size(use['size_bytes'].mean())} per granule) -- not downloaded")
    print(f"  catalogue -> {report_file(cfg.acquisitions_parquet)}")
    return gdf


def load(cfg: Config) -> gpd.GeoDataFrame:
    return gpd.read_parquet(cfg.acquisitions_parquet)

