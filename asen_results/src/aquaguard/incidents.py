"""Stage 1: fetch and clean Kitchener water-main break incidents from the ArcGIS Feature Service."""
from __future__ import annotations

import json
import time
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from .config import UTM_CRS, WGS84, Config, report_file

# Role of every attribute w.r.t. the incident timeline. Only `pre_incident` columns may be used as
# predictive features for a model meant to flag leaks *before* they are reported.
COLUMN_ROLES = {
    "incident_id": "identifier",
    "objectid": "identifier",
    "asset_id": "identifier",
    "road_segment_id": "identifier",
    "civic_number": "location",
    "street": "location",
    "lon": "location",
    "location_suspect": "quality",
    "lat": "location",
    "utm_x": "location",
    "utm_y": "location",
    "asset_size_mm": "pre_incident",
    "asset_material": "pre_incident",
    "asset_year_installed": "pre_incident",
    "asset_depth_m": "pre_incident",
    "asset_age_years": "pre_incident",
    "prior_breaks_same_asset": "pre_incident",
    "prior_breaks_within_100m_5y": "pre_incident",
    "incident_date": "event_time",
    "incident_date_local": "event_time",
    "incident_time_known": "event_time",
    "break_type": "at_report",
    "status": "post_incident",
    "status_date": "post_incident",
    "return_to_normal": "post_incident",
    "break_nature": "post_incident",
    "break_apparent_cause": "post_incident",
    "break_categorization": "post_incident",
    "repair_type": "post_incident",
    "frost_depth_m": "post_incident",
    "road_closed": "post_incident",
    "hours_impacted": "post_incident",
    "asset_exists": "post_incident",
    "update_date": "post_incident",
}

RENAME = {
    "OBJECTID": "objectid",
    "WATBREAKINCIDENTID": "incident_id",
    "INCIDENT_DATE": "incident_date",
    "BREAK_TYPE": "break_type",
    "STATUS": "status",
    "STATUS_DATE": "status_date",
    "RETURN_TO_NORMAL": "return_to_normal",
    "BREAK_NATURE": "break_nature",
    "BREAK_APPARENT_CAUSE": "break_apparent_cause",
    "BREAK_CATEGORIZATION": "break_categorization",
    "REPAIR_TYPE": "repair_type",
    "ROAD_CLOSED": "road_closed",
    "HOUR_IMPACTED": "hours_impacted",
    "ROADSEGMENTID": "road_segment_id",
    "CIVIC_NUMBER": "civic_number",
    "STREET": "street",
    "ASSETID": "asset_id",
    "ASSET_DEPTH": "asset_depth_m",
    "FROST_DEPTH": "frost_depth_m",
    "ASSET_SIZE": "asset_size_mm",
    "ASSET_YEAR_INSTALLED": "asset_year_installed",
    "ASSET_MATERIAL": "asset_material",
    "ASSET_EXISTS": "asset_exists",
    "UPDATE_DATE": "update_date",
}
DATE_COLS = ["incident_date", "status_date", "return_to_normal", "update_date"]


# --------------------------------------------------------------------------- fetch
def fetch_raw(cfg: Config) -> dict:
    """Page through the Feature Service (GeoJSON, WGS84) and return one FeatureCollection."""
    c = cfg.section("incidents")
    url, page = c["feature_service"] + "/query", int(c["page_size"])
    expected = requests.get(url, params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
                            timeout=60).json()["count"]
    feats, offset = [], 0
    while True:
        params = {"where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson",
                  "orderByFields": "OBJECTID", "resultOffset": offset, "resultRecordCount": page}
        for attempt in range(4):
            try:
                r = requests.get(url, params=params, timeout=120)
                r.raise_for_status()
                batch = r.json()["features"]
                break
            except (requests.RequestException, KeyError, ValueError):
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        feats += batch
        print(f"  fetched {len(feats)}/{expected}")
        if len(batch) < page:
            break
        offset += page
    if len(feats) != expected:
        raise RuntimeError(f"pagination mismatch: got {len(feats)}, service reports {expected}")
    return {"type": "FeatureCollection", "features": feats}


# --------------------------------------------------------------------------- clean
def _to_utc(ms: pd.Series) -> pd.Series:
    return pd.to_datetime(pd.to_numeric(ms, errors="coerce"), unit="ms", utc=True)


def clean(fc: dict, cfg: Config) -> tuple[gpd.GeoDataFrame, dict]:
    c = cfg.section("incidents")
    log: dict = {"raw_records": len(fc["features"])}
    gdf = gpd.GeoDataFrame.from_features(fc["features"], crs=WGS84)
    gdf = gdf.rename(columns=RENAME)[[*RENAME.values(), "geometry"]]

    for col in DATE_COLS:
        gdf[col] = _to_utc(gdf[col])

    # Dates: ArcGIS stores date-only values as 00:00 UTC. A clock time repeated across many records
    # (e.g. 15:38 x49) is a bulk-load artefact, not a real report time.
    hhmm = gdf["incident_date"].dt.strftime("%H:%M")
    repeated = hhmm.map(hhmm.value_counts()) > 10
    gdf["incident_time_known"] = (hhmm != "00:00") & ~repeated
    # Calendar date of the report. For date-only values the UTC date *is* the intended local date.
    local = gdf["incident_date"].dt.tz_convert(c["local_timezone"])
    gdf["incident_date_local"] = np.where(gdf["incident_time_known"], local.dt.date,
                                          gdf["incident_date"].dt.date)
    gdf["incident_date_local"] = pd.to_datetime(gdf["incident_date_local"])
    gdf["date_suspect"] = gdf["incident_date"].isna() | (
        gdf["incident_date_local"] < pd.Timestamp(c["suspect_date_before"]))

    # Missing-value normalisation for placeholders.
    gdf["asset_material"] = gdf["asset_material"].replace({"XXX": None, "": None})
    gdf["asset_size_mm"] = gdf["asset_size_mm"].where(gdf["asset_size_mm"] > 0)
    gdf["asset_depth_m"] = gdf["asset_depth_m"].where(gdf["asset_depth_m"] > 0)
    yr = pd.to_numeric(gdf["asset_year_installed"], errors="coerce")
    yr = yr.where((yr >= 1850) & (yr <= date.today().year))
    gdf["asset_year_installed"] = yr.astype("Int64")
    age = gdf["incident_date_local"].dt.year - gdf["asset_year_installed"]
    gdf["asset_age_years"] = age.where(age >= 0).astype("Int64")
    for col in ("break_nature", "break_apparent_cause"):
        gdf[col] = gdf[col].replace({"UNKNOWN": None})
    for col in ("incident_id", "objectid", "asset_id", "road_segment_id"):
        gdf[col] = pd.to_numeric(gdf[col], errors="coerce").astype("Int64")
    for col in ("asset_id", "road_segment_id"):  # 0 is a "no linked asset" placeholder
        gdf[col] = gdf[col].mask(gdf[col] <= 0)

    # Invalid locations.
    x0, y0, x1, y1 = c["valid_bbox"]
    ok = gdf.geometry.notna() & ~gdf.geometry.is_empty
    ok &= gdf.geometry.x.between(x0, x1) & gdf.geometry.y.between(y0, y1)
    log["dropped_invalid_location"] = int((~ok).sum())
    gdf = gdf[ok].copy()
    log["dropped_missing_date"] = int(gdf["incident_date"].isna().sum())
    gdf = gdf[gdf["incident_date"].notna()].copy()

    # Exact duplicates on the incident ID: keep the most recently updated record.
    n = len(gdf)
    gdf = gdf.sort_values("update_date").drop_duplicates("incident_id", keep="last")
    log["dropped_duplicate_incident_id"] = n - len(gdf)

    gdf["lon"], gdf["lat"] = gdf.geometry.x, gdf.geometry.y
    utm = gdf.geometry.to_crs(UTM_CRS)
    gdf["utm_x"], gdf["utm_y"] = utm.x, utm.y

    # Probable duplicates: same asset, same calendar date, within duplicate_distance_m.
    # Grouped (not dropped) so analysts can inspect; `is_primary_record` keeps the most complete one.
    gdf["completeness"] = gdf[["asset_size_mm", "asset_material", "asset_year_installed",
                               "break_nature", "repair_type"]].notna().sum(axis=1)
    gdf = gdf.sort_values(["incident_date", "completeness"], ascending=[True, False]).reset_index(drop=True)
    gdf["duplicate_group"] = pd.array([pd.NA] * len(gdf), dtype="Int64")
    # Key on the asset; without one, fall back to the location rounded to 10 m.
    key = gdf["asset_id"].astype("string").fillna(
        "xy" + (gdf["utm_x"] // 10).astype(int).astype(str) + "_" + (gdf["utm_y"] // 10).astype(int).astype(str))
    for _, grp in gdf.groupby([key, gdf["incident_date_local"].dt.date]):
        if len(grp) < 2:
            continue
        d = np.hypot(grp["utm_x"] - grp["utm_x"].iloc[0], grp["utm_y"] - grp["utm_y"].iloc[0])
        members = grp.index[d <= c["duplicate_distance_m"]]
        if len(members) > 1:
            gdf.loc[members, "duplicate_group"] = int(gdf.loc[members[0], "incident_id"])
    gdf["is_primary_record"] = gdf["duplicate_group"].isna() | (
        gdf["incident_id"] == gdf["duplicate_group"])
    log["possible_duplicate_records"] = int((~gdf["is_primary_record"]).sum())
    gdf["is_cancelled"] = gdf["status"].eq("CANCELLED")
    # No street address and no linked asset: the point may be a default/placeholder location.
    gdf["location_suspect"] = gdf["street"].isna() & gdf["asset_id"].isna()
    log["location_suspect"] = int(gdf["location_suspect"].sum())

    # Historical-incident features computed strictly from *earlier* incidents (no leakage).
    gdf = _history_features(gdf)
    gdf = gdf.drop(columns="completeness")
    order = ["incident_id", "incident_date", "incident_date_local", "incident_time_known", "date_suspect",
             "break_type", "is_cancelled", "is_primary_record", "location_suspect", "duplicate_group", "lon", "lat", "utm_x",
             "utm_y", "street", "civic_number", "asset_id", "road_segment_id", "asset_material",
             "asset_size_mm", "asset_year_installed", "asset_age_years", "asset_depth_m",
             "prior_breaks_same_asset", "prior_breaks_within_100m_5y"]
    rest = [col for col in gdf.columns if col not in order and col != "geometry"]
    gdf = gdf[[*order, *rest, "geometry"]].sort_values("incident_date").reset_index(drop=True)
    log["clean_records"] = len(gdf)
    return gdf, log


def _history_features(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    t = gdf["incident_date_local"].to_numpy()
    xy = gdf[["utm_x", "utm_y"]].to_numpy()
    asset = gdf["asset_id"].fillna(-1).to_numpy(dtype=np.int64)
    usable = (gdf["is_primary_record"] & ~gdf["is_cancelled"] & ~gdf["date_suspect"]).to_numpy()
    five_years = np.timedelta64(5 * 365, "D")
    same, near = np.zeros(len(gdf), int), np.zeros(len(gdf), int)
    for i in range(len(gdf)):
        earlier = usable & (t < t[i])
        if asset[i] >= 0:
            same[i] = int((earlier & (asset == asset[i])).sum())
        recent = earlier & (t >= t[i] - five_years)
        near[i] = int((np.hypot(*(xy[recent] - xy[i]).T) <= 100).sum())
    gdf["prior_breaks_same_asset"] = same
    gdf["prior_breaks_within_100m_5y"] = near
    return gdf


# --------------------------------------------------------------------------- run
def run(cfg: Config) -> gpd.GeoDataFrame:
    print("Stage 1 - Kitchener incidents")
    fc = fetch_raw(cfg)
    raw_path = cfg.path("raw_dir") / f"kitchener_incidents_raw_{date.today():%Y%m%d}.geojson"
    raw_path.write_text(json.dumps(fc))
    print(f"  raw snapshot  -> {report_file(raw_path)}")

    gdf, log = clean(fc, cfg)
    meta = {"column_roles": COLUMN_ROLES, "cleaning_log": log,
            "source": cfg.section("incidents")["feature_service"], "fetched": str(date.today())}
    gdf.to_parquet(cfg.incidents_parquet, schema_version="1.0.0")
    _attach_metadata(cfg.incidents_parquet, {"aquaguard": json.dumps(meta)})
    for k, v in log.items():
        print(f"  {k:32s} {v}")
    print(f"  clean dataset -> {report_file(cfg.incidents_parquet)}")
    return gdf


def _attach_metadata(path, extra: dict) -> None:
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    md = dict(table.schema.metadata or {})
    md.update({k.encode(): v.encode() for k, v in extra.items()})
    pq.write_table(table.replace_schema_metadata(md), path)


def load(cfg: Config) -> gpd.GeoDataFrame:
    return gpd.read_parquet(cfg.incidents_parquet)
